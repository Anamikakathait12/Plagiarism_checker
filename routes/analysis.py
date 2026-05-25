import os
import difflib
import sqlite3
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_from_directory, current_app
from flask_login import login_required, current_user
from database import get_db_connection
from text_utils import extract_text, extract_and_sanitize_text, get_highlighted_texts
from ai_services import generate_ai_report
from utils import calculate_similarity
from check_internet_similarity import check_internet_similarity

analysis_bp = Blueprint('analysis', __name__)


@analysis_bp.route('/download/<filename>')
@login_required
def download(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)


@analysis_bp.route('/debug_internet_results')
def debug_internet_results():
    text   = "Artificial intelligence is the simulation of human intelligence by machines."
    result = check_internet_similarity(text)
    return str(result)


# ─────────────────────────────────────────────
#  MASTER ANALYSIS ROUTE
# ─────────────────────────────────────────────
@analysis_bp.route('/compare', methods=['POST'])
def compare():
    files     = request.files.getlist("files")
    documents = []
    filenames = []

    for file in files:
        if file.filename == '':
            continue
        content = extract_text(file)
        if content.strip():
            documents.append(content)
            filenames.append(file.filename)

    is_teacher = current_user.is_authenticated and current_user.role == 'teacher'
    template   = 'teacher-portal.html' if is_teacher else 'index.html'

    assignments, courses, tasks = [], [], []
    if is_teacher:
        conn = get_db_connection()
        assignments = conn.execute('''
            SELECT a.*, u.username as student_name, c.name as course_name,
                   t.title as task_title, t.total_marks
            FROM assignments a
            JOIN users u   ON a.student_id = u.id
            JOIN courses c ON a.course_id  = c.id
            LEFT JOIN tasks t ON a.task_id = t.id
            WHERE c.teacher_id = ? ORDER BY a.id DESC
        ''', (current_user.id,)).fetchall()
        courses = conn.execute('SELECT * FROM courses WHERE teacher_id = ?', (current_user.id,)).fetchall()
        tasks   = conn.execute('''
            SELECT t.*, c.name as course_name FROM tasks t
            JOIN courses c ON t.course_id = c.id WHERE c.teacher_id = ?
        ''', (current_user.id,)).fetchall()
        conn.close()

    if len(documents) == 0:
        flash("⚠️ Could not read the uploaded file(s). Please try a PDF or DOCX.", "danger")
        return render_template(template,
                               assignments=assignments, courses=courses, tasks=tasks,
                               results=[], internet_results={}, ai_report=None,
                               detailed_comparisons=[])

    internet_results    = {}
    ai_report           = None
    results             = []
    detailed_comparisons = []

    # SCENARIO A: Single file → internet check
    if len(documents) == 1:
        doc_text = documents[0]
        filename = filenames[0]

        if len(doc_text.split()) > 10:
            scan = check_internet_similarity(doc_text)
            internet_results[filename] = scan
            ai_report = generate_ai_report(doc_text, [m['url'] for m in scan.get('matches', [])])
            if not scan['matches']:
                ai_report = f"✅ No internet matches found for '{filename}'."
        else:
            ai_report = f"⚠️ '{filename}' has fewer than 10 words."

    # SCENARIO B: Multiple files → peer-to-peer check
    elif len(documents) > 1:
        similarity_matrix = calculate_similarity(documents)
        for i in range(len(filenames)):
            for j in range(i + 1, len(filenames)):
                score = float(similarity_matrix[i][j] * 100)
                results.append((filenames[i], filenames[j], round(score, 2)))
                if score > 1.0:
                    h1, h2 = get_highlighted_texts(documents[i], documents[j])
                    detailed_comparisons.append({
                        'file1': filenames[i], 'file2': filenames[j],
                        'text1': h1, 'text2': h2, 'score': round(score, 2)
                    })
        results.sort(key=lambda x: x[2], reverse=True)
        detailed_comparisons.sort(key=lambda x: x['score'], reverse=True)

    return render_template(
        template,
        results=results, assignments=assignments, courses=courses, tasks=tasks,
        detailed_comparisons=detailed_comparisons,
        internet_results=internet_results, ai_report=ai_report
    )


