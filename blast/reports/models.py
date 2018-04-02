from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.safestring import mark_safe

from posts.models import Post
from users.models import User


class Report(models.Model):
    OTHER = 0
    SENSITIVE_CONTENT = 1
    SPAM = 2
    DUPLICATED_CONTENT = 3
    BULLYING = 4
    INTEL_VIOLATION = 5

    REASONS = (
        (OTHER, "Other"),
        (SENSITIVE_CONTENT, "Sensitive content"),
        (SPAM, "Spam"),
        (DUPLICATED_CONTENT, "Duplicated content"),
        (BULLYING, "Bulling"),
        (INTEL_VIOLATION, "Intel violation"),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    user = models.ForeignKey(User)
    reason = models.PositiveSmallIntegerField(choices=REASONS, help_text='Report reason')
    text = models.CharField(max_length=128, blank=True, help_text='Details')

    content_type = models.ForeignKey(ContentType,
                                     related_name="content_type_set_for_%(class)s",
                                     on_delete=models.CASCADE)
    object_pk = models.PositiveIntegerField('object ID')
    content_object = GenericForeignKey('content_type', 'object_pk')

    class Meta:
        get_latest_by = "created_at"
        verbose_name = "Report"
        verbose_name_plural = "Reports"


class PostReport(Report):
    def image_tag(self):
        post = Post.objects.get(pk=self.object_pk)
        if post.image_248:
            return mark_safe(u'<img src="{0}"/>'.format(post.image_248.url))
        else:
            return mark_safe('<img src="http://placehold.it/248x248?text=No image">')
    image_tag.short_description = 'Image'

    def video_tag(self):
        post = Post.objects.get(pk=self.object_pk)
        if post.video:
            return mark_safe('<video width="248" height="248" controls><source src="{0}"></video>'.format(post.video.url))
        else:
            return mark_safe('<img src="http://placehold.it/248x248?text=No video">')
    video_tag.short_description = 'Video'

    def url_to_post(self):
        url = reverse('admin:posts_post_change', args=(self.object_pk,))
        return mark_safe('<a class="button" href="{0}">Edit post</a>'.format(url))

    class Meta:
        proxy = True
