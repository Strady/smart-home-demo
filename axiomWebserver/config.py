import os

SECRET_KEY = os.urandom(24)
SQLALCHEMY_DATABASE_URI = 'sqlite:///site.db'
FLASK_ADMIN_SWATCH = 'slate'
WTF_CSRF_ENABLED = False
SQLALCHEMY_TRACK_MODIFICATIONS = False
AXIOM_ROOT_PATH = '/home/pi/office/axiomProject/'
CONSUMPTION_DB_NAME = 'consumption.db'
AXIOM_SETTINGS_PATH = '/etc/axiom/settings.json'
JOBS_DB_NAME = 'jobs.sqlite'