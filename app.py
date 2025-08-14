import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import bcrypt

# Initialize Flask app
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///local.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Fix PostgreSQL URL format for Railway
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')

# Initialize database
db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    cookies_earned = db.Column(db.Integer, default=0)
    total_tasks_completed = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    def set_password(self, password):
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'username': self.username,
            'cookies_earned': self.cookies_earned,
            'total_tasks_completed': self.total_tasks_completed,
            'created_at': self.created_at.isoformat()
        }

class Task(db.Model):
    __tablename__ = 'tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    task_type = db.Column(db.String(50), nullable=False)
    task_name = db.Column(db.String(200), nullable=False)
    task_url = db.Column(db.String(500))
    cookies_reward = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='completed')
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='tasks')

class TaskType(db.Model):
    __tablename__ = 'task_types'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200), nullable=False)
    cookies_reward = db.Column(db.Integer, nullable=False)
    task_url = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username') 
        password = request.form.get('password')
        
        # Validation
        if not email or not username or not password:
            flash('All fields are required!')
            return redirect(url_for('register'))
        
        # Check if user already exists
        existing_user = User.query.filter(
            (User.email == email) | (User.username == username)
        ).first()
        
        if existing_user:
            flash('User with this email or username already exists!')
            return redirect(url_for('register'))
        
        # Create new user
        try:
            user = User(email=email, username=username)
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            session['user_id'] = user.id
            flash('Account created successfully!')
            return redirect(url_for('dashboard'))
        
        except Exception as e:
            db.session.rollback()
            flash('Error creating account. Please try again.')
            print(f"register error: {e}")
            return redirect(url_for('register'))
    
    return render_template('register.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            flash('Email and password are required!')
            return redirect(url_for('login'))
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            flash('Login successful!')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password!')
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please log in to access dashboard.')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('User not found. Please log in again.')
        return redirect(url_for('login'))
    
    # Get available task types
    available_tasks = TaskType.query.filter_by(is_active=True).all()
    
    # Get user's recent tasks
    recent_tasks = Task.query.filter_by(user_id=user.id).order_by(Task.completed_at.desc()).limit(10).all()
    
    return render_template('dashboard.html', 
                         user=user, 
                         available_tasks=available_tasks, 
                         recent_tasks=recent_tasks)

@app.route('/complete_task', methods=['POST'])
def complete_task():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.get_json()
    task_type_id = data.get('task_type_id')
    task_url = data.get('task_url', '')
    
    if not task_type_id:
        return jsonify({'error': 'Task type is required'}), 400
    
    # Get task type
    task_type = TaskType.query.get(task_type_id)
    if not task_type or not task_type.is_active:
        return jsonify({'error': 'Invalid task type'}), 400
    
    # Get user
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 401
    
    try:
        # Create new task
        task = Task(
            user_id=user.id,
            task_type=task_type.name,
            task_name=task_type.description,
            task_url=task_url,
            cookies_reward=task_type.cookies_reward
        )
        
        # Update user's stats
        user.cookies_earned += task_type.cookies_reward
        user.total_tasks_completed += 1
        
        db.session.add(task)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Task completed successfully!',
            'cookies_earned': task_type.cookies_reward,
            'total_cookies': user.cookies_earned,
            'total_tasks': user.total_tasks_completed
        })
    
    except Exception as e:
        db.session.rollback()
        print(f"Task completion error: {e}")
        return jsonify({'error': 'Failed to complete task'}), 500

@app.route('/user_stats')
def user_stats():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 401
    
    return jsonify(user.to_dict())

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('index'))

@app.route('/health')
def health():
    return {'status': 'healthy'}, 200

# Initialize database
def init_db():
    with app.app_context():
        try:
            db.create_all()
            print("✅ Database tables created!")
            
            # Create sample task types if none exist
            if TaskType.query.count() == 0:
                sample_tasks = [
                    TaskType(name='survey', description='Complete Online Survey', cookies_reward=10),
                    TaskType(name='video_watch', description='Watch YouTube Video', cookies_reward=5),
                    TaskType(name='social_follow', description='Follow Social Media Account', cookies_reward=3),
                    TaskType(name='app_install', description='Install Mobile App', cookies_reward=15),
                    TaskType(name='website_visit', description='Visit Partner Website', cookies_reward=2),
                ]
                
                for task in sample_tasks:
                    db.session.add(task)
                
                db.session.commit()
                print("✅ Sample tasks created!")
        except Exception as e:
            print(f"❌ Database error: {e}")

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
