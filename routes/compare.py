import os
import difflib
from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required, current_user

from database import get_db_connection
from services.analysis import extract_text, extract_text_from_path, get_highlighted_texts
from services.internet_scan import check_internet_similarity, generate_ai_report
from utils import calculate_similarity

compare_bp = Blueprint('compare', __name__)

UPLOAD_FOLDER = 'uploads'


# ---------------------------------------------------------------------------
# Main comparison route (single file = internet, multiple = peer-to-peer)
# ---------------------------------------------------------------------------

@compare_bp.route('/compare', methods=['POST'])
def compare():
    files     = request.files.getlist("files")
    documents = []
    filenames = []

    for file in files:
        if not file.filename:
            continue
        content = extract_text(file)
        if content.strip():
            documents.append(content)
            filenames.append(file.filename)

    # Decide which template to render into
    is_teacher = current_user.is_authenticated and current_user.role == 'teacher'
    template   = 'teacher-portal.html' if is_teacher else 'index.html'

    # Fetch teacher context if needed
    assignments, courses, tasks = _get_teacher_context() if is_teacher else ([], [], [])

    if not documents:
        return render_template(template, error="Could not read files.",
                               assignments=assignments, courses=courses, tasks=tasks)

    internet_results     = {}
    ai_report            = None
    results              = []
    detailed_comparisons = []

    # --- Single file: internet scan ---
    if len(documents) == 1:
        doc_text = documents[0]
        filename = filenames[0]

        if len(doc_text.split()) > 20:
            urls = check_internet_similarity(doc_text)
            if urls:
                internet_results[filename] = urls
                ai_report = generate_ai_report(doc_text, urls)
            else:
                ai_report = (
                    f"Excellent news! The scan is complete. No internet matches were found "
                    f"for '{filename}'. It appears to be 100% original."
                )
        else:
            ai_report = f"'{filename}' has fewer than 20 words. Please upload a longer document."

    # --- Multiple files: peer-to-peer scan ---
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
                        'text1': h1, 'text2': h2,
                        'score': round(score, 2),
                    })

        results.sort(key=lambda x: x[2], reverse=True)
        detailed_comparisons.sort(key=lambda x: x['score'], reverse=True)

    return render_template(template,
                           results=results,
                           detailed_comparisons=detailed_comparisons,
                           internet_results=internet_results,
                           ai_report=ai_report,
                           assignments=assignments,
                           courses=courses,
                           tasks=tasks)


# ---------------------------------------------------------------------------
# Global Winnowing scan (O(1) hash lookup against entire DB)
# ---------------------------------------------------------------------------

@compare_bp.route('/global_winnow_scan/<int:new_submission_id>')
@login_required
def global_winnow_scan(new_submission_id):
    if current_user.role != 'teacher':
        return redirect(url_for('main.index'))

    conn   = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT hash_value FROM document_fingerprints WHERE assignment_id = ?",
        (new_submission_id,)
    )
    new_hashes = {row['hash_value'] for row in cursor.fetchall()}

    if not new_hashes:
        conn.close()
        return render_template('global_results.html',
                               target_id=new_submission_id, matches=[])

    query = """
        SELECT assignment_id, COUNT(hash_value) as shared_count
        FROM document_fingerprints
        WHERE hash_value IN ({seq}) AND assignment_id != ?
        GROUP BY assignment_id
        HAVING shared_count > 10
        ORDER BY shared_count DESC
    """.format(seq=','.join(['?'] * len(new_hashes)))

    cursor.execute(query, list(new_hashes) + [new_submission_id])
    matches = cursor.fetchall()
    conn.close()

    return render_template('global_results.html',
                           target_id=new_submission_id, matches=matches)


# ---------------------------------------------------------------------------
# Side-by-side inspector for two DB documents
# ---------------------------------------------------------------------------

@compare_bp.route('/inspect_global/<int:target_id>/<int:match_id>')
@login_required
def inspect_global(target_id, match_id):
    if current_user.role != 'teacher':
        return redirect(url_for('main.index'))

    conn = get_db_connection()
    doc1 = conn.execute('SELECT filename FROM assignments WHERE id = ?', (target_id,)).fetchone()
    doc2 = conn.execute('SELECT filename FROM assignments WHERE id = ?', (match_id,)).fetchone()
    conn.close()

    if not doc1 or not doc2:
        return "Error: Documents not found in the database."

    text1 = extract_text_from_path(os.path.join(UPLOAD_FOLDER, doc1['filename']))
    text2 = extract_text_from_path(os.path.join(UPLOAD_FOLDER, doc2['filename']))
    h1, h2 = get_highlighted_texts(text1, text2)
    score  = difflib.SequenceMatcher(None, text1.lower(), text2.lower()).ratio() * 100

    return render_template('inspect_global.html',
                           file1=doc1['filename'], file2=doc2['filename'],
                           text1=h1, text2=h2,
                           score=round(score, 2))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_teacher_context():
    conn        = get_db_connection()
    assignments = conn.execute('''
        SELECT a.*, u.username as student_name, c.name as course_name,
               t.title as task_title, t.total_marks
        FROM assignments a
        JOIN users u ON a.student_id = u.id
        JOIN courses c ON a.course_id = c.id
        LEFT JOIN tasks t ON a.task_id = t.id
        WHERE c.teacher_id = ? ORDER BY a.id DESC
    ''', (current_user.id,)).fetchall()
    courses     = conn.execute('SELECT * FROM courses WHERE teacher_id = ?', (current_user.id,)).fetchall()
    tasks       = conn.execute('''
        SELECT t.*, c.name as course_name FROM tasks t
        JOIN courses c ON t.course_id = c.id
        WHERE c.teacher_id = ?
    ''', (current_user.id,)).fetchall()
    conn.close()
    return assignments, courses, tasks
