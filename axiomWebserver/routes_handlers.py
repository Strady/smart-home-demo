import time

from flask import render_template, request, send_from_directory, redirect, url_for, make_response
from flask_login import login_user, logout_user, current_user, login_required
from axiomWebserver import app, bcrypt, file_logger, stream_logger, debug_colors
from axiomWebserver.forms import RegistrationForm, LoginForm
from axiomWebserver.models import db, User, Group
from axiomLib.loggers import create_loggers
from flask_socketio import join_room
from datetime import timedelta as td

# r = redis.StrictRedis(port=6379, charset='utf-8', decode_responses=True)
# stream_logger, file_logger = create_loggers(logfilename='/var/log/axiom/axiomWebserver.log', loglevel=20, logger_id='axiomWebserver')


@app.route('/')
@login_required
def index():
    if not current_user.is_authenticated:
        return redirect(redirect(url_for(login)))
    return render_template('index.html')


# DEPRECATED
# @app.route('/register', methods=['GET', 'POST'])
# def register():
#     form = RegistrationForm()
#     if form.validate_on_submit():
#         hashed_password = bcrypt.generate_password_hash(form.password.data).decode()
#         print('user created for {}'.format(form.username.data))
#         print('hashed password {}'.format(hashed_password))
#         user = User(username=form.username.data, password=hashed_password, group_id=Group.query.first().id)
#         print('user', user)
#         print('adding user', db.session.add(user))
#         print('commiting', db.session.commit())
#         # return redirect(url_for(index))
#     return render_template('register.html', title='Register', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Авторизация пользователя (с использованием http)
    :return: http response
    """
    form = LoginForm()

    if request.method == 'POST':
        # print('got login request', time.time())
        if form.validate_on_submit():
            # print('\x1b[35mform validated\x1b[0m', time.time())
            user = User.query.filter_by(username=form.username.data).first()
            # print('user loaded from db', time.time())
            if user and bcrypt.check_password_hash(user.password, form.password.data):
                # print('password has been checked', time.time())
                login_user(user, remember=True, force=True, duration=td(days=365))
                next_page = request.args.get('next')
                # print('return redirect', time.time())
                return redirect(next_page) if next_page else redirect(url_for('index'))
    # print('\x1b[35mform is not validated\x1b[0m')
    response = make_response(render_template('login.html', title='Login', form=form))
    response.status_code = 401
    return response


@app.route('/logout', methods=['GET'])
def logout():
    if current_user.is_authenticated:
        logout_user()
    return redirect(url_for('login'))


# @app.route('/test')
# @login_required
# def test():
#     response = render_template('testing-index.html')
#     # print(dir(response))
#     return response


@app.route('/<path:path>')
def send_static(path):
    return send_from_directory('static/', path)


@app.route('/mounting_service')
def mounting_service():
    # with open('elements_list.json') as f:
    #     elements_list = json.load(f)
    # response = app.response_class(
    #     response=json.dumps(elements_list),
    #     status=200,
    #     mimetype='application/json',
    # )
    # return response
    return render_template('mount.html')


# @app.route('/testing')
# def print_output():
#     # print('\x1b[34moutput: %s\x1b[0m' % output)
#     print(request.args)
#     return str(request.args)
