import os
from extensions import app
from database import init_db, get_db_connection
from routes import register_blueprints

# ── Ensure upload folder exists ───────────────
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ── Init DB + safe migrations ─────────────────
init_db()
conn = get_db_connection()
try:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER,
            title TEXT,
            deadline TEXT,
            total_marks INTEGER DEFAULT 100,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS document_fingerprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            hash_value INTEGER NOT NULL,
            FOREIGN KEY(assignment_id) REFERENCES assignments(id) ON DELETE CASCADE
        )
    ''')
    conn.execute('ALTER TABLE assignments ADD COLUMN task_id INTEGER')
    conn.commit()
except Exception:
    pass

try:
    conn.execute('ALTER TABLE tasks ADD COLUMN total_marks INTEGER DEFAULT 100')
    conn.commit()
except Exception:
    pass
finally:
    conn.close()

# ── Import models (registers user_loader) ─────
import models  # noqa: F401

# ── Register all route blueprints ─────────────
register_blueprints(app)

if __name__ == '__main__':
    print(" 🚀  Server running...")
    app.run(debug=True)
