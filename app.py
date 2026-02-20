from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Expense, Settlement, EmailSettings
from email_service import send_expense_notification, send_bulk_reminders, send_payment_notification
from apscheduler.schedulers.background import BackgroundScheduler
import os
import atexit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expenses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# APScheduler setup
scheduler = BackgroundScheduler()
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Initialize DB
with app.app_context():
    db.create_all()
    # Create default admin if not exists
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password=generate_password_hash('admin123', method='pbkdf2:sha256'), is_admin=True)
        db.session.add(admin)
        db.session.commit()
    # Create default email settings if not exists
    if not EmailSettings.query.first():
        db.session.add(EmailSettings())
        db.session.commit()

def reschedule_reminders():
    """Reschedule the reminder job based on current settings."""
    with app.app_context():
        settings = EmailSettings.query.first()
        if scheduler.get_job('reminder_job'):
            scheduler.remove_job('reminder_job')
        if settings and settings.reminders_enabled and settings.gmail_address:
            scheduler.add_job(
                func=lambda: send_bulk_reminders(app),
                trigger='interval',
                hours=settings.reminder_hours,
                id='reminder_job',
                replace_existing=True
            )

# Start scheduler with saved settings on boot
with app.app_context():
    reschedule_reminders()

@app.route('/')
@login_required
def dashboard():
    # Calculate debts
    # My Debts (I owe others)
    my_debts = Settlement.query.filter_by(user_id=current_user.id, is_paid=False).all()
    
    # Owed to Me (Others owe me)
    # Get all expenses I paid for
    my_expenses = Expense.query.filter_by(payer_id=current_user.id).all()
    owed_to_me = []
    for exp in my_expenses:
        for settlement in exp.settlements:
            if not settlement.is_paid and settlement.user_id != current_user.id:
                 owed_to_me.append(settlement)
    
    # Calculate total balances
    total_debt = sum(debt.amount_due for debt in my_debts)
    total_owed = sum(debt.amount_due for debt in owed_to_me)
                 
    return render_template('dashboard.html', my_debts=my_debts, owed_to_me=owed_to_me, 
                          total_debt=total_debt, total_owed=total_owed)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/add_user', methods=['GET', 'POST'])
@login_required
def add_user():
    if not current_user.is_admin:
        flash('Unauthorized')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email', '').strip()
        
        if User.query.filter_by(username=username).first():
            flash('User already exists')
        else:
            new_user = User(username=username, password=generate_password_hash(password, method='pbkdf2:sha256'), is_admin=False, email=email or None)
            db.session.add(new_user)
            db.session.commit()
            flash('User added successfully')
        return redirect(url_for('add_user')) # Stay on admin page
    
    # GET request - show all users with statistics
    all_users = User.query.filter_by(is_admin=False).all()
    
    # Calculate statistics for each user
    user_stats = []
    for user in all_users:
        # Calculate what they owe
        debts = Settlement.query.filter_by(user_id=user.id, is_paid=False).all()
        total_owed_by_user = sum(debt.amount_due for debt in debts)
        
        # Calculate what they're owed (expenses they paid for)
        expenses_paid = Expense.query.filter_by(payer_id=user.id).all()
        total_owed_to_user = 0
        for exp in expenses_paid:
            for settlement in exp.settlements:
                if not settlement.is_paid and settlement.user_id != user.id:
                    total_owed_to_user += settlement.amount_due
        
        user_stats.append({
            'user': user,
            'owes': total_owed_by_user,
            'owed': total_owed_to_user,
            'balance': total_owed_to_user - total_owed_by_user
        })
    
    email_settings = EmailSettings.query.first()
    return render_template('admin.html', user_stats=user_stats, email_settings=email_settings)

@app.route('/save_email_settings', methods=['POST'])
@login_required
def save_email_settings():
    if not current_user.is_admin:
        flash('Unauthorized')
        return redirect(url_for('dashboard'))
    
    settings = EmailSettings.query.first()
    settings.gmail_address = request.form.get('gmail_address', '').strip()
    settings.gmail_app_password = request.form.get('gmail_app_password', '').strip()
    settings.reminder_hours = int(request.form.get('reminder_hours', 24))
    settings.reminders_enabled = request.form.get('reminders_enabled') == 'on'
    db.session.commit()
    
    # Reschedule with new settings
    reschedule_reminders()
    flash('Email settings saved successfully!')
    return redirect(url_for('add_user'))

