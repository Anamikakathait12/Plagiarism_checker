from flask import url_for, current_app
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer


def _get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def send_verification_email(mail, username: str, email: str):
    """
    Generate a signed token and send a verification link to the user's email.
    Returns (success: bool, error_message: str | None).
    """
    try:
        token = _get_serializer().dumps(email, salt='email-confirm')
        link  = url_for('auth.confirm_email', token=token, _external=True)

        msg      = Message('Verify Your Account - Plagiarism Checker', recipients=[email])
        msg.body = f'Hi {username}, please click the link to verify your account: {link}'

        mail.send(msg)
        return True, None

    except Exception as e:
        print(f"Mail Error: {e}")
        return False, str(e)


def verify_token(token: str, max_age: int = 3600):
    """
    Decode a timed verification token.
    Returns (email: str | None, error: str | None).
    """
    try:
        email = _get_serializer().loads(token, salt='email-confirm', max_age=max_age)
        return email, None
    except Exception as e:
        return None, str(e)
