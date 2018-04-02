import logging
import redis
import os
import re
import uuid
from datetime import timedelta

from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.db.backends.dummy.base import IntegrityError

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.utils.safestring import mark_safe

from notifications.tasks import send_push_notification
from tags.models import Tag
from users.models import User, USER_RECENT_POSTS_KEY, UserSettings, Follower
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill

logger = logging.getLogger(__name__)
r = redis.StrictRedis(host='localhost', port=6379, db=0)


def post_image_upload_dir(instance: User, filename: str):
    """Returns unique path for uploading image by user and filename"""
    name, ext = os.path.splitext(filename)
    filename = u'{}{}'.format(str(uuid.uuid4()), ext)
    return u'/'.join([u'user', u'images', filename])


def post_upload_dir(instance, filename: str):
    """Returns unique path for uploading image by user and filename"""
    name, ext = os.path.splitext(filename)
    filename = u'{}{}'.format(str(uuid.uuid4()), ext)
    return u'/'.join([u'user', u'videos', filename])


def get_expiration_date():
    return timezone.now() + timedelta(days=1)


USER_REG = reg = re.compile(r'(?:(?<=\s)|^)@(\w*[A-Za-z_]+\w*)', re.IGNORECASE)


class TextNotificationMixin(object):
    @property
    def notified_users(self):
        """returns list of users notified by @"""
        return USER_REG.findall(self.text)


class PostManager(models.Manager):
    def actual(self):
        return self.get_queryset().filter(expired_at__gte=timezone.now())

    def public(self):
        qs = self.get_queryset()
        qs = qs.filter(Q(user__is_private=False) | Q(user=None),
                       expired_at__gte=timezone.now())

        return qs

    def expired(self):
        qs = self.get_queryset()
        qs = qs.filter(expired_at__lt=timezone.now())

        return qs


class PostAdminFields(object):
    def image_tag(self):
        if self.image_248:
            return mark_safe(u'<img src="{0}"/>'.format(self.image_248.url))
        else:
            return mark_safe('<img src="http://placehold.it/248x248?text=No image">')

    image_tag.short_description = 'Image'

    def video_tag(self):
        if self.video:
            return mark_safe(
                '<video controls><source src="{0}"></video>'.format(self.video.url))
        else:
            return mark_safe('<img src="http://placehold.it/248x248?text=No video">')

    video_tag.short_description = 'Video'


