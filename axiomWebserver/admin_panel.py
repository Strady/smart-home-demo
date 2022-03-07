########################################################################################################################
#                                                    Админ панель                                                      #
########################################################################################################################
from flask_admin.contrib.sqla import ModelView
from flask_admin import AdminIndexView
import werkzeug
import bcrypt
from flask import request, redirect, url_for
from flask_login import current_user
from axiomWebserver import bcrypt, admin
from axiomWebserver.models import db, User, Group, WebElement, Room
from flask import flash
from flask_admin.babel import gettext
import logging

# Set up logger
log = logging.getLogger("flask-admin.sqla")

# def decorated_inaccessible_callback(name, kwargs):
#     return redirect(url_for('login', next=request.url))
#
# def decorated_is_accessible(something):
#     return current_user.is_authenticated and current_user.username == 'admin'
#
# AdminIndexView.is_accessible = decorated_is_accessible
# AdminIndexView.inaccessible_callback = decorated_inaccessible_callback


class UserModelView(ModelView):
    """Класс для отображения и работы с моделью пользователя"""

    column_list = ('username', 'group')

    column_labels = {
        'username': 'Имя',
        'group': 'Группа',
    }

    def update_model(self, form, model):
        """
            Обновляем модель. В форме подменяем пароль на хэш
            :param form: Form instance
            :param model: Model instance
        """
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode()
        form.password.data = hashed_password
        try:
            form.populate_obj(model)
            self._on_model_change(form, model, False)
            self.session.commit()
        except Exception as ex:
            if not self.handle_view_exception(ex):
                flash(gettext('Failed to update record. %(error)s', error=str(ex)), 'error')
                log.exception('Failed to update record.')

            self.session.rollback()

            return False
        else:
            self.after_model_change(form, model, False)

        return True

    def is_form_submitted(self):
        """
            Check if current method is PUT or POST
        """
        print('\x1b[33mform submitted\x1b[0m')
        return request and request.method in ('PUT', 'POST')

    def get_form_data(self):
        """
            If current method is PUT or POST, return concatenated `request.form` with
            `request.files` or `None` otherwise.
        """
        if self.is_form_submitted():
            d = request.form.to_dict()
            hashed_password = bcrypt.generate_password_hash(d['password']).decode()
            d['password'] = hashed_password
            request.form = werkzeug.ImmutableMultiDict(d)
            formdata = request.form
            if request.files:
                formdata = formdata.copy()
                formdata.update(request.files)
            return formdata

        return None

    def create_form(self, obj=None):
        """
            Instantiate model creation form and return it.

            Override to implement custom behavior.
        """
        return self._create_form_class(self.get_form_data(), obj=obj)

    def create_model(self, form):
        """
            Update model from form.

            :param form:
                Form instance
            :param model:
                Model instance
        """
        print('\x1b[33mform: %s\x1b[0m' % form.data['password'])
        print(type(form.data))
        form.data['password'] = 'anotherpass'
        #pdb.set_trace()
        return super().create_model(form)

    def is_accessible(self):
        return current_user.is_authenticated and current_user.username == 'admin'

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login', next=request.url))

class WebElementModelView(ModelView):

    column_hide_backrefs = False

    column_list = ('name', 'addr', 'type', 'we_type', 'room', 'viewers', 'controllers', 'hardware_addr')

    column_labels = {
        'name': 'Название',
        'addr': 'Адрес',
        'type': 'Функция',
        'we_type': 'Тип',
        'room': 'Помещение',
        'viewers': 'Просмотр',
        'controllers': 'Управление',
        'hardware_addr': 'Аппаратный адрес'
    }

class RoomModelView(ModelView):

    def is_visible(self):
        return False

class MyAdminIndexView(AdminIndexView):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def is_accessible(self):
        return current_user.is_authenticated and current_user.username == 'admin'
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login', next=request.url))


admin._set_admin_index_view(MyAdminIndexView(url='/'))
admin.add_view(UserModelView(User, db.session, name='Пользователи', url='/admin/users'))
admin.add_view(ModelView(Group, db.session, name='Группы пользователей', url='/admin/groups'))
admin.add_view(WebElementModelView(WebElement, db.session, name='Элементы интерфейса', url='/admin/web_elements'))
admin.add_view(RoomModelView(Room, db.session, name='Комнаты', url='/admin/rooms'))
admin._menu = admin._menu[1:]




