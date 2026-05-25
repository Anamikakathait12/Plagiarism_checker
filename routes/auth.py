from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_user, login_required, logout_user
from werkzeug.security import check_password_hash
from database import get_db_connection, register_user
from models import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/')
def index():
    return render_template('index.html')


@auth_bp.route('/student-login')
def student_login_page():
    return render_template('student-login.html')


@auth_bp.route('/teacher-login')
def teacher_login_page():
    return render_template('teacher-login.html')


@auth_bp.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    email    = request.form.get('email')
    password = request.form.get('password')
    role     = request.form.get('role')
    success  = register_user(username, email, password, role)
    template = 'student-login.html' if role == 'student' else 'teacher-login.html'
    if success:
        return render_template(template, success="Account created! You can now log in.")
    return render_template(template, error="Registration failed. Username or Email already taken.")


@auth_bp.route('/login', methods=['POST'])
def login():
    identifier = request.form.get('identifier')
    password   = request.form.get('password')
    role       = request.form.get('role')
    conn = get_db_connection()
    user = conn.execute(
        'SELECT * FROM users WHERE email = ? OR username = ?', (identifier, identifier)
    ).fetchone()
    conn.close()
    template = 'student-login.html' if role == 'student' else 'teacher-login.html'
    if user and check_password_hash(user['password'], password):
        if user['role'] != role:
            return render_template(template, error=f"Access denied. You are registered as a {user['role']}.")
        login_user(User(id=user['id'], email=user['email'], role=user['role'], username=user['username']))
        return redirect(url_for('student.student_portal')) if role == 'student' else redirect(url_for('teacher.teacher_portal'))
    return render_template(template, error="Invalid Username/Email or Password.")


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.index'))
