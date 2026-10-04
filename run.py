import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    print(" 🚀  Server running on http://127.0.0.1:5000")
    app.run(debug=os.getenv("FLASK_DEBUG", "1") == "1", use_reloader=False)
