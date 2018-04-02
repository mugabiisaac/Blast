import json
import logging
import uuid


from io import BytesIO

import redis
from PIL import Image
from unittest import mock
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from django.core.urlresolvers import reverse_lazy

from countries.models import Country
from users.models import User


logger = logging.getLogger(__name__)


def sinch_request_mok(resource, data, method):
    logger.info('Send sinch notification %s %s %s', resource, data, method)


def create_file(name, content_file=True):
    image = Image.new('RGBA', size=(50, 50))
    file = BytesIO(image.tostring())
    file.name = name
    file.seek(0)

    if content_file:
        return ContentFile(file.read(), name=name)
    else:
        return SimpleUploadedFile(name, file.read(), content_type='image/png')


@mock.patch('core.smsconfirmation.tasks.sinch_request_mok', sinch_request_mok)
@override_settings(CELERY_ALWAYS_EAGER=True)
class BaseTestCaseUnauth(TestCase):
    phone = '8913123123'
    password = '111111'
    username = 'username'

    def generate_user(self, username=None, is_private=False):
        if not username:
            username = str(uuid.uuid4())[:15]

        return User.objects.create_user(username=username, password=self.password,
                                        country=self.country, phone=uuid.uuid4(),
                                        is_private=is_private)

    def login(self, username,):
        data = {
            'username': username,
            'password': self.password
        }

        response = self.client.post(reverse_lazy('get-auth-token'), data)
        self.auth_token = response.data.get('token')
        self.headers = {
            'HTTP_AUTHORIZATION': 'Token {0}'.format(self.auth_token)
        }
        self.client.defaults.update(self.headers)

    def setUp(self):
        self.r = redis.StrictRedis(host='localhost', port=6379, db=0)
        self.r.flushdb()

        data = {
            'phone': self.phone,
            'username': self.username,
            'password': self.password,
        }

        self.country = Country.objects.create(name='Russia', code='+7')

        self.anonymous = User.objects.create(username='Anonymous', password=uuid.uuid4(),
                                             phone='+', country=self.country)

        self.user = User.objects.create_user(**data)

        data = {
            'username': self.username,
            'password': self.password
        }

        response = self.client.post(reverse_lazy('get-auth-token'), data)
        self.auth_token = response.data.get('token')

    def clear_cache(self):
        self.r.flushdb()

    def map_result_to_pk(self, results):
        if 'results' in results:
            results = results['results']

        return {it['id']: it for it in results}

    def put_json(self, url, data=''):
        if type(data) is dict:
            data = json.dumps(data)

        return self.client.put(url, data=data, content_type='application/json')

    def post_json(self, url, data=''):

        if type(data) is dict:
            data = json.dumps(data)

        return self.client.post(url, data=data, content_type='application/json')

    def patch_json(self, url, data=''):
        return self.client.patch(url, json.dumps(data),
                                 content_type='application/json')


class BaseTestCase(BaseTestCaseUnauth):
    def setUp(self):
        super().setUp()

        self.headers = {
            'HTTP_AUTHORIZATION': 'Token {0}'.format(self.auth_token)
        }
        self.client.defaults.update(self.headers)