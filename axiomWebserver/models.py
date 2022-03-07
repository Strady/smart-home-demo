from axiomWebserver import login_manager, db
from flask_login import UserMixin
from datetime import datetime, timedelta
import base64
import os


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

we_group_view = db.Table('we_group_view',
                         db.Column('we_id', db.Integer, db.ForeignKey('web_element.id')),
                         db.Column('group_id', db.Integer, db.ForeignKey('group.id')))

we_group_control = db.Table('we_group_control',
                         db.Column('we_id', db.Integer, db.ForeignKey('web_element.id')),
                         db.Column('group_id', db.Integer, db.ForeignKey('group.id')))

class LogEntry(db.Model):
    __tablename__ = 'log_entries'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.Float, nullable=False)
    event = db.Column(db.String, nullable=False)


class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_name = db.Column(db.String(20), unique=True, nullable=False)
    users = db.relationship('User', backref='group', lazy=True)

    def __repr__(self):
        return self.group_name


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)

    # токен для аутентификации
    token = db.Column(db.String(32), index=True, unique=True)
    # срок годности токена
    token_expiration = db.Column(db.DateTime)

    def get_token(self, expires_in=3600):
        """
        Возвращает токен для аутентификации пользователя
        :param expires_in: срок валидности токена
        :return: токен
        """
        now = datetime.utcnow()
        if self.token and self.token_expiration > now + timedelta(seconds=60):
            return self.token
        self.token = base64.b64encode(os.urandom(24)).decode('utf-8')
        self.token_expiration = now + timedelta(seconds=expires_in)
        db.session.add(self)
        return self.token

    def revoke_token(self):
        """
        делает токен невалидным
        """
        self.token_expiration = datetime.utcnow() - timedelta(seconds=1)

    @staticmethod
    def check_token(token):
        """
        проверяет валидность токена
        :param token: токен
        :return: экземляр класса пользователя, для которого токен валидный
        """
        user = User.query.filter_by(token=token).first()
        if user is None or user.token_expiration < datetime.utcnow():
            return None
        return user

    def __repr__(self):
        return '{}:{}:{}'.format(self.id, self.username, self.password)


class WebElement(db.Model):
    __tablename__ = 'web_element'
    id = db.Column(db.Integer, primary_key=True, unique=True, nullable=False)
    addr = db.Column(db.String(20), unique=True, nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('web_element.id'))
    name = db.Column(db.String(40), unique=True, nullable=False)
    type = db.Column(db.String(40), nullable=False)    # например свет
    we_type = db.Column(db.String(40), nullable=False) # например range (слайдер + чекбокс)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    hardware_addr = db.Column(db.String(20))
    viewers = db.relationship('Group', secondary=we_group_view, backref=db.backref('view_allowed', lazy='dynamic'))
    controllers = db.relationship('Group', secondary=we_group_control, backref=db.backref('control_allowed', lazy='dynamic'))
    children = db.relationship('WebElement', backref=db.backref('parent', remote_side=[id]), lazy=True)


    def to_dict(self):
        default_we_states = {'checkbox': {'status': False},
                             'range': {'status': False, 'value': 0},
                             'indicator': {'status': False}}

        dict_we = {'addr': self.addr,
                   'parent': self.parent.addr if self.parent else None,
                   'room': self.room.name,
                   'type': self.type,
                   'name': self.name,
                   'we_type': self.we_type,
                   # 'viewers': [viewer.id for viewer in self.viewers],
                   # 'controllers': [controller.id for controller in self.controllers],
                   'state': default_we_states[self.we_type],
                   'hardware_addr': self.hardware_addr}

        return dict_we

    def __repr__(self):
        return '{} {}'.format(self.addr, self.name)


class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(40), unique=True, nullable=False)
    icon_file = db.Column(db.String(80))
    web_elements = db.relationship('WebElement', backref='room', lazy=True)

    def __repr__(self):
        return self.name


# class ConsumptionRate(db.Model):
#     __tablename__ = 'consumption_rates'
#
#     # Первая тарифная зона
#     rate1 = db.Column(db.Float)
#     beginning1 = db.Column(db.String)
#
#     # Вторая тарифная зона
#     rate2 = db.Column(db.Float)
#     beginning2 = db.Column(db.String)
#
#     # Третья тарифная зона
#     rate3 = db.Column(db.Float)
#     beginning3 = db.Column(db.String)
#
#     # Четвертая тарифная зона
#     rate4 = db.Column(db.Float)
#     beginning4 = db.Column(db.String)




