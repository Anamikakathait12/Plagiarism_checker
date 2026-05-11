from flask_login import UserMixin


class User(UserMixin):
    """Lightweight user object used by Flask-Login."""

    def __init__(self, id, email, role, username):
        self.id       = id
        self.email    = email
        self.role     = role
        self.username = username
