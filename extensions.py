import google.generativeai as genai
from flask import Flask
from flask_login import LoginManager

app = Flask(__name__)
app.secret_key = "secret123"

app.config['UPLOAD_FOLDER'] = 'uploads'

# 🔐 Login Manager
login_manager = LoginManager()
login_manager.init_app(app)

# 🚀 Gemini
genai.configure(api_key="AIzaSyAoSqxPA9BxB-TN6YYrcugk7z65T-5nMjM")
