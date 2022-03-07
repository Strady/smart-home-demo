import redis
from flask import Flask, session, request, g
from flask_socketio import SocketIO
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_admin import Admin
from axiomLib.loggers import create_loggers, debug_colors
from flask_migrate import Migrate


class CustomFlask(Flask):
    jinja_options = Flask.jinja_options.copy()
    jinja_options.update(dict(
        block_start_string='<%',
        block_end_string='%>',
        variable_start_string='<<',
        variable_end_string='>>',
        comment_start_string='<#',
        comment_end_string='#>',
    ))


app = CustomFlask(__name__)
app.config.from_object('axiomWebserver.config')
socketio = SocketIO(app, async_mode='eventlet', )
bcrypt = Bcrypt(app)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
admin = Admin(app, name='axiom', template_mode='bootstrap3', base_template='admin/base.html')
migrate = Migrate(app=app, db=db)

stream_logger, file_logger = create_loggers(logfilename='/var/log/axiom/axiomWebserver.log',
                                            loglevel=20,
                                            logger_id='axiomWebserver')

r = redis.StrictRedis(decode_responses=True)

from axiomWebserver import routes_handlers
from axiomWebserver import api_routes_handlers
from axiomWebserver import events_handlers
from axiomWebserver import admin_panel
from axiomWebserver import models


# @app.before_request
# def print_request():
#     print('\x1b[31mrequest {}\x1b[0m'.format(request), time.time())
#     # print('\x1b[32msession {}\x1b[0m'.format(session))
#
# @app.after_request
# def print_response(response):
#     print('\x1b[33mresponse {}\x1b[0m'.format(response), time.time())
#     return response