@app.route('/send_reminders_now', methods=['POST'])
@login_required
def send_reminders_now():
    if not current_user.is_admin:
        flash('Unauthorized')
        return redirect(url_for('dashboard'))
    send_bulk_reminders(app)
    flash('Reminder emails sent to all users with unpaid balances!')
    return redirect(url_for('add_user'))

@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash('Unauthorized')
        return redirect(url_for('dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    # Prevent deleting admin
    if user.is_admin:
        flash('Cannot delete admin users')
        return redirect(url_for('add_user'))
    
    # Delete all settlements related to this user
    Settlement.query.filter_by(user_id=user_id).delete()
    
    # Delete all expenses paid by this user (and their settlements)
    expenses = Expense.query.filter_by(payer_id=user_id).all()
    for expense in expenses:
        Settlement.query.filter_by(expense_id=expense.id).delete()
        db.session.delete(expense)
    
    # Delete the user
    db.session.delete(user)
    db.session.commit()
    
    flash(f'User {user.username} deleted successfully')
    return redirect(url_for('add_user'))

@app.route('/add_expense', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        description = request.form.get('description')
        try:
            total_amount = float(request.form.get('amount'))
        except (ValueError, TypeError):
            flash('Invalid amount entered.')
            users = User.query.filter_by(is_admin=False).all()
            return render_template('add_expense.html', users=users)

        # Block negative or zero amounts
        if total_amount <= 0:
            flash('Amount must be greater than zero.')
            users = User.query.filter_by(is_admin=False).all()
            return render_template('add_expense.html', users=users)

        # Get selected users from checkboxes (exclude any admin IDs)
        admin_ids = {str(u.id) for u in User.query.filter_by(is_admin=True).all()}
        selected_user_ids = [uid for uid in request.form.getlist('selected_users') if uid not in admin_ids]

        if not selected_user_ids:
            flash('Please select at least one user to split with')
            users = User.query.filter_by(is_admin=False).all()
            return render_template('add_expense.html', users=users)

        # Check if custom amounts are provided
        use_custom = request.form.get('use_custom') == 'true'

        # Include payer in the split only if payer is NOT admin
        if not current_user.is_admin and str(current_user.id) not in selected_user_ids:
            selected_user_ids.append(str(current_user.id))

        # Create Expense
        new_expense = Expense(description=description, amount=total_amount, payer_id=current_user.id)
        db.session.add(new_expense)
        db.session.commit()

        if use_custom:
            # Use custom amounts
            total_custom = 0
            settlements_to_add = []
            for user_id in selected_user_ids:
                custom_amount = request.form.get(f'amount_{user_id}', '0')
                try:
                    amount = float(custom_amount)
                    if amount < 0:
                        amount = 0
                    total_custom += amount
                except:
                    amount = 0

                uid = int(user_id)
                is_paid = (uid == current_user.id)
                settlements_to_add.append(Settlement(expense_id=new_expense.id, user_id=uid, amount_due=amount, is_paid=is_paid))

            # Validate that custom amounts match total
            if abs(total_custom - total_amount) > 0.01:
                db.session.rollback()
                flash(f'Custom amounts (PKR {total_custom:.2f}) must equal total amount (PKR {total_amount:.2f})')
                users = User.query.filter_by(is_admin=False).all()
                return render_template('add_expense.html', users=users)

            for s in settlements_to_add:
                db.session.add(s)
        else:
            # Equal split
            split_amount = total_amount / len(selected_user_ids)

            for user_id in selected_user_ids:
                uid = int(user_id)
                is_paid = (uid == current_user.id)
                settlement = Settlement(expense_id=new_expense.id, user_id=uid, amount_due=split_amount, is_paid=is_paid)
                db.session.add(settlement)

        db.session.commit()

        # Send email notifications
        fresh_settlements = Settlement.query.filter_by(expense_id=new_expense.id).all()
        try:
            send_expense_notification(new_expense, fresh_settlements)
        except Exception as e:
            print(f"[Email] Notification error: {e}")

        flash('Expense split successfully!')
        return redirect(url_for('dashboard'))

    # GET request - show form with non-admin users only
    users = User.query.filter_by(is_admin=False).all()
    return render_template('add_expense.html', users=users)


@app.route('/pay/<int:settlement_id>')
@login_required
def pay_settlement(settlement_id):
    settlement = Settlement.query.get_or_404(settlement_id)
    if settlement.user_id != current_user.id:
        flash('Unauthorized')
        return redirect(url_for('dashboard'))
    
    settlement.is_paid = True
    db.session.commit()
    
    # Notify the payer via email
    try:
        send_payment_notification(settlement)
    except Exception as e:
        print(f"[Email] Payment notification error: {e}")
    
    flash('Payment recorded')
    return redirect(url_for('dashboard'))

@app.route('/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    
    # Only payer or admin can edit
    if expense.payer_id != current_user.id and not current_user.is_admin:
        flash('Unauthorized')
        return redirect(url_for('history'))
    
    if request.method == 'POST':
        new_description = request.form.get('description')
        new_amount = float(request.form.get('amount'))
        
        # Get selected users from checkboxes
        selected_user_ids = request.form.getlist('selected_users')
        
        if not selected_user_ids:
            flash('Please select at least one user to split with')
            users = User.query.filter_by(is_admin=False).all()
            current_users = [s.user_id for s in expense.settlements]
            return render_template('edit_expense.html', expense=expense, users=users, current_users=current_users)
        
        # Check if custom amounts are provided
        use_custom = request.form.get('use_custom') == 'true'
        
        # Update expense
        expense.description = new_description
        expense.amount = new_amount
        
        # Delete old settlements
        Settlement.query.filter_by(expense_id=expense.id).delete()
        
        # Include payer in the split if not already selected
        if str(expense.payer_id) not in selected_user_ids:
            selected_user_ids.append(str(expense.payer_id))
        
        if use_custom:
            # Use custom amounts
            total_custom = 0
            for user_id in selected_user_ids:
                custom_amount = request.form.get(f'amount_{user_id}', '0')
                try:
                    amount = float(custom_amount)
                    total_custom += amount
                except:
                    amount = 0
                
                user_id = int(user_id)
                is_paid = (user_id == expense.payer_id)
                settlement = Settlement(expense_id=expense.id, user_id=user_id, amount_due=amount, is_paid=is_paid)
                db.session.add(settlement)
            
            # Validate that custom amounts match total
            if abs(total_custom - new_amount) > 0.01:
                db.session.rollback()
                flash(f'Custom amounts (PKR {total_custom:.2f}) must equal total amount (PKR {new_amount:.2f})')
                users = User.query.filter_by(is_admin=False).all()
                current_users = [int(uid) for uid in selected_user_ids]
                return render_template('edit_expense.html', expense=expense, users=users, current_users=current_users)
        else:
            # Equal split
            split_amount = new_amount / len(selected_user_ids)
            
            for user_id in selected_user_ids:
                user_id = int(user_id)
                is_paid = (user_id == expense.payer_id)
                settlement = Settlement(expense_id=expense.id, user_id=user_id, amount_due=split_amount, is_paid=is_paid)
                db.session.add(settlement)
        
        db.session.commit()
        flash('Expense updated successfully!')
        return redirect(url_for('history'))
    
    # GET request - show edit form
    users = User.query.filter_by(is_admin=False).all()
    current_users = [s.user_id for s in expense.settlements]
    current_amounts = {s.user_id: s.amount_due for s in expense.settlements}
    return render_template('edit_expense.html', expense=expense, users=users, current_users=current_users, current_amounts=current_amounts)

@app.route('/delete_expense/<int:expense_id>', methods=['POST'])
@login_required
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    
    # Only payer or admin can delete
    if expense.payer_id != current_user.id and not current_user.is_admin:
        flash('Unauthorized')
        return redirect(url_for('history'))
    
    # Delete all settlements
    Settlement.query.filter_by(expense_id=expense.id).delete()
    
    # Delete expense
    db.session.delete(expense)
    db.session.commit()
    
    flash('Expense deleted successfully')
    return redirect(url_for('history'))

@app.route('/statistics')
@login_required
def statistics():
    from datetime import datetime, timedelta
    from collections import defaultdict

    # --- Expenses the user PAID FOR ---
    my_paid_expenses = Expense.query.filter_by(payer_id=current_user.id).all()
    total_spent_as_payer = sum(exp.amount for exp in my_paid_expenses)

    # --- Settlements involving the current user (splits they owe) ---
    my_settlements = Settlement.query.filter_by(user_id=current_user.id).all()

    # Total I owe (unpaid debts on expenses others paid)
    total_owed = sum(
        s.amount_due for s in my_settlements
        if not s.is_paid and s.expense.payer_id != current_user.id
    )

    # Total amount of all splits I'm part of (my share across all expenses)
    total_my_share = sum(s.amount_due for s in my_settlements)

    # Total spent = amount I paid out-of-pocket for group + my share of others' expenses
    total_spent = total_spent_as_payer + sum(
        s.amount_due for s in my_settlements
        if s.expense.payer_id != current_user.id
    )

    # --- What others owe me (unpaid shares on expenses I paid) ---
    total_owed_to_me = 0
    for exp in my_paid_expenses:
        for settlement in exp.settlements:
            if not settlement.is_paid and settlement.user_id != current_user.id:
                total_owed_to_me += settlement.amount_due

    # Net balance: positive = people owe me more than I owe
    net_balance = total_owed_to_me - total_owed

    # --- Top 5 expenses user is involved in (as payer or participant) ---
    involved_expense_ids = {s.expense_id for s in my_settlements} | {e.id for e in my_paid_expenses}
    all_involved = Expense.query.filter(Expense.id.in_(involved_expense_ids)).all() if involved_expense_ids else []
    top_expenses = sorted(all_involved, key=lambda x: x.amount, reverse=True)[:5]

    # --- Monthly spending trend (last 6 months) — expenses user is involved in ---
    today = datetime.now()
    six_months_ago = today - timedelta(days=180)

    monthly_data = defaultdict(float)
    # Expenses I paid for
    for exp in my_paid_expenses:
        if exp.date >= six_months_ago:
            monthly_data[exp.date.strftime('%Y-%m')] += exp.amount
    # My share in expenses others paid
    for s in my_settlements:
        if s.expense.payer_id != current_user.id and s.expense.date >= six_months_ago:
            monthly_data[s.expense.date.strftime('%Y-%m')] += s.amount_due

    months = []
    amounts = []
    for i in range(5, -1, -1):
        d = today - timedelta(days=30 * i)
        months.append(d.strftime('%b %Y'))
        amounts.append(round(monthly_data.get(d.strftime('%Y-%m'), 0), 2))

    # --- Paid vs Unpaid settlements (my debts) ---
    paid_count = sum(1 for s in my_settlements if s.is_paid)
    unpaid_count = sum(1 for s in my_settlements if not s.is_paid)

    return render_template('statistics.html',
                          total_spent=total_spent,
                          total_owed=total_owed,
                          total_owed_to_me=total_owed_to_me,
                          net_balance=net_balance,
                          top_expenses=top_expenses,
                          months=months,
                          amounts=amounts,
                          paid_count=paid_count,
                          unpaid_count=unpaid_count)


@app.route('/history')
@login_required
def history():
    from datetime import datetime, timedelta

    # Get filter parameters
    search_query = request.args.get('search', '').strip()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    user_filter = request.args.get('user_id', '')
    status_filter = request.args.get('status', '')

    if current_user.is_admin:
        # Admin sees all expenses
        query = Expense.query
    else:
        # Get expense IDs where current user is involved (as payer or in settlement)
        payer_expense_ids = {e.id for e in Expense.query.filter_by(payer_id=current_user.id).all()}
        settlement_expense_ids = {s.expense_id for s in Settlement.query.filter_by(user_id=current_user.id).all()}
        involved_ids = payer_expense_ids | settlement_expense_ids
        query = Expense.query.filter(Expense.id.in_(involved_ids))

    # Apply search filter
    if search_query:
        query = query.filter(Expense.description.ilike(f'%{search_query}%'))

    # Apply date range filters
    if date_from:
        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
        query = query.filter(Expense.date >= date_from_obj)

    if date_to:
        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
        query = query.filter(Expense.date < date_to_obj)

    # Apply user (payer) filter
    if user_filter:
        query = query.filter(Expense.payer_id == int(user_filter))

    # Get expenses sorted newest first
    expenses = query.order_by(Expense.date.desc()).all()

    # Apply status filter (requires checking settlements)
    if status_filter:
        filtered_expenses = []
        for expense in expenses:
            if status_filter == 'paid':
                if all(s.is_paid for s in expense.settlements):
                    filtered_expenses.append(expense)
            elif status_filter == 'unpaid':
                if any(not s.is_paid for s in expense.settlements):
                    filtered_expenses.append(expense)
        expenses = filtered_expenses

    # Get all non-admin users for filter dropdown
    all_users = User.query.filter_by(is_admin=False).all()

    return render_template('history.html', expenses=expenses, all_users=all_users,
                          search_query=search_query, date_from=date_from, date_to=date_to,
                          user_filter=user_filter, status_filter=status_filter)


if __name__ == '__main__':
    app.run(debug=True)
