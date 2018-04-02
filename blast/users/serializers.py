from rest_framework import serializers

from smsconfirmation.models import PhoneConfirmation
from users.models import User, UserSettings


# TODO: Rename
class CheckUsernameAndPassword(serializers.Serializer):
    phone = serializers.CharField(max_length=20, required=False)
    username = serializers.CharField(max_length=15, required=False)

    def validate_phone(self, value):
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError('This phone is taken')

        return value

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('This username is taken')

        return value


class RegisterUserSerializer(serializers.ModelSerializer):
    """
    Serializer for registration method.
    It allows set up very limited field set.
    """
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        if not value or len(value) < 6:
            raise serializers.ValidationError('Your password must be at least 6 characters')
        return value

    def validate_username(self, value):
        if not value or len(value) > 15:
            raise serializers.ValidationError('Your username must be 15 characters or less')

        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('This username is taken')

        return value

    def create(self, validated_data):
        is_confirmed, message = PhoneConfirmation.check_phone(validated_data['phone'])
        if not is_confirmed:
            raise serializers.ValidationError({'phone': [message]})

        avatar = validated_data.get('avatar')
        instance = User.objects.create_user(phone=validated_data['phone'],
                                            password=validated_data['password'],
                                            username=validated_data['username'],
                                            country=validated_data['country'],
                                            commit=False)
        instance.set_password(validated_data['password'])

        if avatar:
            instance.avatar.save(name=avatar.name, content=avatar)

        instance.save()
        return instance

    class Meta:
        model = User
        fields = ('phone', 'username', 'password', 'country', 'avatar',)


class ProfileUserSerializer(serializers.ModelSerializer):
    """
    Serializer for updating user model
    """

    class Meta:
        model = User
        fields = ('fullname', 'avatar', 'bio', 'website', 'gender', 'birthday',
                  'save_original_content', 'is_private', 'save_original_content',
                  'is_safe_mode')


class ProfilePublicSerializer(serializers.ModelSerializer):
    """
    Special serializer for logged user
    """
    followers = serializers.ReadOnlyField(source='followers_count',
                                          help_text='Total count of followers')
    blasts = serializers.ReadOnlyField(source='blasts_count',
                                       help_text='Total count of blasts')
    following = serializers.ReadOnlyField(source='following_count',
                                          help_text='Total count of followees')

    class Meta:
        model = User
        # TODO: Don't use exclude
        exclude = ('password', 'user_permissions', 'groups', 'friends',
                   'blocked', 'pinned_tags', 'pinned_posts', 'hidden_posts')


class PublicUserSerializer(serializers.ModelSerializer):
    """
    Serializer for safe methods.
    It serialize only safe public methods, like username, avatar etc.
    """
    followers = serializers.ReadOnlyField(source='followers_count')
    following = serializers.ReadOnlyField(source='following_count')
    blasts = serializers.ReadOnlyField(source='blasts_count')

    class Meta:
        model = User
        fields = ('id', 'username', 'created_at', 'fullname', 'avatar',
                  'is_private', 'bio', 'website', 'followers', 'blasts',
                  'following')


class NotificationSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSettings
        # FIXME: Don't use exclude
        exclude = ('user',)


class ChangePasswordSerializer(serializers.ModelSerializer):
    old_password = serializers.CharField(min_length=6, write_only=True)
    password1 = serializers.CharField(min_length=6, write_only=True)
    password2 = serializers.CharField(min_length=6, write_only=True)

    def validate_old_password(self, value):
        if not self.instance.check_password(value):
            raise serializers.ValidationError('Wrong old password')

    def validate(self, data):
        if data['password1'] != data['password2']:
            raise serializers.ValidationError({'password1': ['Passwords do not match']})

        return data

    def save(self, **kwargs):
        self.instance.set_password(self.validated_data['password1'])
        super().save(**kwargs)

    class Meta:
        model = User
        fields = ('password1', 'password2', 'old_password')


class ChangePhoneSerializer(serializers.ModelSerializer):
    password = serializers.CharField(min_length=6, write_only=True)
    current_phone = serializers.CharField(write_only=True)
    new_phone = serializers.CharField(write_only=True)

    def validate_password(self, value):
        if not self.instance.check_password(value):
            raise serializers.ValidationError('Wrong password')

        return value

    def validate_current_phone(self, value):
        if self.instance.phone != value:
            raise serializers.ValidationError('Wrong current phone number')

        return value

    def validate(self, attrs: dict):
        super().validate(attrs)

        if 'new_phone' not in attrs:
            raise serializers.ValidationError({'new_phone': 'Wrong new phone'})

        if User.objects.filter(phone=attrs['new_phone']).exists():
            raise serializers.ValidationError({'new_phone': 'This phone taken'})

        is_confirmed, message = PhoneConfirmation.check_phone(attrs['new_phone'])
        if not is_confirmed:
            raise serializers.ValidationError({'code': [message]})

        del attrs['password']

        return attrs

    def save(self, **kwargs):
        self.instance.phone = self.validated_data['new_phone']
        super().save(**kwargs)

    class Meta:
        model = User
        fields = ('password', 'current_phone', 'new_phone',)

# FIXME: Looks like OwnerSerializer
class UsernameSerializer(serializers.ModelSerializer):
    avatar = serializers.SerializerMethodField()

    def get_avatar(self, obj):
        request = self.context['request']
        if obj.avatar:
            return request.build_absolute_uri(obj.avatar.url)
        else:
            return None

    class Meta:
        model = User
        fields = ('id', 'username', 'avatar', 'fullname', 'is_private',)


class FollowersSerializer(serializers.ModelSerializer):
    avatar = serializers.SerializerMethodField()

    def get_avatar(self, obj):
        request = self.context['request']
        if obj.avatar:
            return request.build_absolute_uri(obj.avatar.url)
        else:
            return None

    class Meta:
        model = User
        fields = ('id', 'username', 'avatar', 'fullname', 'is_private')


class OwnerSerializer(serializers.ModelSerializer):
    """
    nested serializer class for post author or notification payload
    """
    avatar = serializers.SerializerMethodField()

    # is_followee
    # is_requested

    def get_avatar(self, obj):
        request = self.context['request']
        return request.build_absolute_uri(obj.avatar.url) if obj.avatar else None

    class Meta:
        model = User
        fields = ('id', 'username', 'avatar', 'is_private',)
