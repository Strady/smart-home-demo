from flask import g
from . import bcrypt
from flask_httpauth import HTTPBasicAuth, HTTPTokenAuth
from .models import User
from .APIerrors import error_response
from flask_login import login_user

basic_auth = HTTPBasicAuth()
token_auth = HTTPTokenAuth()

@basic_auth.verify_password
def verify_password(username, password):
    user = User.query.filter_by(username=username).first()
    if not user or not bcrypt.check_password_hash(user.password, password):
        return False
    g.current_user = user
    # login_user(user)
    return True

@basic_auth.error_handler
def basic_auth_error():
    return error_response(401)

@token_auth.verify_token
def verify_token(token):
    g.current_user = User.query.filter_by(token=token).first() if token else None
    return g.current_user is not None

@token_auth.error_handler
def token_auth_error():
    return error_response(401)