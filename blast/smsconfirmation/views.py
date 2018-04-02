# Create your views here.
import logging

import json
import requests
from rest_framework import mixins, views
from rest_framework import status, permissions
from rest_framework.response import Response
from django.http import HttpResponse
from django.core.cache import cache

from smsconfirmation.models import PhoneConfirmation
from smsconfirmation.serializers import (PhoneConfirmationSerializer, ChangePasswordSerializer,
                                         MessagebirdVerificationSerializer, MessagebirdPhoneConfirmationSerializer, VerifyCreateSerializer,
                                         RequestChangePasswordSerializer, RequestChangePasswordSerializerUnauth)
from users.models import User

from smsconfirmation.tasks import (send_verification_request,
                                   send_code_confirmation_request)

logger = logging.getLogger(__name__)
import messagebird
from messagebird import client, verify
from messagebird.client import Client
#from . import verify_create
client = messagebird.Client('CS1FgyAO8o51GT4KesklVy4Zq')



class PhoneConfirmBase(mixins.CreateModelMixin,
                       mixins.UpdateModelMixin,
                       views.APIView):
    """
    Base class for requests that can be confirmed by phone.

    serializer_class - class for serializing and validating request data.
    queryset - PhoneConfirmation queryset.
    """
    permission_classes = (permissions.AllowAny,)

    def on_code_confirmed(self, request, confirmation):
        raise NotImplemented()

    def post(self, request, *args, **kwargs):
        return self.create(request)

    # TODO: Make tests
    def update(self, request, *args, **kwargs):
        # FIXME: Replace by get_serializer?
        serializer = self.serializer_class(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        phone = request.data.get('phone')
        if not phone:
            return Response({'phone': 'Invalid phone number'}, status=status.HTTP_400_BAD_REQUEST)

        is_confirmed, message = PhoneConfirmation.check_phone(phone)

        if not is_confirmed:
            return Response({'code': [message]}, status=status.HTTP_400_BAD_REQUEST)

        error = self.on_code_confirmed(request, phone)
        if error:
            return Response(error, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.data, status=status.HTTP_200_OK)


class PhoneConfirmView(PhoneConfirmBase):
    serializer_class = PhoneConfirmationSerializer

    REQUEST_TYPE = PhoneConfirmation.REQUEST_PHONE

    def get_serializer(self, data):
        if self.request.method == 'POST':
            return PhoneConfirmationSerializer(data=data)

    def post(self, request, *args, **kwargs):
        """
        Requests new phone confirmation code by SMS.
        This method should be called before signing.

        ---
        serializer: smsconfirmation.serializers.PhoneConfirmationSerializer
        parameters:
            - name: phone
              description: phone number with country code (+79131234567 e.g)
        """


        recipient = request.POST.get('phone', "")
        if not recipient:
            return HttpResponse("No mobile number", status=403)

        client = messagebird.Client('CS1FgyAO8o51GT4KesklVy4Zq')
        verified = client.verify_create(recipient)

        return HttpResponse("verified %s sent" % verified.id, status=201)


    def perform_create(self, serializer):
        serializer.save(request_type=self.REQUEST_TYPE)
        send_verification_request.delay(phone=serializer.data['phone'])

    def on_code_confirmed(self, request, confirmation: PhoneConfirmation):
        try:
            user = User.objects.get(phone=request.data.get('phone'))
            user.is_verified = True
            user.save()
        except User.DoesNotExist:
            return {'phone': 'User with given phone does not exist'}

class VerifyCreateView(PhoneConfirmBase):
    serializer_class = VerifyCreateSerializer


    def post(self, request, *args, **kwargs):
        """
        Requests new phone confirmation code by SMS.
        This method should be called before signing.

        ---
        serializer: smsconfirmation.serializers.PhoneConfirmationSerializer
        parameters:
            - name: recipient
              description: phone number with country code (+79131234567 e.g)
        """


        recipient = request.POST.get('recipient', "")
        if not recipient:
            return HttpResponse("No mobile number", status=403)

        client = messagebird.Client('CS1FgyAO8o51GT4KesklVy4Zq')
        verify = client.verify_create(recipient)

        return HttpResponse("verify %s sent" % verify.id, status=201)

class ResetPasswordView(PhoneConfirmBase):

    serializer_class = ChangePasswordSerializer

    REQUEST_TYPE = PhoneConfirmation.REQUEST_PASSWORD

    def get_serializer(self, data):
        if self.request.method == 'POST':
            if self.request.user.is_authenticated():
                return RequestChangePasswordSerializer(data=data)
            else:
                return RequestChangePasswordSerializerUnauth(data=data)
        else:
            return ChangePasswordSerializer(data=data)

    def perform_create(self, serializer):
        serializer.save(request_type=self.REQUEST_TYPE)

    def post(self, request, *args, **kwargs):
        """
        Initial password changing and send confirmation code to user phone.

        ---
        serializer: smsconfirmation.serializers.RequestChangePasswordSerializer
        parameters:
            - name: phone
              description: phone number (+79528048941 for e.g)
            - name: username
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(request_type=PhoneConfirmation.REQUEST_PASSWORD)

        send_verification_request.delay(serializer.data['phone'])

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def patch(self, request, *args, **kwargs):
        """
        Method for changing password.
        You must request confirmation code before changing your password.

        ---
        serializer: smsconfirmation.serializers.ChangePasswordSerializer
        parameters:
            - name: phone
              description: confirmed phone number
            - name: password1
              description: New password. Must be great than 5.
            - name: password2
              description: Password confirmation. Must be equal to password1.
        """
        return self.update(request, *args, **kwargs)

    def on_code_confirmed(self, request, phone):
        try:
            user = User.objects.get(phone=phone)

            user.set_password(request.data['password1'])
            user.save()
        except User.DoesNotExist:
            return {'phone': 'User with given phone does not exist'}


class MessagebirdPhoneConfirmationView(views.APIView):
    queryset = PhoneConfirmation.objects.all()
    serializer_class = PhoneConfirmation
    def post(self, request):
        """
        Requests new phone verification code

        ---
        serializer: smsconfirmation.serializers.PhoneConfirmationSerializer
        """
        #serializer = PhoneConfirmationSerializer(data=request.data)
        #serializer.is_valid(raise_exception=True)
        #serializer.save(request_type=PhoneConfirmation.REQUEST_PHONE)

        recipient = request.POST.get('phone', "")
        if not recipient:
            return HttpResponse("No mobile number", status=403)

        client = messagebird.Client('CS1FgyAO8o51GT4KesklVy4Zq')
        verify = client.verify_create(recipient)

        return HttpResponse("verify %s sent" % verify.id, status=201)

    def put(self, request, verified=None):
        """

        ---
        serializer: smsconfirmation.serializers.MessagebirdPhoneConfirmationSerializer
        """
    #    recipient = request.POST.get('phone', "")
    #    verified = client.verify_create(recipient)
        token = request.POST.get(verified)

        verify_code = client.verify_verify(id, token=token)
        return HttpResponse("verify_code %s verified" % verify.id, status=201)
