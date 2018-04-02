import logging

from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

from posts.models import Post, PostComment
from tags.models import Tag
from users.models import User, UserSettings, Follower

from notifications.tasks import send_push_notification

logger = logging.getLogger(__name__)


# TODO: make proxy model for Notification
class FollowRequest(models.Model):
    """ Follow request for private user """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    follower = models.ForeignKey(User, related_name='follower_requests', db_index=True)
    followee = models.ForeignKey(User, related_name='followee_requests', db_index=True)

    is_seen = models.BooleanField(default=False)

    @property
    def notification_text(self):
        return '@{} has requested to follow you.'.format(self.follower.username)

    @property
    def push_payload(self):
        return {
            'userId': self.follower_id,
        }

    def send_push_message(self):
        logger.info('Send follow request push message for id = %s, follower = %s', self.followee_id, self.follower_id)
        send_push_notification.delay(self.followee_id, self.notification_text, self.push_payload)

    def __str__(self):
        return u'{} {}'.format(self.follower_id, self.followee_id)

    class Meta:
        unique_together = ('follower', 'followee',)
        ordering = ('-id',)


class NotificationManager(models.Manager):

    @staticmethod
    def create_marked_for_removal(user_id: int, post_id: int):
        return Notification.objects.create(user_id=user_id, other_id=user_id,
                                           post_id=post_id, type=Notification.MARKED_FOR_REMOVAL)

    @staticmethod
    def create_replied_on_comment(comment: PostComment):
        parent = comment.parent
        if parent.user_id == comment.user_id:
            return None

        return Notification.objects.create(post_id=comment.post_id,
                                           user_id=parent.user_id, other_id=comment.user_id,
                                           comment_id=comment.pk, parent_comment_id=comment.parent_id,
                                           type=Notification.REPLIED_ON_COMMENT)