# ─────────────────────────────────────────────
#  GLOBAL WINNOWING SCAN
# ─────────────────────────────────────────────
@analysis_bp.route('/global_winnow_scan/<int:new_submission_id>')
@login_required
def global_winnow_scan(new_submission_id):
    if current_user.role != 'teacher':
        return redirect(url_for('auth.index'))

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    target = cursor.execute('''
        SELECT a.*, u.username as student_name, c.name as course_name
        FROM assignments a
        LEFT JOIN users u   ON a.student_id = u.id
        LEFT JOIN courses c ON a.course_id  = c.id
        WHERE a.id = ?
    ''', (new_submission_id,)).fetchone()

    cursor.execute(
        "SELECT hash_value FROM document_fingerprints WHERE assignment_id = ?",
        (new_submission_id,)
    )
    new_hashes = set(row['hash_value'] for row in cursor.fetchall())

    if not new_hashes:
        conn.close()
        return render_template('global_results.html',
                               target_id=new_submission_id, target=target,
                               matches=[], total_scanned=0)

    total_scanned = cursor.execute(
        "SELECT COUNT(DISTINCT assignment_id) FROM document_fingerprints WHERE assignment_id != ?",
        (new_submission_id,)
    ).fetchone()[0]

    placeholders = ','.join(['?'] * len(new_hashes))
    query = f"""
        SELECT df.assignment_id AS matched_doc_id,
               COUNT(df.hash_value) AS shared_count,
               a.filename AS match_filename,
               COALESCE(u.username, 'Unknown') AS match_student,
               COALESCE(c.name, 'No Course')   AS match_course,
               a.course_id AS match_course_id
        FROM document_fingerprints df
        JOIN assignments a  ON df.assignment_id = a.id
        LEFT JOIN users u   ON a.student_id = u.id
        LEFT JOIN courses c ON a.course_id  = c.id
        WHERE df.hash_value IN ({placeholders})
          AND df.assignment_id != ?
        GROUP BY df.assignment_id
        HAVING shared_count > 0
        ORDER BY shared_count DESC
    """
    cursor.execute(query, list(new_hashes) + [new_submission_id])
    raw_matches       = cursor.fetchall()
    target_hash_count = len(new_hashes)

    matches = []
    for row in raw_matches:
        shared = row['shared_count']
        pct    = round((shared / target_hash_count) * 100, 1) if target_hash_count else 0
        severity    = 'HIGH' if pct >= 70 else ('MEDIUM' if pct >= 30 else 'LOW')
        same_course = (row['match_course_id'] == target['course_id']) if target else False
        matches.append({
            'matched_doc_id': row['matched_doc_id'],
            'match_filename':  row['match_filename'],
            'match_student':   row['match_student'],
            'match_course':    row['match_course'],
            'shared_count':    shared,
            'similarity_pct':  pct,
            'severity':        severity,
            'same_course':     same_course,
        })

    conn.close()
    return render_template('global_results.html',
                           target_id=new_submission_id, target=target,
                           matches=matches, total_scanned=total_scanned)


