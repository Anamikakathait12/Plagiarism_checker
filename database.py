import re
import sqlite3
from werkzeug.security import generate_password_hash


def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    conn = get_db_connection()

    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        username    TEXT UNIQUE NOT NULL,
        email       TEXT UNIQUE NOT NULL,
        password    TEXT NOT NULL,
        role        TEXT NOT NULL,
        is_verified INTEGER DEFAULT 0)''')

    conn.execute('''CREATE TABLE IF NOT EXISTS courses (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT NOT NULL,
        code       TEXT UNIQUE NOT NULL,
        teacher_id INTEGER NOT NULL)''')

    conn.execute('''CREATE TABLE IF NOT EXISTS enrollments (
        student_id INTEGER,
        course_id  INTEGER,
        PRIMARY KEY (student_id, course_id))''')

    conn.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id   INTEGER,
        title       TEXT,
        deadline    TEXT,
        total_marks INTEGER DEFAULT 100,
        FOREIGN KEY(course_id) REFERENCES courses(id))''')

    conn.execute('''CREATE TABLE IF NOT EXISTS assignments (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        course_id  INTEGER,
        task_id    INTEGER,
        filename   TEXT NOT NULL,
        status     TEXT DEFAULT 'Pending',
        marks      INTEGER,
        comments   TEXT)''')

    conn.execute('''CREATE TABLE IF NOT EXISTS document_fingerprints (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        assignment_id INTEGER NOT NULL,
        hash_value    INTEGER NOT NULL,
        FOREIGN KEY(assignment_id) REFERENCES assignments(id) ON DELETE CASCADE)''')

    _safe_alter(conn, 'ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0')
    _safe_alter(conn, 'ALTER TABLE assignments ADD COLUMN course_id INTEGER')
    _safe_alter(conn, 'ALTER TABLE assignments ADD COLUMN task_id INTEGER')
    _safe_alter(conn, 'ALTER TABLE tasks ADD COLUMN total_marks INTEGER DEFAULT 100')

    conn.commit()
    conn.close()


def _safe_alter(conn, sql):
    try:
        conn.execute(sql)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def is_valid_email_format(email: str) -> bool:
    """Basic regex check — ensures the email looks like x@y.z"""
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def check_existing_user(username: str, email: str) -> str | None:
    """
    Returns an error message string if username or email is already taken,
    otherwise returns None (meaning all clear).
    """
    conn = get_db_connection()
    existing_username = conn.execute(
        'SELECT id FROM users WHERE username = ?', (username,)
    ).fetchone()
    existing_email = conn.execute(
        'SELECT id FROM users WHERE email = ?', (email,)
    ).fetchone()
    conn.close()

    if existing_username:
        return "This username is already taken. Please choose a different one."
    if existing_email:
        return "An account with this email already exists. Please log in instead."
    return None


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

def register_user(username: str, email: str, password: str, role: str) -> tuple:
    """
    Validates and registers a new user.
    Returns (success: bool, error_message: str | None).
    """
    # 1. Check email format
    if not is_valid_email_format(email):
        return False, "Please enter a valid email address (e.g. name@example.com)."

    # 2. Check for duplicate username / email
    conflict = check_existing_user(username, email)
    if conflict:
        return False, conflict

    # 3. Password length
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."

    # 4. Insert into DB
    conn = get_db_connection()
    try:
        conn.execute(
            'INSERT INTO users (username, email, password, role, is_verified) VALUES (?, ?, ?, ?, 0)',
            (username, email, generate_password_hash(password), role)
        )
        conn.commit()
        return True, None
    except Exception as e:
        print(f"DATABASE REGISTRATION ERROR: {e}")
        return False, "Registration failed due to a server error. Please try again."
    finally:
        conn.close()
