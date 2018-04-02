from rest_framework import serializers

from smsconfirmation.models import PhoneConfirmation, VerifyCreate
from users.models import User
import messagebird
from messagebird.client import Client


class MessagebirdVerificationSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=10)
    event = serializers.CharField(max_length=25)
    method = serializers.CharField(max_length=10)
    status = serializers.CharField(max_length=15)
    reason = serializers.CharField(max_length=50)


class MessagebirdPhoneConfirmationSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=6,
                                 min_length=4)


class PhoneConfirmationSerializer(serializers.ModelSerializer):

    class Meta:
        model = PhoneConfirmation
        fields = ('phone',)

class VerifyCreateSerializer(serializers.ModelSerializer):

    class Meta:
        model = VerifyCreate
        fields = ('recipient',)


class RequestChangePasswordSerializer(serializers.ModelSerializer):
    def validate_phone(self, value):
        if not User.objects.filter(phone=value).exists():
            raise serializers.ValidationError('Phone does not exist')

        return value

    class Meta:
        model = PhoneConfirmation
        fields = ('phone',)


class RequestChangePasswordSerializerUnauth(serializers.ModelSerializer):
    username = serializers.CharField(max_length=15, write_only=True)

    def validate_username(self, value):
        if not User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('Username does not exist')

        return value

    def validate_phone(self, value):
        if not User.objects.filter(phone=value).exists():
            raise serializers.ValidationError('Phone does not exist')

        return value

    def validate(self, data):
        super().validate(data)

        if not User.objects.filter(phone=data['phone'], username__iexact=data['username']).exists():
            raise serializers.ValidationError({'user': 'User does not exist'})

        del data['username']

        return data

    class Meta:
        model = PhoneConfirmation
        fields = ('phone', 'username')


class ChangePasswordSerializer(serializers.ModelSerializer):
    """Serializer for unauthorized user"""
    password1 = serializers.CharField(min_length=6)
    password2 = serializers.CharField(min_length=6)

    def validate(self, data):
        if data['password1'] != data['password2']:
            raise serializers.ValidationError('Passwords do not match')

        return data

    class Meta:
        model = PhoneConfirmation
        fields = ('phone', 'password1', 'password2')
