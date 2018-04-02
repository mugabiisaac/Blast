from datetime import timedelta

from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from notifications.models import Notification
from posts.models import Post
from reports.models import Report, PostReport


def mark_for_removal(modeladmin, request, qs):
    content_type = ContentType.objects.get(app_label='posts', model='post')

    # Pull posts from reports
    reports = list(qs.filter(content_type=content_type).values('user_id', 'object_pk'))

    expired_at = timezone.now() + timedelta(minutes=10)

    # Mark post for removal
    post_ids = {it['object_pk'] for it in reports}
    Post.objects.filter(pk__in=post_ids).update(expired_at=expired_at, is_marked_for_removal=True)
    posts = list(Post.objects.filter(pk__in=post_ids))

    # Send notification PUSH'es
    for post in posts:
        notification = Notification.objects.create_marked_for_removal(post.user_id, post.pk)
        notification.send_push_message()


mark_for_removal.short_description = 'Mark for removal (posts only)'


@admin.register(Report)
class ReportsAdmin(admin.ModelAdmin):
    list_display = ('pk', 'reason', 'content_type', 'object_pk', 'content_object', 'user')


@admin.register(PostReport)
class PostReportAdmin(admin.ModelAdmin):
    list_display = ('pk', 'reason', 'user', 'image_tag', 'video_tag', 'url_to_post')
    actions = [mark_for_removal]
    readonly_fields = ('image_tag', 'video_tag')

    def get_queryset(self, request):
        content_type = ContentType.objects.get(app_label='posts', model='post')
        return PostReport.objects.filter(content_type=content_type)
