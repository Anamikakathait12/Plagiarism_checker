import sqlite3
from werkzeug.security import generate_password_hash

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    # Enforce foreign key constraints (required for the fingerprints table)
    conn.execute('PRAGMA foreign_keys = ON') 
    return conn

def init_db():
    conn = get_db_connection()
    
    # 1. Existing Users Table (Updated with is_verified)
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL,
                    is_verified INTEGER DEFAULT 0)''') # 👈 NEW COLUMN ADDED
    
    # 2. Courses Table
    conn.execute('''CREATE TABLE IF NOT EXISTS courses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    code TEXT UNIQUE NOT NULL,
                    teacher_id INTEGER NOT NULL)''')
    
    # 3. Enrollments Table (Links Students to Courses)
    conn.execute('''CREATE TABLE IF NOT EXISTS enrollments (
                    student_id INTEGER,
                    course_id INTEGER,
                    PRIMARY KEY (student_id, course_id))''')
    
    # 4. Assignments Table with Course Link
    conn.execute('''CREATE TABLE IF NOT EXISTS assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    course_id INTEGER,  
                    filename TEXT NOT NULL,
                    status TEXT DEFAULT 'Pending',
                    marks INTEGER,
                    comments TEXT)''')
    
    # 5. NEW Document Fingerprints Table (For Winnowing Algorithm Integration)
    conn.execute('''CREATE TABLE IF NOT EXISTS document_fingerprints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    assignment_id INTEGER NOT NULL,
                    hash_value INTEGER NOT NULL,
                    FOREIGN KEY(assignment_id) REFERENCES assignments(id) ON DELETE CASCADE)''')
    
    # 👈 SAFELY UPGRADE EXISTING USERS TABLE
    try:
        conn.execute('ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass # Column already exists, so we just ignore the error and move on
        
    # Safely try to add course_id to assignments if the table already exists from an old version
    try:
        conn.execute('ALTER TABLE assignments ADD COLUMN course_id INTEGER')
    except sqlite3.OperationalError:
        pass 
        
    conn.commit()
    conn.close()

def register_user(username, email, password, role):
    conn = get_db_connection()
    try:
        hashed_password = generate_password_hash(password)
        
        # 👈 UPDATED TO INCLUDE is_verified = 0
        conn.execute('INSERT INTO users (username, email, password, role, is_verified) VALUES (?, ?, ?, ?, 0)',
                     (username, email, hashed_password, role))
        conn.commit()
        return True
        
    except Exception as e:
        # 👈 IMPROVED ERROR HANDLING: Now it prints EXACTLY why it failed in the terminal
        print(f"❌ DATABASE REGISTRATION ERROR: {e}")
        return False
    finally:
        conn.close()