# 🛡️ PlagiarismGuard — AI-Powered Academic Plagiarism Detection System

A full-stack web application for detecting plagiarism in student submissions using a **triple-layer detection engine** combining database fingerprinting, peer-to-peer comparison, and live internet scanning.

---

## 🚀 Features

### 👨‍🏫 For Teachers
- Create subjects and generate unique invite codes for students
- Assign tasks with deadlines and total marks
- Grade submissions with scores and feedback
- Run **Global Winnowing Scan** — cross-checks a submission against every document in the entire database
- Run **Subject-wide Scan** — compares all submissions within a subject against each other
- View side-by-side highlighted comparison of flagged documents

### 🎓 For Students
- Join subjects using invite codes
- View assigned tasks with deadlines
- Upload PDF, DOCX, or TXT submissions
- Track grades and teacher feedback

### 🔍 Triple-Layer Plagiarism Detection

| Layer | Method | Purpose |
|-------|--------|---------|
| **Layer 1** | Winnowing Fingerprint Hashing | O(1) cross-database structural matching |
| **Layer 2** | Gestalt Pattern Matching | Peer-to-peer sentence-level comparison |
| **Layer 3** | Tavily Search API + Web Scraping | Live internet plagiarism scanning |

### 🤖 AI-Powered Reports
- Google Gemini generates a professional 2-sentence investigator report for every internet scan
- Sentence-level match breakdown showing exactly which sentences matched which web source
- Per-source similarity percentages with color-coded severity badges

---

## 🗂️ Project Structure

```
plagiarism-checker/
├── app.py                        # Entry point
├── extensions.py                 # Flask app, login manager, Gemini config
├── models.py                     # User class and user_loader
├── text_utils.py                 # Text extraction and highlighting
├── ai_services.py                # Gemini AI report generation
├── check_internet_similarity.py  # Triple-layer internet scanner
├── winnowing_engine.py           # Fingerprint hashing engine
├── database.py                   # DB init and connection helpers
├── utils.py                      # TF-IDF cosine similarity
├── requirements.txt
├── routes/
│   ├── __init__.py               # Blueprint registration
│   ├── auth.py                   # Login, logout, register
│   ├── student.py                # Student portal routes
│   ├── teacher.py                # Teacher portal routes
│   └── analysis.py               # Plagiarism scan routes
└── templates/
    ├── index.html
    ├── student-login.html
    ├── teacher-login.html
    ├── student-portal.html
    ├── teacher-portal.html
    ├── global_results.html
    └── inspect_global.html
```

---

## ⚙️ Setup & Installation

### 1. Clone the repository
```bash
git clone https://github.com/Anamikakathait12/plagiarism-checker.git
cd plagiarism-checker
```

### 2. Create a virtual environment
```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Add your API keys

In `extensions.py`:
```python
genai.configure(api_key="YOUR_GEMINI_API_KEY")
```

In `check_internet_similarity.py`:
```python
TAVILY_API_KEY = "YOUR_TAVILY_API_KEY"
```

### 5. Run the app
```bash
python app.py
```

Visit `http://127.0.0.1:5000` in your browser.

---

## 🔑 API Keys Required

| Service | Purpose | Get it at |
|---------|---------|-----------|
| **Google Gemini** | AI investigator reports | [aistudio.google.com](https://aistudio.google.com) |
| **Tavily** | Internet plagiarism search | [tavily.com](https://tavily.com) |

---

## 🧠 How the Detection Works

### Winnowing (Global Database Scan)
Each uploaded document is converted into a set of cryptographic k-gram hashes using MD5. When a new submission arrives, its hash set is intersected mathematically against every other document in the database. Shared hash count determines similarity percentage.

### Gestalt Pattern Matching (Peer-to-Peer)
Documents are split into sentences and compared using Python's `difflib.SequenceMatcher`. Matching sentences above a 70% threshold are highlighted red in a side-by-side view.

### Internet Scanner (5-Signal Scoring)
For single-file uploads, the system:
1. Detects any source URLs embedded in the document
2. Fires multiple targeted Tavily search queries (beginning, middle, end of text + keyword query)
3. Scores each result using 5 signals: sequence match, keyword overlap, 3-gram fingerprint, 5-gram fingerprint, and sentence-level matching
4. Uses Tavily Extract API to retrieve full page content, bypassing bot-blocking

---

## 📊 Algorithm Comparison

The project includes two standalone research scripts:

```bash
python algorithm_comparison.py      # Compares Jaccard, Cosine, Gestalt, Winnowing
python time_complexity_benchmark.py # Benchmarks O(N²) vs O(N) scalability
```

---

## 🛠️ Tech Stack

- **Backend:** Python, Flask, Flask-Login, SQLite
- **Frontend:** Bootstrap 5, Chart.js, html2pdf.js
- **AI/ML:** Google Gemini 1.5 Flash, Sentence Transformers
- **Plagiarism APIs:** Tavily Search & Extract
- **Document Parsing:** PyPDF2, python-docx
- **Algorithms:** Winnowing (MD5 hashing), Gestalt, TF-IDF Cosine Similarity

---

## 📸 Screenshots

> _Add screenshots of your Teacher Dashboard, Internet Plagiarism Report, and Side-by-Side Comparison here._


---

## 📄 License

This project is for academic purposes. Feel free to fork and build upon it.

---

## 👩‍💻 Author

**Anamika** — Built as part of an academic research project on plagiarism detection algorithms.