# ─────────────────────────────────────────────
#  SUBJECT-WIDE SCAN
# ─────────────────────────────────────────────
@analysis_bp.route('/scan_subject_assignments/<int:course_id>')
@login_required
def scan_subject_assignments(course_id):
    if current_user.role != 'teacher':
        return redirect(url_for('auth.index'))

    conn           = get_db_connection()
    assignments_db = conn.execute(
        'SELECT * FROM assignments WHERE course_id = ?', (course_id,)
    ).fetchall()
    conn.close()

    documents = []
    filenames = []
    for a in assignments_db:
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], a['filename'])
        if not os.path.exists(filepath):
            fallback = os.path.join(os.getcwd(), 'uploads', a['filename'])
            if os.path.exists(fallback):
                filepath = fallback
        if os.path.exists(filepath):
            text = extract_and_sanitize_text(filepath)
            if text and text.strip():
                documents.append(text)
                filenames.append(a['filename'])

    if len(documents) < 2:
        flash("Need at least 2 assignments within this subject to compare.", "warning")
        return redirect(url_for('teacher.teacher_portal', course_id=course_id))

    similarity_matrix    = calculate_similarity(documents)
    results              = []
    detailed_comparisons = []

    for i in range(len(filenames)):
        for j in range(i + 1, len(filenames)):
            score = float(similarity_matrix[i][j] * 100)
            results.append((filenames[i], filenames[j], round(score, 2)))
            h1, h2 = get_highlighted_texts(documents[i], documents[j])
            detailed_comparisons.append({
                'file1': filenames[i], 'file2': filenames[j],
                'text1': h1, 'text2': h2, 'score': round(score, 2)
            })

    results.sort(key=lambda x: x[2], reverse=True)
    detailed_comparisons.sort(key=lambda x: x['score'], reverse=True)

    conn    = get_db_connection()
    courses = conn.execute('SELECT * FROM courses WHERE teacher_id = ?', (current_user.id,)).fetchall()
    tasks   = conn.execute('''
        SELECT t.*, c.name as course_name FROM tasks t
        JOIN courses c ON t.course_id = c.id WHERE c.teacher_id = ?
    ''', (current_user.id,)).fetchall()
    assignments = conn.execute('''
        SELECT a.*, u.username as student_name, c.name as course_name,
               t.title as task_title, t.total_marks
        FROM assignments a
        JOIN users u   ON a.student_id = u.id
        JOIN courses c ON a.course_id  = c.id
        LEFT JOIN tasks t ON a.task_id = t.id
        WHERE c.teacher_id = ? AND c.id = ?
        ORDER BY a.id DESC
    ''', (current_user.id, course_id)).fetchall()
    conn.close()

    selected_course_name = next((c['name'] for c in courses if str(c['id']) == str(course_id)), None)

    return render_template(
        'teacher-portal.html',
        results=results, detailed_comparisons=detailed_comparisons,
        assignments=assignments, courses=courses, tasks=tasks,
        selected_course_id=course_id, selected_course_name=selected_course_name,
        internet_results=None, ai_report=None
    )


# ─────────────────────────────────────────────
#  GLOBAL SIDE-BY-SIDE INSPECTOR
# ─────────────────────────────────────────────
@analysis_bp.route('/inspect_global/<int:target_id>/<int:match_id>')
@login_required
def inspect_global(target_id, match_id):
    if current_user.role != 'teacher':
        return redirect(url_for('auth.index'))

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    doc1 = conn.execute('SELECT filename FROM assignments WHERE id = ?', (target_id,)).fetchone()
    doc2 = conn.execute('SELECT filename FROM assignments WHERE id = ?', (match_id,)).fetchone()
    conn.close()

    if not doc1 or not doc2:
        return "Error: Documents not found in the database.", 404

    path1 = os.path.join(current_app.config['UPLOAD_FOLDER'], doc1['filename'])
    path2 = os.path.join(current_app.config['UPLOAD_FOLDER'], doc2['filename'])

    if not os.path.exists(path1) or not os.path.exists(path2):
        missing_file  = doc1['filename'] if not os.path.exists(path1) else doc2['filename']
        expected_path = path1 if not os.path.exists(path1) else path2
        return render_template('error_missing_files.html',
                               filename=missing_file, expected_path=expected_path), 400

    try:
        text1 = extract_and_sanitize_text(path1)
        text2 = extract_and_sanitize_text(path2)
    except Exception as e:
        return f"Error reading file content: {str(e)}", 500

    h1, h2 = get_highlighted_texts(text1, text2)
    score  = difflib.SequenceMatcher(None, text1.lower(), text2.lower()).ratio() * 100

    return render_template('inspect_global.html',
                           file1=doc1['filename'], file2=doc2['filename'],
                           text1=h1, text2=h2, score=round(score, 2))
