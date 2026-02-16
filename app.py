from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Expense, Settlement
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expenses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

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
        
        if User.query.filter_by(username=username).first():
            flash('User already exists')
        else:
            new_user = User(username=username, password=generate_password_hash(password, method='pbkdf2:sha256'), is_admin=False)
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
    
    return render_template('admin.html', user_stats=user_stats)

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
        amount = float(request.form.get('amount'))
        
        # Get selected users from checkboxes
        selected_user_ids = request.form.getlist('selected_users')
        
        if not selected_user_ids:
            flash('Please select at least one user to split with')
            users = User.query.filter_by(is_admin=False).all()
            return render_template('add_expense.html', users=users)
        
        # Create Expense
        new_expense = Expense(description=description, amount=amount, payer_id=current_user.id)
        db.session.add(new_expense)
        db.session.commit()
        
        # Include payer in the split if not already selected
        if str(current_user.id) not in selected_user_ids:
            selected_user_ids.append(str(current_user.id))
        
        # Split equally among selected users
        split_amount = amount / len(selected_user_ids)
        
        for user_id in selected_user_ids:
            user_id = int(user_id)
            is_paid = (user_id == current_user.id)
            settlement = Settlement(expense_id=new_expense.id, user_id=user_id, amount_due=split_amount, is_paid=is_paid)
            db.session.add(settlement)
        
        db.session.commit()
        flash('Expense split successfully!')
        return redirect(url_for('dashboard'))
    
    # GET request - show form with non-admin users
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
            # Get currently selected users
            current_users = [s.user_id for s in expense.settlements]
            return render_template('edit_expense.html', expense=expense, users=users, current_users=current_users)
        
        # Update expense
        expense.description = new_description
        expense.amount = new_amount
        
        # Delete old settlements
        Settlement.query.filter_by(expense_id=expense.id).delete()
        
        # Include payer in the split if not already selected
        if str(expense.payer_id) not in selected_user_ids:
            selected_user_ids.append(str(expense.payer_id))
        
        # Create new settlements
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
    return render_template('edit_expense.html', expense=expense, users=users, current_users=current_users)

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
    
    # Calculate total spent (expenses I paid for)
    my_expenses = Expense.query.filter_by(payer_id=current_user.id).all()
    total_spent = sum(exp.amount for exp in my_expenses)
    
    # Calculate total I owe (unpaid settlements)
    my_debts = Settlement.query.filter_by(user_id=current_user.id, is_paid=False).all()
    total_owed = sum(debt.amount_due for debt in my_debts)
    
    # Calculate what others owe me
    total_owed_to_me = 0
    for exp in my_expenses:
        for settlement in exp.settlements:
            if not settlement.is_paid and settlement.user_id != current_user.id:
                total_owed_to_me += settlement.amount_due
    
    # Net balance
    net_balance = total_owed_to_me - total_owed
    
    # Top 5 expenses
    top_expenses = sorted(my_expenses, key=lambda x: x.amount, reverse=True)[:5]
    
    # Monthly spending trend (last 6 months)
    today = datetime.now()
    six_months_ago = today - timedelta(days=180)
    
    monthly_data = defaultdict(float)
    for exp in my_expenses:
        if exp.date >= six_months_ago:
            month_key = exp.date.strftime('%Y-%m')
            monthly_data[month_key] += exp.amount
    
    # Generate all months for the last 6 months
    months = []
    amounts = []
    for i in range(5, -1, -1):
        month = (today - timedelta(days=30*i)).strftime('%Y-%m')
        months.append((today - timedelta(days=30*i)).strftime('%b %Y'))
        amounts.append(monthly_data.get(month, 0))
    
    # Paid vs Unpaid count
    all_settlements = Settlement.query.filter_by(user_id=current_user.id).all()
    paid_count = sum(1 for s in all_settlements if s.is_paid)
    unpaid_count = sum(1 for s in all_settlements if not s.is_paid)
    
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
    # Get filter parameters
    search_query = request.args.get('search', '').strip()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    user_filter = request.args.get('user_id', '')
    status_filter = request.args.get('status', '')
    
    # Base query
    query = Expense.query
    
    # Apply search filter
    if search_query:
        query = query.filter(Expense.description.ilike(f'%{search_query}%'))
    
    # Apply date range filters
    if date_from:
        from datetime import datetime
        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
        query = query.filter(Expense.date >= date_from_obj)
    
    if date_to:
        from datetime import datetime
        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
        # Add one day to include the entire end date
        from datetime import timedelta
        date_to_obj = date_to_obj + timedelta(days=1)
        query = query.filter(Expense.date < date_to_obj)
    
    # Apply user filter
    if user_filter:
        query = query.filter(Expense.payer_id == int(user_filter))
    
    # Get expenses
    expenses = query.order_by(Expense.date.desc()).all()
    
    # Apply status filter (requires checking settlements)
    if status_filter:
        filtered_expenses = []
        for expense in expenses:
            if status_filter == 'paid':
                # All settlements must be paid
                if all(s.is_paid for s in expense.settlements):
                    filtered_expenses.append(expense)
            elif status_filter == 'unpaid':
                # At least one settlement is unpaid
                if any(not s.is_paid for s in expense.settlements):
                    filtered_expenses.append(expense)
        expenses = filtered_expenses
    
    # Get all users for filter dropdown
    all_users = User.query.all()
    
    return render_template('history.html', expenses=expenses, all_users=all_users,
                          search_query=search_query, date_from=date_from, date_to=date_to,
                          user_filter=user_filter, status_filter=status_filter)

if __name__ == '__main__':
    app.run(debug=True)
