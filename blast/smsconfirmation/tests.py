from django.core.urlresolvers import reverse_lazy
from rest_framework import status

from core.tests import BaseTestCase, BaseTestCaseUnauth
from smsconfirmation.models import PhoneConfirmation
from users.models import User


class TestPhoneConfirmation(BaseTestCase):

    url = reverse_lazy('phone-confirmation')
    phone = '+79991234567'

    def test_get_confirmation_code(self):
        pass
        # response = self.client.post(self.url, data={'phone': self.phone})
        #
        # confirm = PhoneConfirmation.objects.get(phone=self.phone)
        # self.user.refresh_from_db()
        #
        # self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # self.assertFalse(confirm.is_confirmed)


class TestResetPassword(BaseTestCaseUnauth):
    url = reverse_lazy('reset-password')

    def setUp(self):
        super().setUp()

        self.password_request = PhoneConfirmation.objects.create(phone=self.user.phone,
                                                                 is_confirmed=True,
                                                                 request_type=PhoneConfirmation.REQUEST_PASSWORD)

    def test_phone_does_not_exist(self):
        data = {
            'phone': 'abcd'
        }

        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNotNone(response.data.get('phone'))

    def test_code_not_found(self):
        data = {
            'phone': '1234567',
            'password1': 'newpass',
            'password2': 'newpass'
        }

        response = self.patch_json(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNotNone(response.data.get('code'))
        self.assertIsInstance(response.data.get('code'), list)

    def test_wrong_password_len(self):
        data = {
            'code': self.password_request.code,
            'phone': self.user.phone,
            'password1': 'new',
            'password2': 'new'
        }

        response = self.patch_json(self.url, data)

        self.user.refresh_from_db()
        self.password_request.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(self.user.check_password(self.password))

    def test_password_do_not_match(self):
        data = {
            'code': self.password_request.code,
            'phone': self.user.phone,
            'password1': 'old_password',
            'password2': 'new_password'
        }

        response = self.patch_json(self.url, data)

        self.user.refresh_from_db()
        self.password_request.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(self.user.check_password(self.password))

    def test_change_password_by_phone(self):
        new_password = 'new_password'
        data = {
            'phone': self.user.phone,
            'password1': new_password,
            'password2': new_password,
        }

        response = self.patch_json(self.url, data)

        self.user.refresh_from_db()
        self.password_request.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(self.password_request.is_confirmed)
        self.assertTrue(self.user.check_password(new_password))
        self.assertIsNone(response.data.get('errors'))

    def test_wrong_username(self):
        data = {
            'username': self.username + '1',
            'phone': self.user.phone
        }

        response = self.client.post(self.url, data=data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNotNone(response.data.get('username'))

        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, self.phone)

    def test_username_case_insensitive(self):
        data = {
            'username': self.user.username.upper(),
            'phone': self.user.phone,
        }
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # TODO: complete asserts
        # confirm = PhoneConfirmation.objects.get(phone=self.phone)


    def test_validate_user(self):
        other_username = self.username + '2'
        other_phone = self.phone + '2'

        User.objects.create_user(username=other_username, phone=other_phone, password=self.password)

        data = {
            'username': self.username,
            'phone': other_phone
        }

        response = self.client.post(self.url, data=data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNotNone(response.data.get('user'))


class TestSinchVerification(BaseTestCase):
    url = reverse_lazy('sinch-phone-confirmation')

    def test_sinch_request_confirmation(self):
        pass
        # self.client.post(self.url, {'phone': self.phone})
        #
        # confirm = PhoneConfirmation.objects.get(phone=self.phone)
        #
        # self.assertEqual(PhoneConfirmation.objects.count(), 1)
        # self.assertEqual(confirm.is_confirmed, False)

    def test_sinch_confirm_phone(self):
        pass
        # self.client.post(self.url, {'phone': self.phone})
        #
        # confirm = PhoneConfirmation.objects.get(phone=self.phone)
        #
        # self.client.put(self.url, {'phone': self.phone, 'code': '1111'})
