import sqlite3
from flask import current_app
from werkzeug.security import generate_password_hash


def get_db_connection():
    conn = sqlite3.connect(current_app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    # Enforce foreign key constraints (required for the fingerprints table)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _add_column_if_missing(conn, table, column, definition):
    cols = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    """Create all tables, and upgrade databases created by older versions."""
    conn = get_db_connection()

    conn.execute("""CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL)""")

    conn.execute("""CREATE TABLE IF NOT EXISTS courses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    code TEXT UNIQUE NOT NULL,
                    teacher_id INTEGER NOT NULL)""")

    # Links students to courses
    conn.execute("""CREATE TABLE IF NOT EXISTS enrollments (
                    student_id INTEGER,
                    course_id INTEGER,
                    PRIMARY KEY (student_id, course_id))""")

    conn.execute("""CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_id INTEGER,
                    title TEXT,
                    deadline TEXT,
                    total_marks INTEGER DEFAULT 100,
                    FOREIGN KEY(course_id) REFERENCES courses(id))""")

    conn.execute("""CREATE TABLE IF NOT EXISTS assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    course_id INTEGER,
                    task_id INTEGER,
                    filename TEXT NOT NULL,
                    status TEXT DEFAULT 'Pending',
                    marks INTEGER,
                    comments TEXT)""")

    # Winnowing fingerprints used for the global (cross-submission) scan
    conn.execute("""CREATE TABLE IF NOT EXISTS document_fingerprints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    assignment_id INTEGER NOT NULL,
                    hash_value INTEGER NOT NULL,
                    FOREIGN KEY(assignment_id) REFERENCES assignments(id) ON DELETE CASCADE)""")

    # Upgrades for databases created by earlier versions of the app
    _add_column_if_missing(conn, "assignments", "course_id", "INTEGER")
    _add_column_if_missing(conn, "assignments", "task_id", "INTEGER")
    _add_column_if_missing(conn, "tasks", "total_marks", "INTEGER DEFAULT 100")

    conn.commit()
    conn.close()


def register_user(username, email, password, role):
    conn = get_db_connection()
    try:
        hashed_password = generate_password_hash(password)
        conn.execute(
            "INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
            (username, email, hashed_password, role),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()
