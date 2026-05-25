from .auth     import auth_bp
from .student  import student_bp
from .teacher  import teacher_bp
from .analysis import analysis_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(analysis_bp)
