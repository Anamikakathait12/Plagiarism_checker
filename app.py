import os
from flask import Flask, render_template
from flask_mail import Mail
from flask_login import LoginManager

from config import Config
from database import init_db, get_db_connection
from routes.auth_helpers import User
from routes.auth import auth_bp, init_mail
from routes.student import student_bp
from routes.teacher import teacher_bp
from routes.compare import compare_bp


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Extensions
    mail = Mail(app)
    init_mail(mail)          # give auth blueprint access to the mail instance

    # Flask-Login
    login_manager = LoginManager(app)
    login_manager.login_view = 'auth.student_login_page'

    @login_manager.user_loader
    def load_user(user_id):
        conn  = get_db_connection()
        user  = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        if user:
            return User(id=user['id'], email=user['email'],
                        role=user['role'], username=user['username'])
        return None

    # Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(compare_bp)

    # Home route
    @app.route('/')
    def index():
        return render_template('index.html')

    # Database initialisation
    with app.app_context():
        init_db()

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    app = create_app()
    print("Server running...")
    app.run(debug=True)
