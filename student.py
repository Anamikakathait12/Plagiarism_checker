import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from database import get_db_connection
from services.analysis import extract_text_from_path
from winnowing_engine import generate_fingerprints

student_bp = Blueprint('student', __name__)

UPLOAD_FOLDER = 'uploads'


# ---------------------------------------------------------------------------
# Portal
# ---------------------------------------------------------------------------

@student_bp.route('/student-portal')
@login_required
def student_portal():
    if current_user.role != 'student':
        return redirect(url_for('main.index'))

    conn = get_db_connection()

    tasks = conn.execute('''
        SELECT t.*, c.name as course_name, u.username as teacher_name
        FROM tasks t
        JOIN courses c ON t.course_id = c.id
        JOIN enrollments e ON c.id = e.course_id
        JOIN users u ON c.teacher_id = u.id
        WHERE e.student_id = ? ORDER BY t.id DESC
    ''', (current_user.id,)).fetchall()

    assignments = conn.execute('''
        SELECT a.*, c.name as course_name, t.title as task_title, t.total_marks
        FROM assignments a
        LEFT JOIN courses c ON a.course_id = c.id
        LEFT JOIN tasks t ON a.task_id = t.id
        WHERE a.student_id = ? ORDER BY a.id DESC
    ''', (current_user.id,)).fetchall()

    enrolled_courses = conn.execute('''
        SELECT c.id, c.name, u.username as teacher_name
        FROM courses c
        JOIN enrollments e ON c.id = e.course_id
        JOIN users u ON c.teacher_id = u.id
        WHERE e.student_id = ?
    ''', (current_user.id,)).fetchall()

    conn.close()
    return render_template('student-portal.html',
                           assignments=assignments,
                           tasks=tasks,
                           enrolled_courses=enrolled_courses)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@student_bp.route('/upload_assignment', methods=['POST'])
@login_required
def upload_assignment():
    if current_user.role != 'student':
        return redirect(url_for('main.index'))

    file      = request.files.get('file')
    course_id = request.form.get('course_id') or None
    task_id   = request.form.get('task_id') or None

    if course_id == 'none': course_id = None
    if task_id   == 'none': task_id   = None

    if not file or not file.filename:
        flash('No file selected.', 'danger')
        return redirect(url_for('student.student_portal'))

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    conn = get_db_connection()
    cursor = conn.execute(
        'INSERT INTO assignments (student_id, course_id, task_id, filename) VALUES (?, ?, ?, ?)',
        (current_user.id, course_id, task_id, filename)
    )
    assignment_id = cursor.lastrowid

    # Generate and store Winnowing fingerprints
    extracted_text = extract_text_from_path(filepath)
    if extracted_text.strip():
        fingerprints = generate_fingerprints(extracted_text)
        conn.executemany(
            'INSERT INTO document_fingerprints (assignment_id, hash_value) VALUES (?, ?)',
            [(assignment_id, h) for h in fingerprints]
        )

    conn.commit()
    conn.close()
    return redirect(url_for('student.student_portal'))


# ---------------------------------------------------------------------------
# Delete assignment
# ---------------------------------------------------------------------------

@student_bp.route('/delete_assignment/<int:assignment_id>', methods=['POST'])
@login_required
def delete_assignment(assignment_id):
    if current_user.role != 'student':
        return redirect(url_for('main.index'))

    conn = get_db_connection()
    assignment = conn.execute(
        'SELECT * FROM assignments WHERE id = ? AND student_id = ?',
        (assignment_id, current_user.id)
    ).fetchone()

    if assignment:
        if assignment['status'] == 'Graded':
            flash('Graded assignments cannot be deleted.', 'warning')
        else:
            conn.execute('DELETE FROM document_fingerprints WHERE assignment_id = ?', (assignment_id,))
            conn.execute('DELETE FROM assignments WHERE id = ?', (assignment_id,))
            conn.commit()

            filepath = os.path.join(UPLOAD_FOLDER, assignment['filename'])
            if os.path.exists(filepath):
                os.remove(filepath)

    conn.close()
    return redirect(url_for('student.student_portal'))


# ---------------------------------------------------------------------------
# Course membership
# ---------------------------------------------------------------------------

@student_bp.route('/join_course', methods=['POST'])
@login_required
def join_course():
    if current_user.role != 'student':
        return redirect(url_for('main.index'))

    code = request.form.get('invite_code', '').strip().upper()
    conn = get_db_connection()
    course = conn.execute('SELECT id FROM courses WHERE code = ?', (code,)).fetchone()

    if course:
        try:
            conn.execute(
                'INSERT INTO enrollments (student_id, course_id) VALUES (?, ?)',
                (current_user.id, course['id'])
            )
            conn.commit()
            flash('Successfully joined the course!', 'success')
        except Exception:
            flash('You are already enrolled in this course.', 'warning')
    else:
        flash('Invalid Invite Code. Please check with your teacher.', 'danger')

    conn.close()
    return redirect(url_for('student.student_portal'))


@student_bp.route('/leave_course/<int:course_id>', methods=['POST'])
@login_required
def leave_course(course_id):
    if current_user.role != 'student':
        return redirect(url_for('main.index'))

    conn = get_db_connection()
    conn.execute(
        'DELETE FROM enrollments WHERE student_id = ? AND course_id = ?',
        (current_user.id, course_id)
    )
    conn.commit()
    conn.close()
    flash('Successfully left the subject.', 'info')
    return redirect(url_for('student.student_portal'))
