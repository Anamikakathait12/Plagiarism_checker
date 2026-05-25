import random
import string
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_db_connection

teacher_bp = Blueprint('teacher', __name__)


def _generate_invite_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def _fetch_teacher_dashboard(teacher_id, selected_course_id=None):
    """Return (courses, tasks, assignments, selected_course_name) for the teacher portal."""
    conn = get_db_connection()

    courses = conn.execute('SELECT * FROM courses WHERE teacher_id = ?', (teacher_id,)).fetchall()
    tasks   = conn.execute('''
        SELECT t.*, c.name as course_name FROM tasks t
        JOIN courses c ON t.course_id = c.id
        WHERE c.teacher_id = ? ORDER BY t.id DESC
    ''', (teacher_id,)).fetchall()

    selected_course_name = None
    if selected_course_id:
        row = conn.execute('SELECT name FROM courses WHERE id = ?', (selected_course_id,)).fetchone()
        if row:
            selected_course_name = row['name']
        assignments = conn.execute('''
            SELECT a.*, u.username as student_name, c.name as course_name,
                   t.title as task_title, t.total_marks
            FROM assignments a
            JOIN users u   ON a.student_id = u.id
            JOIN courses c ON a.course_id  = c.id
            LEFT JOIN tasks t ON a.task_id = t.id
            WHERE c.teacher_id = ? AND c.id = ?
            ORDER BY a.id DESC
        ''', (teacher_id, selected_course_id)).fetchall()
    else:
        assignments = conn.execute('''
            SELECT a.*, u.username as student_name, c.name as course_name,
                   t.title as task_title, t.total_marks
            FROM assignments a
            JOIN users u   ON a.student_id = u.id
            JOIN courses c ON a.course_id  = c.id
            LEFT JOIN tasks t ON a.task_id = t.id
            WHERE c.teacher_id = ?
            ORDER BY a.id DESC
        ''', (teacher_id,)).fetchall()

    conn.close()
    return courses, tasks, assignments, selected_course_name


@teacher_bp.route('/teacher-portal')
@login_required
def teacher_portal():
    if current_user.role != 'teacher':
        return redirect(url_for('auth.index'))

    selected_course_id = request.args.get('course_id')
    courses, tasks, assignments, selected_course_name = _fetch_teacher_dashboard(
        current_user.id, selected_course_id
    )

    return render_template(
        'teacher-portal.html',
        assignments=assignments, courses=courses, tasks=tasks,
        selected_course_id=selected_course_id,
        selected_course_name=selected_course_name,
        results=None, internet_results=None, ai_report=None
    )


@teacher_bp.route('/grade/<int:assignment_id>', methods=['POST'])
@login_required
def grade(assignment_id):
    if current_user.role != 'teacher':
        return redirect(url_for('auth.index'))

    marks    = request.form.get('marks')
    comments = request.form.get('comments')
    conn = get_db_connection()
    conn.execute(
        'UPDATE assignments SET marks = ?, comments = ?, status = ? WHERE id = ?',
        (marks, comments, 'Graded', assignment_id)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('teacher.teacher_portal'))


@teacher_bp.route('/create_course', methods=['POST'])
@login_required
def create_course():
    if current_user.role != 'teacher':
        return redirect(url_for('auth.index'))

    course_name = request.form.get('course_name')
    code = _generate_invite_code()
    conn = get_db_connection()
    conn.execute('INSERT INTO courses (name, code, teacher_id) VALUES (?, ?, ?)', (course_name, code, current_user.id))
    conn.commit()
    conn.close()
    return redirect(url_for('teacher.teacher_portal'))


@teacher_bp.route('/create_task', methods=['POST'])
@login_required
def create_task():
    if current_user.role != 'teacher':
        return redirect(url_for('auth.index'))

    course_id   = request.form.get('course_id')
    title       = request.form.get('title')
    deadline    = request.form.get('deadline')
    total_marks = request.form.get('total_marks', 100)
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO tasks (course_id, title, deadline, total_marks) VALUES (?, ?, ?, ?)',
        (course_id, title, deadline, total_marks)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('teacher.teacher_portal'))


@teacher_bp.route('/delete_task/<int:task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    if current_user.role != 'teacher':
        return redirect(url_for('auth.index'))

    import os
    from flask import current_app

    conn = get_db_connection()
    task = conn.execute('''
        SELECT t.id FROM tasks t JOIN courses c ON t.course_id = c.id
        WHERE t.id = ? AND c.teacher_id = ?
    ''', (task_id, current_user.id)).fetchone()

    if task:
        submissions = conn.execute(
            'SELECT id, filename FROM assignments WHERE task_id = ?', (task_id,)
        ).fetchall()
        for sub in submissions:
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], sub['filename'])
            if os.path.exists(file_path):
                os.remove(file_path)
            conn.execute('DELETE FROM document_fingerprints WHERE assignment_id = ?', (sub['id'],))
        conn.execute('DELETE FROM assignments WHERE task_id = ?', (task_id,))
        conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        conn.commit()

    conn.close()
    return redirect(url_for('teacher.teacher_portal'))
