from flask_login import UserMixin
from extensions import login_manager
from database import get_db_connection


class User(UserMixin):
    def __init__(self, id, email, role, username):
        self.id = id
        self.email = email
        self.role = role
        self.username = username


@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user:
        return User(id=user['id'], email=user['email'], role=user['role'], username=user['username'])
    return None
