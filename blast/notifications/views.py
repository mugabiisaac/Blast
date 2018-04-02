from celery.bin.celery import list_
from rest_framework import viewsets, permissions, mixins
from rest_framework.decorators import list_route
from rest_framework.response import Response

from notifications.models import Notification, FollowRequest
from core.views import ExtendableModelMixin
from notifications.serializers import NotificationPublicSerializer, FollowRequestPublicSerializer, \
    FollowRequestSerializer

from  users.models import User, Follower
from users.serializers import OwnerSerializer
from users.utils import mark_followee, mark_requested
import datetime
from django.utils import timezone

class NotificationsViewSet(ExtendableModelMixin,
                           viewsets.ReadOnlyModelViewSet):
    def extend_response_data(self, data):
        request = self.request

        users = {it['other'] for it in data if it['other']}
        users = list(User.objects.filter(pk__in=users))
        users = {it.pk: it for it in users}

        context = {'request': request}
        serialized_users = []
        for it in data:
            if not it['other']:
                continue

            user = users[it['other']]
            user = OwnerSerializer(instance=user, context=context).data
            serialized_users.append(user)

            it['user'] = user

            del it['other']

        mark_followee(serialized_users, self.request.user)
        mark_requested(serialized_users, self.request.user)

        return data

    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = NotificationPublicSerializer

    def get_queryset(self):
        time_24_hours_ago = timezone.now() - datetime.timedelta(days=1)
        Notification.objects.filter(user=self.request.user, is_seen=True, created_at__lt=time_24_hours_ago).delete()
        return Notification.objects.filter(user=self.request.user)

    # FIXME: need to write PUT for this action
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        results = response.data.get('results', [])
        ids = {it['id'] for it in results}

        # FIXME: need to write PUT for this action
        Notification.objects.filter(id__in=ids, is_seen=False).update(is_seen=True)

        return response

    @list_route(methods=['get'])
    def unseen(self, request):
        return Response({
            'count': Notification.unseen_count(request.user.pk)
        })
    

class FollowRequestViewSet(mixins.RetrieveModelMixin,
                           mixins.UpdateModelMixin,
                           mixins.ListModelMixin,
                           viewsets.GenericViewSet):
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return FollowRequest.objects.filter(followee=self.request.user)

    def get_serializer_class(self):
        if self.request.method in permissions.SAFE_METHODS:
            return FollowRequestPublicSerializer
        else:
            return FollowRequestSerializer

    # FIXME: need to write PUT for this action
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        results = response.data.get('results', [])
        ids = {it['id'] for it in results}

        # FIXME: need to write PUT for this action
        self.get_queryset().filter(id__in=ids, is_seen=False).update(is_seen=True)

        return response
