import logging
import random
import string

from django.db import models
from django.utils import timezone

from django.db.models.signals import post_save
from django.dispatch import receiver

from users.models import User


logger = logging.getLogger(__name__)

CODE_CONFIRMATION_LEN = 6
PHONE_CONFIRMATION_LIFE_TIME_IN_SECONDS = 5 * 60


def get_phone_confirmation_code():
    return ''.join([random.choice(string.digits) for _ in range(CODE_CONFIRMATION_LEN)])


class PhoneConfirmationManager(models.Manager):

    def get_actual(self, phone, **kwargs):
        qs = self.get_queryset().filter(phone=phone, **kwargs)
        qs = qs.order_by('-created_at')

        return qs.first()

    def verified(self, request):
        recipient = request.POST.get('phone', "")
        if not recipient:
            return HttpResponse("No mobile number", status=403)

        client = messagebird.Client('CS1FgyAO8o51GT4KesklVy4Zq')
        verified = client.verify_create(recipient)
        return verified

class PhoneConfirmation(models.Model):
    REQUEST_PHONE = 1
    REQUEST_PASSWORD = 2
    REQUEST_CHANGE_PHONE = 3

    REQUEST_TYPES = (
        (REQUEST_PHONE, 'Phone confirmation'),
        (REQUEST_PASSWORD, 'Reset password'),
    )

    objects = PhoneConfirmationManager()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    phone = models.CharField(max_length=20)

    code = models.CharField(max_length=CODE_CONFIRMATION_LEN,
                            default=get_phone_confirmation_code)

    is_delivered = models.BooleanField(default=False)
    is_confirmed = models.BooleanField(default=False)

    request_type = models.IntegerField(choices=REQUEST_TYPES)

    @classmethod
    def check_phone(cls, phone: str):
        confirmation = PhoneConfirmation.objects.get_actual(phone)

        if not confirmation:
            logger.info('Confirmation request for {} was not found'.format(phone))
            return False, 'Confirmation code not found'

        if not confirmation.is_actual():
            logger.info('Confirmation code is expired {}'.format(confirmation.pk))
            return False, 'Confirmation code is expired'

        return True, None

    def __str__(self):
        return '{} {} {} {}'.format(self.phone, self.code, self.created_at, self.is_confirmed)

    def is_actual(self):
        delta = (timezone.now() - self.created_at).total_seconds()

        return delta < PHONE_CONFIRMATION_LIFE_TIME_IN_SECONDS

    class Meta:
        ordering = ('-created_at',)

class VerifyCreate(models.Model):
    REQUEST_PHONE = 1
    REQUEST_PASSWORD = 2
    REQUEST_CHANGE_PHONE = 3

    REQUEST_TYPES = (
        (REQUEST_PHONE, 'Phone confirmation'),
        (REQUEST_PASSWORD, 'Reset password'),
    )

    objects = PhoneConfirmationManager()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    recipient = models.CharField(max_length=20)

    code = models.CharField(max_length=CODE_CONFIRMATION_LEN,
                            default=get_phone_confirmation_code)

    @classmethod
    def check_phone(cls, phone: str):
        confirmation = verifycreate.objects.get_actual(phone)

    def __str__(self):
        return '{} {} {} {}'.format(self.phone, self.code, self.created_at, self.is_confirmed)

    def is_actual(self):
        delta = (timezone.now() - self.created_at).total_seconds()

        return delta < PHONE_CONFIRMATION_LIFE_TIME_IN_SECONDS

# @receiver(post_save, sender=PhoneConfirmation)
# def post_confirmation(sender, instance, *args, **kwargs):
#     from blast.celery import send_sms

    # send_sms.delay(instance.phone, instance.code)
