from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime
from sqlalchemy.orm import joinedload

from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from urllib.parse import urlparse, urljoin

from flask_wtf import CSRFProtect
from forms import LoginForm, RegisterForm
import os
from flask import jsonify

# ⬇️ Import desc for use in index
from sqlalchemy import desc

from dotenv import load_dotenv
load_dotenv()  # ← This loads .env into os.environ


app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI', 'sqlite:///test.db')
# 👇 ADDED: Increase CSRF token timeout to 12 hours (43200 seconds)
app.config['WTF_CSRF_TIME_LIMIT'] = 43200
db = SQLAlchemy(app)
migrate = Migrate(app, db)
csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Set the route name for the login page

@login_manager.user_loader
def load_user(user_id):
    # This function is crucial! It tells Flask-Login how to load the user.
    return User.query.get(int(user_id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    # You need a password field for security, even if testing:
    password_hash = db.Column(db.String(128), nullable=False)
    boards = db.relationship('Board', backref='user', lazy=True, cascade="all, delete-orphan")
    
    boards = db.relationship('Board', backref='owner', lazy=True)

    def __repr__(self):
        return f'<User {self.username}>'

class Board(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    # The 'lists' attribute allows you to access all lists belonging to this board
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    lists = db.relationship('List', backref='board', lazy=True, cascade="all, delete-orphan")


class List(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    # Foreign Key linking list back to the board
    board_id = db.Column(db.Integer, db.ForeignKey('board.id'), nullable=False)
    # The 'cards' attribute allows you to access all cards belonging to this list
    cards = db.relationship('Card', backref='list', lazy=True, cascade="all, delete-orphan")

class Card(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(200), nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    # Foreign Key linking card back to the list
    list_id = db.Column(db.Integer, db.ForeignKey('list.id'), nullable=False)

from flask_login import login_required, current_user # Make sure these are imported

@app.route('/')
@login_required # Ensures only logged-in users can see this page
def index():
    # In app.py, inside your index route:
    # from sqlalchemy import desc # ⬅️ Make sure you import this if you use it (Moved to top of file)

    boards = Board.query.filter_by(user_id=current_user.id)\
                     .order_by(desc(Board.id))\
                     .all()
    # Fetch boards related to the current user (Flask-SQLAlchemy relationship)
    user_boards = current_user.boards 
    
    return render_template('index.html', boards=user_boards)


@app.route('/login', methods=['GET', 'POST'])
def login():
    # 1. Instantiate the form
    form = LoginForm() 

    # 2. Check form submission (POST)
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()

        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            flash(f'Logged in successfully as {user.username}.', 'success')
            
            # Redirect to the 'next' page if requested (e.g., after being redirected from a protected page)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Login Unsuccessful. Check username and password.', 'danger')

    # 3. For GET request or failed POST, render the template
    return render_template('login.html', form=form)

# In your app.py, add this route:

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm() 

    if form.validate_on_submit():
        # 1. Corrected Hashing: Remove 'method='sha256'
        hashed_password = generate_password_hash(form.password.data) 
        
        # 2. Create the new User object (must include email, as per your template)
        new_user = User(
            username=form.username.data,
            # Assuming you added the email column to your User model:
            email=form.email.data, 
            password_hash=hashed_password
        )
        
        # 3. Save the new user to the database
        try:
            db.session.add(new_user)
            db.session.commit()
            
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        
        except Exception as e:
            # Rollback in case of a unique constraint violation (username/email already taken)
            db.session.rollback()
            flash('An error occurred during registration. Check if username or email is already in use.', 'danger')
            print(f"Registration DB Error: {e}")
            
    # For GET request or if validation fails (POST)
    return render_template('register.html', form=form)

# In app.py, replace the existing new_board route:

@app.route('/boards/new', methods=['POST'])
@login_required 
def new_board():
    board_title = request.form.get('title') 
    
    if not board_title:
        # Check if it's an AJAX request (optional, but good practice)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Board title cannot be empty.'}), 400
        flash("Board title cannot be empty.", 'danger')
        return redirect(url_for('index'))
        
    new_board = Board(
        title=board_title,
        user_id=current_user.id 
    )

    try:
        db.session.add(new_board)
        db.session.commit()
        
        # 🔑 CHANGE: If it's an AJAX request, return JSON success
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
             # Return the newly created board data for Vue to display instantly
            return jsonify({
                'success': True, 
                'message': f'Board "{board_title}" created successfully!',
                'board': {
                    'id': new_board.id,
                    'title': new_board.title,
                    'list_count': 0 # New boards have 0 lists
                }
            }), 201
            
        flash(f'Board "{board_title}" created successfully!', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        db.session.rollback()
        
        # 🔑 CHANGE: If it's an AJAX request, return JSON failure
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
             return jsonify({'success': False, 'message': 'There was an issue creating the board.'}), 500
        
        flash('There was an issue creating the board.', 'danger')
        print(f"Board Creation Error: {e}")
        return redirect(url_for('index'))

# NOTE: The old 'else: return render_template('new_board.html')' is removed since 
# the form is submitted from the index page.

        
# In app.py, replace the existing new_list route:

@app.route('/board/<int:board_id>/list/new', methods=['POST'])
@login_required 
def new_list(board_id): # ✅ CRITICAL FIX: Parameter name must be 'board_id'
    board = Board.query.get_or_404(board_id)

    # Security Check: Ensure user owns the board before adding a list
    if board.user_id != current_user.id:
        flash("Unauthorized action.", 'danger')
        return redirect(url_for('index'))

    list_title = request.form.get('title')
    
    if not list_title:
        flash('List title cannot be empty.', 'danger')
        return redirect(url_for('view_board', board_id=board.id))
        
    new_list = List(title=list_title, board_id=board.id)
    
    try:
        db.session.add(new_list)
        db.session.commit()
        flash(f'List "{list_title}" added.', 'success')
        return redirect(url_for('view_board', board_id=board.id))
    except Exception as e:
        db.session.rollback()
        flash('There was an issue creating the list.', 'danger')
        print(f"List Creation Error: {e}")
        return redirect(url_for('view_board', board_id=board.id))

# In app.py

# In app.py, add this new route:

@app.route('/board/<int:board_id>')
@login_required # Ensure the user is logged in
def view_board(board_id):
    # Load the board and all its associated lists and cards using joinedload for efficiency
    board = db.session.query(Board).options(
        joinedload(Board.lists).joinedload(List.cards)
    ).filter(Board.id == board_id).first_or_404()
    
    # Security Check: Ensure the logged-in user owns this board
    if board.user_id != current_user.id:
        flash("You do not have permission to view that board.", 'danger')
        return redirect(url_for('index'))

    # Assumes you have already created the board_detail.html template
    return render_template('board_detail.html', board=board)

# In app.py, replace the existing create_card route:

@app.route('/list/<int:list_id>/card/new', methods=['POST'])
@login_required # Ensure only logged-in users can create cards
def create_card(list_id):
    card_content = request.form.get('content')
    list_parent = List.query.get_or_404(list_id)

    # Security check: Ensure the user owns the list's board
    if list_parent.board.user_id != current_user.id:
        flash("Unauthorized action.", 'danger')
        return redirect(url_for('index'))

    if not card_content:
        flash('Card content cannot be empty.', 'danger')
        # Redirect back to the board detail page
        return redirect(url_for('view_board', board_id=list_parent.board_id))
    
    # Card creation logic
    new_card = Card(
        content=card_content,
        list_id=list_id
    )
    
    try:
        db.session.add(new_card)
        db.session.commit()
        flash('Card created successfully!', 'success')
        # Redirect back to the board detail page
        return redirect(url_for('view_board', board_id=list_parent.board_id))
    except Exception as e:
        db.session.rollback()
        flash('There was an issue creating your card.', 'danger')
        print(f'Error creating card: {e}')
        return redirect(url_for('view_board', board_id=list_parent.board_id))

# In app.py, add this new route:

@app.route('/board/<int:board_id>/delete', methods=['POST'])
@login_required 
def delete_board(board_id):
    # 1. Load the board
    board = Board.query.get_or_404(board_id)
    
    # 2. Security Check: Only the board owner can delete it
    if board.user_id != current_user.id:
        flash("Unauthorized to delete this board.", 'danger')
        return redirect(url_for('index'))
    
    # 3. Handle Deletion
    # NOTE: SQLAlchemy's cascade delete behavior (if configured in your models) 
    # will automatically delete all associated lists and cards.
    try:
        db.session.delete(board)
        db.session.commit()
        flash(f'Board "{board.title}" successfully deleted.', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        db.session.rollback()
        flash('There was an error deleting the board.', 'danger')
        print(f"Delete Board Error: {e}")
        return redirect(url_for('index'))

# In app.py, add this new route:

@app.route('/list/<int:list_id>/delete', methods=['POST'])
@login_required 
def delete_list(list_id):
    # 1. Load the list and its parent board
    list_to_delete = List.query.get_or_404(list_id)
    board_id = list_to_delete.board_id
    
    # 2. Security Check: Only the owner of the board can delete its lists
    if list_to_delete.board.user_id != current_user.id:
        flash("Unauthorized to delete this list.", 'danger')
        return redirect(url_for('index'))
    
    # 3. Handle Deletion
    try:
        db.session.delete(list_to_delete)
        db.session.commit()
        flash(f'List "{list_to_delete.title}" successfully deleted.', 'success')
        # Redirect back to the board detail page
        return redirect(url_for('view_board', board_id=board_id)) 
    except Exception as e:
        db.session.rollback()
        flash('There was an error deleting the list.', 'danger')
        print(f"Delete List Error: {e}")
        return redirect(url_for('view_board', board_id=board_id))

# In app.py, add this new route:

@app.route('/card/<int:card_id>/delete', methods=['POST'])
@login_required 
def delete_card(card_id):
    # 1. Load the card and its parent list/board
    card_to_delete = Card.query.get_or_404(card_id)
    # The board ID is needed for the redirect
    board_id = card_to_delete.list.board_id 
    
    # 2. Security Check: Only the owner of the board can delete its cards
    if card_to_delete.list.board.owner != current_user: # NOTE: This uses the 'owner' backref you defined
        flash("Unauthorized to delete this card.", 'danger')
        return redirect(url_for('index'))
    
    # 3. Handle Deletion
    try:
        db.session.delete(card_to_delete)
        db.session.commit()
        flash(f'Card successfully deleted.', 'success')
        # Redirect back to the board detail page
        return redirect(url_for('view_board', board_id=board_id)) 
    except Exception as e:
        db.session.rollback()
        flash('There was an error deleting the card.', 'danger')
        print(f"Delete Card Error: {e}")
        return redirect(url_for('view_board', board_id=board_id))


@app.route('/logout')
@login_required # Only logged-in users can access this route
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index')) # Redirect to the index (which will send them to login)
        
if __name__ == '__main__':
    app.run(debug=True)