class Post(PostAdminFields,
           TextNotificationMixin,
           models.Model):

    objects = PostManager()

    post_type = models.IntegerField(null=True, blank=True)

    media_width = models.FloatField(default=0)
    media_height = models.FloatField(default=0)

    caption_width = models.FloatField('Caption Width', default=0)
    caption_height = models.FloatField('Caption Height', default=0)
    caption_x_pos = models.FloatField('Caption Center X Position', default=0)
    caption_y_pos = models.FloatField('Caption Center Y Position', default=0)
    cap_rotate_ang = models.FloatField('Caption Rotation Angle', default=0)

    lat = models.FloatField('Location Latitude', blank=True, null=True)
    lon = models.FloatField('Location Longitude', blank=True, null=True)
    location_name = models.CharField(max_length=1024, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expired_at = models.DateTimeField(default=get_expiration_date)

    text = models.CharField(max_length=1024, blank=True)

    # TODO: Remove black, null.
    user = models.ForeignKey(User, db_index=True, blank=True, null=True)
    image = models.ImageField(upload_to=post_image_upload_dir, blank=True, null=True)
    video = models.FileField(upload_to=post_upload_dir, blank=True, null=True)

    image_135 = ImageSpecField(source='image',
                               processors=[ResizeToFill(135, 135)],
                               format='PNG',
                               options={'quality': 90})

    image_248 = ImageSpecField(source='image',
                               processors=[ResizeToFill(248, 248)],
                               format='PNG',
                               options={'quality': 90})

    tags = models.ManyToManyField('tags.Tag', blank=True)

    # Cache for voted and downvoted lists.
    downvoted_count = models.PositiveIntegerField(default=0)
    voted_count = models.PositiveIntegerField(default=0)

    is_marked_for_removal = models.BooleanField(default=False)

    @property
    def is_anonymous(self):
        return self.user_id == User.objects.anonymous_id

    @property
    def popularity(self):
        return self.voted_count - self.downvoted_count

    def get_tag_titles(self):
        expr = re.compile(r'(?:(?<=\s)|^)#(\w*[A-Za-z_]+\w*)', re.IGNORECASE)
        return {it.lower() for it in expr.findall(self.text)}

    @property
    def time_remains(self):
        delta = self.expired_at - timezone.now()
        delta = delta - timedelta(microseconds=delta.microseconds)  # Remove microseconds for pretty printing
        return delta

    def comments_count(self):
        # TODO (VM): Cache this value to redis
        return PostComment.objects.filter(post=self.pk).count()

    def save(self, **kwargs):
        if not self.user:
            self.user_id = User.objects.anonymous_id

        return super().save(**kwargs)

    def __str__(self):
        return u'{} {}'.format(self.id, self.user_id)

    class Meta:
        ordering = ('created_at',)


class PostVote(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)

    user = models.ForeignKey(User, db_index=True)
    post = models.ForeignKey(Post, db_index=True)
    is_positive = models.NullBooleanField()  # False if post is downvoted, True otherwise.

    def __str__(self):
        return u'{} {}'.format(self.pk, self.user_id, self.post_id)

    class Meta:
        unique_together = (('user', 'post'),)


class PostComment(TextNotificationMixin, models.Model):
    created_at = models.DateTimeField(auto_now_add=True)

    parent = models.ForeignKey('PostComment', db_index=True, blank=True, null=True)
    user = models.ForeignKey(User, db_index=True)
    post = models.ForeignKey(Post, db_index=True)
    text = models.CharField(max_length=1024)

    def replies_count(self):
        # TODO (VM): Add redis cache
        return PostComment.objects.filter(parent=self.pk).count()

    def __str__(self):
        return u'{} for post {}'.format(self.pk, self.post)


USERS_RANGES_COUNT = 4


@receiver(pre_delete, sender=Post, dispatch_uid='on_blast_delete')
def blast_delete_handler(sender, instance: Post, **kwargs):
    logging.info('pre_delete for {} post'.format(instance.pk))
    if instance.video:
        logger.info('Delete {} image of {} post'.format(instance.image, instance.pk))
        instance.video.delete()

    if instance.image:
        logger.info('Delete {} video of {} post'.format(instance.image, instance.pk))
        instance.image.delete()

    # Remove post from user post set.
    posts_key = User.redis_posts_key(instance.user_id)
    if r.exists(posts_key):  # If cache is "hot"
        r.zrem(posts_key, instance.pk)
        logging.info('Remove {} from {} cache'.format(instance.pk, posts_key))

    # Updates search range
    search_range = min(r.zcard(posts_key), USERS_RANGES_COUNT)
    User.objects.filter(pk=instance.user_id).update(search_range=search_range)

    # Updates user popularity
    User.objects.filter(pk=instance.user_id).update(popularity=F('popularity') - 1)

    # Update user recent posts
    key = USER_RECENT_POSTS_KEY.format(instance.user_id)
    r.lrem(key, 1, instance.pk)


@receiver(pre_delete, sender=Post, dispatch_uid='post_clear_cache')
def blast_delete_handle_tags(sender, instance: Post, **kwargs):
    tags = list(instance.tags.all())
    tags = {it.title for it in tags}
    logging.info('pre_delete: Post. Update tag counters. {}'.format(tags))
    for it in tags:
        key = Tag.redis_posts_key(it)
        logging.info('pre_delete: Post. Update tag {} with key {}'.format(it, key))
        r.zrem(key, instance.pk)

    try:
        Tag.objects.filter(title__in=tags).update(total_posts=F('total_posts') - 1)
    except IntegrityError as e:
        logger.error('{}'.format(e))


@receiver(post_save, sender=Post, dispatch_uid='on_blast_save')
def blast_save_handler(sender, instance: Post, **kwargs):
    if not kwargs['created']:
        return

    # Add post to user post set.
    posts_key = User.redis_posts_key(instance.user_id)
    if not r.exists(posts_key):
        User.get_posts(instance.user_id, 0, 1)  # Heat up cache

    r.zadd(posts_key, 1, instance.pk)
    logging.info('Add {} to {} cache'.format(instance.pk, posts_key))

    # Updates search popularity
    search_range = min(r.zcard(posts_key), USERS_RANGES_COUNT)
    User.objects.filter(pk=instance.user_id).update(search_range=search_range)

    # Updates user popularity
    User.objects.filter(pk=instance.user_id).update(popularity=F('popularity') + 1)

    # Update user recent posts
    key = USER_RECENT_POSTS_KEY.format(instance.user_id)
    r.lpush(key, instance.pk)


@receiver(post_save, sender=Post, dispatch_uid='post_create_tags')
def blast_save_handle_tags(sender, instance: Post, **kwargs):
    if not kwargs['created']:
        return

    tags = instance.get_tag_titles()

    if tags:
        logger.info('Created new post with {} tags'.format(tags))

    if not tags:
        return

    db_tags = Tag.objects.filter(title__in=tags)
    db_tags = {it.title for it in db_tags}
    to_create = set(tags) - db_tags

    db_tags = []
    for it in to_create:
        db_tags.append(Tag(title=it))

    if db_tags:
        # FIXME (VM): if two user tries to create a same tags,
        # it will throw exception for one of them.
        Tag.objects.bulk_create(db_tags)

    db_tags = list(Tag.objects.filter(title__in=tags))
    instance.tags.add(*db_tags)

    # Increase total posts counter
    for it in db_tags:
        key = Tag.redis_posts_key(it.title)
        r.zincrby(key, instance.pk)

    Tag.objects.filter(title__in=tags).update(total_posts=F('total_posts') + 1)


@receiver(post_save, sender=PostVote, dispatch_uid='posts_post_save_vote_handler')
def vote_save(sender, instance: PostVote, created: bool, **kwargs):
    if not created or instance.is_positive is None:
        return

    user_key = User.redis_posts_key(instance.post.user_id)
    if instance.is_positive:
        r.zincrby(user_key, instance.post_id, 1)  # incr post in redis cache
        Post.objects.filter(pk=instance.post_id).update(voted_count=F('voted_count') + 1)
        logger.debug('Incremented voted_count {} {}'.format(instance, instance.post_id))
    else:
        r.zincrby(user_key, instance.post_id, -1)  # incr post in redis cache
        Post.objects.filter(pk=instance.post_id).update(downvoted_count=F('downvoted_count') + 1)
        logger.debug('Decremented voted_count {} {}'.format(instance, instance.post_id))

    logger.debug('Refreshing post after changing counter')
    # FIXME: Workaround for tests.VoteTest.test_twice_vote
    instance.post.refresh_from_db()


@receiver(post_save, sender=PostComment, dispatch_uid='blast_comment_notification')
def blast_comment_notification(sender, instance: PostComment, created, **kwargs):
    from notifications.models import Notification
    if not created:
        return

    post = instance.post
    if post.user_id == instance.user_id:  # Ignore post author
        return

    user = User.objects.select_related('settings').get(id=post.user_id)

    # Check that user allows to send push
    if user.settings.notify_comments == UserSettings.EVERYONE:
        pass
    elif user.settings.notify_comments == UserSettings.PEOPLE_I_FOLLOW:
        is_follower = Follower.objects.filter(followee_id=user.id, follower=instance.user_id).exists()
        if not is_follower:
            return
    elif user.settings.notify_comments == UserSettings.OFF:
        return

    notification = Notification(comment_id=instance.pk, post_id=instance.post_id,
                                user_id=user.pk, other_id=instance.user_id,
                                type=Notification.COMMENTED_POST)
    if instance.parent_id:
        notification.parent_comment_id = instance.parent_id

    notification.save()
    notification.send_push_message()
