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

@app.route('/history')
@login_required
def history():
    # Show all debts that involve me (either as payer or debtor)
    # Actually, user wants to see "all the history". Let's show all for now or just relevant?
    # "users can see all the history" - implies transparency.
    expenses = Expense.query.order_by(Expense.date.desc()).all()
    return render_template('history.html', expenses=expenses)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

