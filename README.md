PlagiarismGuard: A Triple-Layer Academic Integrity SystemPlagiarismGuard is a centralized Learning Management System (LMS) designed to automate academic integrity checks. Unlike traditional scanners, it utilizes a hybrid triple-layer engine to detect unoriginal content from the live web, peer-to-peer collusion, and historical institution-wide databases. 
🚀 Core Features
Layer 1: External Internet Validation: Utilizes the Tavily Search API to bypass search engine bot-protections and retrieve live source material.  
Layer 2: Internal Peer-to-Peer Matrix: Executes a recursive Ratcliff/Obershelp (Gestalt) algorithm to detect $O(N^2)$ collusion within localized student batches. 
Layer 3: Global Historical Fingerprinting: Implements the Winnowing algorithm to create cryptographic $K$-gram fingerprints, enabling high-speed $O(1)$ intersection lookups across all historical submissions.
AI Synthesis: Integrates Google Gemini API to transform raw computational data into professional, two-sentence executive summaries for educators.  

🛠️ System Architecture
The system follows a modular Flask architecture:
app.py: The central routing logic and controller.  
winnowing_engine.py: Handles the cryptographic hashing and fingerprint generation for Layer 3.  
utils.py: Manages similarity calculations and sequence matching for Layer 2.
database.py: Manages the SQLite relational database for student records and fingerprints.  

📊 Performance Benchmarks
The project includes empirical evaluations that justify its algorithmic choices:
Time Complexity: Demonstrates that the Winnowing engine maintains $O(N)$ linear efficiency, significantly outperforming quadratic string matching for large-scale databases.  
<img width="3000" height="1800" alt="updated_time_complexity_graph" src="https://github.com/user-attachments/assets/6d4bf041-348b-4e21-8499-f59dcc942331" />

Accuracy: Validates that the Gestalt algorithm successfully identifies "scrambled" text where Jaccard and Cosine similarity models fail. 
<img width="3600" height="2100" alt="algorithm_comparison_graph" src="https://github.com/user-attachments/assets/26928736-5c42-40b7-85dd-bd38d9e30651" />


💻 Installation & Setup
1. Clone the Repository:
   Bash
   git clone https://github.com/Anamikakathait12/Plagiarism_checker.git
   cd Plagiarism_checker
2. Install Dependencies:
   Ensure you have Python 3.10+
   installed.Bash
   pip install -r requirements.txt
4. Environment Configuration:
   Ensure your API keys for Google Gemini and Tavily are updated in the configuration section of app.py.
5. Run the Application:
   Bash
   python app.py
   Access the portal at http://127.0.0.1:5000.