class Notification(models.Model):
    TEXT_STARTED_FOLLOW_PATTERN = 'Started following you.'
    TEXT_VOTES_REACHED_PATTERN = 'Your Blast now has {:,} votes.'

    TEXT_END_SOON_OWNER = 'Your Blast is ending soon.'
    TEXT_END_SOON_PINNER = 'Pinned Blast ending soon.'
    TEXT_END_SOON_UPVOTER = 'Upvoted Blast ending soon.'
    TEXT_END_SOON_DOWNVOTER = 'Downvoted Blast ending soon.'

    TEXT_SHARE_POST = 'Shared a Blast.'
    TEXT_SHARE_TAG = 'Shared a hashtag: #{}.'

    #special direct message messages
    TEXT_SELF_DESTRUCT = 'set the selt destruct to 24hrs'
    TEXT_CHANGED_GROUP_NAME ='changed the group name to {}.'
    TEXT_TOOK_SCREENSHOT = '{} took a screenshot'

    STARTED_FOLLOW = 0
    MENTIONED_IN_COMMENT = 1
    VOTES_REACHED = 2
    ENDING_SOON_OWNER = 3
    ENDING_SOON_PINNER = 4
    ENDING_SOON_UPVOTER = 5
    ENDING_SOON_DOWNVOTER = 6

    SHARE_POST = 7
    SHARE_TAG = 8

    COMMENTED_POST = 9
    MARKED_FOR_REMOVAL = 10
    REPLIED_ON_COMMENT = 11

    SELF_DESTRUCT = 12
    CHANGED_GROUP_NAME = 13
    TOOK_SCREENSHOT = 14

    TYPE = (
        (STARTED_FOLLOW, 'Started follow'),
        (MENTIONED_IN_COMMENT, 'Mentioned in comment'),
        (VOTES_REACHED, 'Votes reached'),
        (ENDING_SOON_OWNER, 'Ending soon: owner'),
        (ENDING_SOON_PINNER, 'Ending soon: pinner'),
        (ENDING_SOON_UPVOTER, 'Ending soon: upvoter'),
        (ENDING_SOON_DOWNVOTER, 'Ending soon: downvoter'),
        (SHARE_POST, "Shared a Blast"),
        (SHARE_TAG, "Shared a hashtag"),
        (COMMENTED_POST, "Commented post"),
        (MARKED_FOR_REMOVAL, "Marked for removal"),
        (REPLIED_ON_COMMENT, "Replied on comment"),
        (SELF_DESTRUCT, "set the selt destruct to 24hrs"),
        (CHANGED_GROUP_NAME, "changed the group name to {}."),
        (TOOK_SCREENSHOT, "{} took a screenshot")
    )

    objects = NotificationManager()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    votes = models.PositiveIntegerField(default=0)
    post = models.ForeignKey(Post, blank=True, null=True)
    comment = models.ForeignKey(PostComment, blank=True, null=True)
    parent_comment = models.ForeignKey(PostComment, blank=True, null=True, related_name='notifaication_parent')
    user = models.ForeignKey(User, related_name='notifications', db_index=True)
    tag = models.ForeignKey(Tag, blank=True, null=True)
    other = models.ForeignKey(User, null=True, blank=True, related_name='mention_notifications')

    type = models.PositiveSmallIntegerField(choices=TYPE)

    is_seen = models.BooleanField(default=False)

    @staticmethod
    def unseen_count(user_id: int):
        count = Notification.objects.filter(user_id=user_id, is_seen=False).count()
        count += FollowRequest.objects.filter(followee_id=user_id, is_seen=False).count()
        return count

    @property
    def text(self):
        if self.type == Notification.STARTED_FOLLOW:
            return Notification.TEXT_STARTED_FOLLOW_PATTERN.format(self.other.username)
        elif self.type == Notification.VOTES_REACHED:
            return Notification.TEXT_VOTES_REACHED_PATTERN.format(self.votes)
        elif self.type == Notification.MENTIONED_IN_COMMENT:
            return 'Mentioned you in comment.'

        elif self.type == Notification.ENDING_SOON_OWNER:
            return self.TEXT_END_SOON_OWNER
        elif self.type == Notification.ENDING_SOON_PINNER:
            return self.TEXT_END_SOON_PINNER
        elif self.type == Notification.ENDING_SOON_UPVOTER:
            return self.TEXT_END_SOON_UPVOTER
        elif self.type == Notification.ENDING_SOON_DOWNVOTER:
            return self.TEXT_END_SOON_DOWNVOTER
        elif self.type == Notification.SHARE_POST:
            return self.TEXT_SHARE_POST
        elif self.type == Notification.SHARE_TAG:
            return self.TEXT_SHARE_TAG.format(self.tag_id)
        elif self.type == Notification.COMMENTED_POST:
            return u'Commented: {}'.format(self.comment.text)
        elif self.type == Notification.MARKED_FOR_REMOVAL:
            return u'Content Removed: Your Blast is ending soon.'
        elif self.type == Notification.REPLIED_ON_COMMENT:
            return u'Replied to your comment: {}'.format(self.comment.text)

        raise ValueError('Unknown notification type')

    @property
    def notification_text(self):
        if self.type == Notification.STARTED_FOLLOW:
            return u'@{} started following you.'.format(self.other.username)
        elif self.type == Notification.SHARE_POST:
            return u'@{} shared a Blast.'.format(self.other.username)
        elif self.type == Notification.SHARE_TAG:
            return u'@{} shared a tag.'.format(self.other.username)
        elif self.type == Notification.MENTIONED_IN_COMMENT:
            return u'@{} mentioned you in comment.'.format(self.other.username)
        elif self.type == Notification.COMMENTED_POST:
            return u'@{} commented: {}.'.format(self.other.username, self.comment.text)
        elif self.type == Notification.REPLIED_ON_COMMENT:
            return u'@{} replied to your comment: {}'.format(self.other.username, self.comment.text)
        else:
            return self.text

    @property
    def direct_messages(self):
        if self.type == Notification.STARTED_FOLLOW:
            return u'@{} started following you.'.format(self.other.username)
        elif self.type == Notification.SELF_DESTRUCT:
            return u'@{} set the selt destruct to 24hrs.'.format(self.other.username)
        elif self.type == Notification.CHANGED_GROUP_NAME:
            return u'@{} changed the group name.'.format(self.other.username)
        elif self.type == Notification.TOOK_SCREENSHOT:
            return u'@{} took a screenshot.'.format(self.other.username)
        else:
            return self.text



    @property
    def push_payload(self):
        payload = {}
        if self.tag_id:
            payload['tagId'] = self.tag_id

        if self.post_id:
            payload['postId'] = self.post_id

        if self.other_id:
            payload['userId'] = self.other_id

        if self.comment_id:
            payload['commentId'] = self.comment_id

        if self.parent_comment_id:
            payload['parentId'] = self.parent_comment_id

        return payload

    def send_push_message(self):
        logger.info('Send push message: type=%s, user=%s, text=%s, payload=%s', self.type, self.user_id,
                    self.notification_text, self.push_payload)

        send_push_notification.delay(self.user_id, self.notification_text, self.push_payload)

    def __str__(self):
        return '{} - {}'.format(self.user, self.text)

    class Meta:
        ordering = ('-id',)


