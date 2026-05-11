from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_user, logout_user, login_required
from werkzeug.security import check_password_hash

from database import get_db_connection, register_user
from services.email_service import send_verification_email, verify_token

auth_bp = Blueprint('auth', __name__)

_mail = None

def init_mail(mail_instance):
    global _mail
    _mail = mail_instance


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@auth_bp.route('/student-login')
def student_login_page():
    return render_template('student-login.html')


@auth_bp.route('/teacher-login')
def teacher_login_page():
    return render_template('teacher-login.html')


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

@auth_bp.route('/register', methods=['POST'])
def register():
    username = request.form.get('username', '').strip()
    email    = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    role     = request.form.get('role', '')

    template = 'student-login.html' if role == 'student' else 'teacher-login.html'

    # --- Run all validations (database.py handles them) ---
    success, error = register_user(username, email, password, role)

    if not success:
        # Send the exact error message back to the template
        return render_template(template, error=error,
                               reg_username=username, reg_email=email, reg_role=role)

    # --- User saved, now send verification email ---
    sent, mail_error = send_verification_email(_mail, username, email)

    if not sent:
        print(f"Mail Error: {mail_error}")
        return render_template(template,
                               error="Account created but verification email could not be sent. "
                                     "Please contact support.",
                               reg_role=role)

    return render_template(template,
                           success="Account created! Please check your email to verify your account before logging in.",
                           reg_role=role)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@auth_bp.route('/login', methods=['POST'])
def login():
    from routes.auth_helpers import User

    identifier = request.form.get('identifier', '').strip()
    password   = request.form.get('password', '')
    role       = request.form.get('role', '')
    template   = 'student-login.html' if role == 'student' else 'teacher-login.html'

    conn = get_db_connection()
    user = conn.execute(
        'SELECT * FROM users WHERE email = ? OR username = ?',
        (identifier, identifier)
    ).fetchone()
    conn.close()

    # --- Check 1: Does the user exist and is the password correct? ---
    if not user or not check_password_hash(user['password'], password):
        return render_template(template,
                               error="Incorrect username/email or password. Please try again.",
                               login_identifier=identifier)

    # --- Check 2: Is the role correct? ---
    if user['role'] != role:
        return render_template(template,
                               error=f"This account is registered as a '{user['role']}', not a '{role}'.",
                               login_identifier=identifier)

    # --- Check 3: Has the email been verified? ---
    if not user['is_verified']:
        return render_template(template,
                               error="Your email is not verified yet. Please check your inbox for the verification link.",
                               login_identifier=identifier)

    # --- All checks passed ---
    login_user(User(id=user['id'], email=user['email'],
                    role=user['role'], username=user['username']))

    return (
        redirect(url_for('student.student_portal'))
        if role == 'student'
        else redirect(url_for('teacher.teacher_portal'))
    )


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

@auth_bp.route('/confirm_email/<token>')
def confirm_email(token):
    email, error = verify_token(token)

    if error:
        if 'expired' in str(error).lower():
            return render_template('student-login.html',
                                   error="Verification link has expired. Please register again.")
        return render_template('student-login.html',
                               error="Invalid verification link.")

    conn = get_db_connection()
    conn.execute('UPDATE users SET is_verified = 1 WHERE email = ?', (email,))
    conn.commit()
    conn.close()

    return render_template('student-login.html',
                           success="Email verified successfully! You can now log in.")
