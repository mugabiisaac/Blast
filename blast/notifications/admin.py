from django.contrib import admin
from notifications.models import Notification, FollowRequest
import datetime

def send_push(modeladmin, request, qs):
    for it in qs:
        it.send_push_message()

send_push.short_description = 'Send push notifications'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'text', 'type', 'created_at')
    actions = [send_push]

@admin.register(FollowRequest)
class FollowRequestAdmin(admin.ModelAdmin):
    list_display = ('follower', 'followee', 'created_at')