# TODO: move to TextNotificationMixin mixin
def notify_users(users: list, post: Post, comment: PostComment or None, author: User):
    # TODO: author can be None
    if not users:
        return

    query = Q()
    for it in users:
        query = query | Q(username__istartswith=it)

    users = User.objects.filter(query).prefetch_related('settings')

    followers = Follower.objects.filter(followee=author, follower__in=users)
    followers = {it.follower_id for it in followers}

    notifications = []
    for user in users:
        is_follow = user.id in followers
        if user.settings.notify_comments == UserSettings.OFF:
            continue

        for_everyone = user.settings.notify_comments == UserSettings.EVERYONE
        for_follower = user.settings.notify_comments == UserSettings.PEOPLE_I_FOLLOW and is_follow
        if for_everyone or for_follower:
            notification = Notification(user=user, post=post,
                                        other=author, comment=comment,
                                        type=Notification.MENTIONED_IN_COMMENT)
            notifications.append(notification)

    Notification.objects.bulk_create(notifications)

    for it in notifications:
        it.send_push_message()


@receiver(post_save, sender=PostComment, dispatch_uid='notifications_comments')
def save_comment_notifications(sender, instance: PostComment, **kwargs):
    if not kwargs['created']:
        return

    users = instance.notified_users
    notify_users(users, instance.post, instance, instance.user)

    if instance.parent_id:
        notification = Notification.objects.create_replied_on_comment(instance)
        if notification:
            notification.send_push_message()


@receiver(post_save, sender=Post, dispatch_uid='notifications_posts')
def blast_save_notifications(sender, instance: Post, **kwargs):
    """Handles changing of votes counter and creates notification"""
    votes = instance.voted_count

    users = instance.notified_users
    notify_users(users, instance, None, instance.user)

    if votes == 0 or votes % 10:
        return

    if (votes <= 100 and votes % 10 == 0) or (votes >= 1000 and votes % 1000 == 0):
        logger.info('Post {} reached {} votes'.format(instance, votes))
        notification = Notification.objects.create(user_id=instance.user_id, other_id=instance.user_id,
                                                   post_id=instance.pk, votes=votes, type=Notification.VOTES_REACHED)

        if instance.user.settings.notify_votes:
            notification.send_push_message()


@receiver(post_save, sender=Follower, dispatch_uid='notifications_follow')
def start_following_handler(sender, instance: Follower, **kwargs):
    """Handles following event"""
    followee_id = instance.followee_id
    follower_id = instance.follower_id

    if followee_id == User.objects.anonymous_id:
        # Ignore anonymous user because he followee by default
        return

    logger.info('Create following notification {} {}'.format(follower_id, followee_id))
    notification = Notification.objects.create(user_id=followee_id, other_id=follower_id,
                                               type=Notification.STARTED_FOLLOW)
    notification.send_push_message()


@receiver(post_save, sender=FollowRequest, dispatch_uid='notification_follow_request')
def follow_request_created(sender, instance: FollowRequest, created: bool, **kwargs):
    if not created:
        return False

    instance.send_push_message()
