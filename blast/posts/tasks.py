import logging
from datetime import timedelta

import itertools

import redis
from django.utils import timezone

from push_notifications.models import APNSDevice

from celery import shared_task

from notifications.models import Notification
from posts.models import Post, PostVote
from users.models import User, PinnedPosts


EXPIRE_LIMIT_MINUTES = 10


logger = logging.getLogger(__name__)
r = redis.StrictRedis(host='localhost', port=6379, db=0)


@shared_task(bind=False)
def clear_expired_posts():
    posts = Post.objects.expired()

    posts = list(posts)
    if not len(posts):
        return

    logger.info('Remove {} expired posts'.format(len(posts)))

    for it in posts:
        logger.info('Delete {}'.format(it.pk))
        # TODO: delete file
        it.delete()


def send_ending_soon_notification(post_id: int, users: set, message: str):
    send_marker_key = 'EndSoonPUSHSendState:{}:{}'.format(post_id, '{}')
    logger.info('Ending soon PUSH message candidates %s: %s', post_id, users)

    users = [it for it in users if not r.exists(send_marker_key.format(it))]
    logger.info('Send ending soon PUSH message to %s: %s', post_id, users)

    devices = APNSDevice.objects.filter(user_id__in=users)
    token_to_user_id = {it.registration_id: it.user_id for it in devices}

    def get_badge(token):
        if token not in token_to_user_id:
            return 0
        else:
            return Notification.unseen_count(token_to_user_id[token])

    for device in devices:
        device.send_message(message, sound='default',
                            badge=get_badge(device.registration_id), extra={'postId': post_id})

    author_id = Post.objects.get(id=post_id).user_id
    # Create notifications
    try:
        notify_type = None
        if message == Notification.TEXT_END_SOON_OWNER:
            notify_type = Notification.ENDING_SOON_OWNER
        elif message == Notification.TEXT_END_SOON_PINNER:
            notify_type = Notification.ENDING_SOON_PINNER
        elif message == Notification.TEXT_END_SOON_UPVOTER:
            notify_type = Notification.ENDING_SOON_UPVOTER
        elif message == Notification.TEXT_END_SOON_DOWNVOTER:
            notify_type = Notification.ENDING_SOON_DOWNVOTER

        logger.info('Creating notifications for %s, %s, notify_type is %s', post_id, users, notify_type)
        notifications = []
        for user_id in users:
            notify = Notification(post_id=post_id, user_id=user_id, other_id=author_id, type=notify_type)
            notifications.append(notify)

        Notification.objects.bulk_create(notifications)
        logger.info('Created notifications for %s, %s', post_id, users)
    except Exception:
        logger.exception("Failed to create notifications for %s %s", post_id, users)

    logger.info('Set up ending soon markers for %s %s', post_id, users)
    for it in users:
        key = send_marker_key.format(it)
        r.set(key, '1', ex=60 * (EXPIRE_LIMIT_MINUTES + 1))


def _get_post_for_users_push_list() -> dict:
    expired_posts = Post.objects.actual().filter(expired_at__lte=timezone.now() + timedelta(minutes=EXPIRE_LIMIT_MINUTES))
    expired_posts = expired_posts.filter(is_marked_for_removal=False)
    expired_posts = expired_posts.values('id', 'user_id')
    expired_posts = [{'post_id': it['id'], 'user_id': it['user_id']} for it in expired_posts]
    expired_ids = {it['post_id'] for it in expired_posts}
    posts = {it['post_id']: it for it in expired_posts}

    if not expired_posts:
        return

    logger.info('Got ready for removal posts: {}'.format(expired_posts))

    # Owners
    own_user_ids = {it['user_id'] for it in expired_posts}
    own_user_ids = User.objects.filter(id__in=own_user_ids, settings__notify_my_blasts=True)
    own_user_ids = set(own_user_ids.values_list('id', flat=True))
    logger.info('Got own_user_ids: {}'.format(own_user_ids))

    # Pinned
    pinned_posts = PinnedPosts.objects.filter(post_id__in=expired_ids)
    pinned_posts = list(pinned_posts.values('user_id', 'post_id'))
    logger.info('Got pinned_posts {}'.format(pinned_posts))

    pin_user_ids = {it['user_id'] for it in pinned_posts}
    pin_user_ids = User.objects.filter(id__in=pin_user_ids, settings__notify_pinned_blasts=True)
    pin_user_ids = set(pin_user_ids.values_list('id', flat=True))

    def pinned_cond(it):
        if it['user_id'] not in pin_user_ids:
            return False

        if it['user_id'] == posts[it['post_id']]['user_id']: # Was user pin own post?
            return False

        return True

    pinned_posts = list(filter(pinned_cond, pinned_posts))
    logger.info('Filtered pinned_posts is %s', pinned_posts)

    post_to_pinner = {it['post_id']: {it['user_id']} for it in pinned_posts}

    # Upvoters and downvoters
    votes = PostVote.objects.filter(post_id__in=expired_ids)
    votes = list(votes.values('is_positive', 'post_id', 'user_id'))
    logger.info('Got votes {}'.format(votes))

    def map_post_to_users(is_positive: bool) -> dict:
        """
        Maps posts to list of voters
        :return: dict of post_id to set of user_id
        """
        def voters_cond(it):
            post_id = it['post_id']
            if it['is_positive'] != is_positive:
                return False

            if it['user_id'] == posts[post_id]['user_id']:  # Was user vote for own post?
                return False

            if post_id in post_to_pinner and it['user_id'] in post_to_pinner[post_id]:  # Was user pin this post?
                return False

            return True

        votes_subset = list(filter(voters_cond, votes))
        users_ids = {it['user_id'] for it in votes_subset}

        query = {'id__in': users_ids}
        if is_positive:
            query['settings__notify_upvoted_blasts'] = True
        else:
            query['settings__notify_downvoted_blasts'] = True

        # Excludes user without appropriate settings
        users_ids = User.objects.filter(**query)
        users_ids = list(users_ids.values_list('id', flat=True))
        if is_positive:
            logger.info('Got post voters: %s', users_ids)
        else:
            logger.info('Got post downvoters: %s', users_ids)

        _votes = list(filter(lambda it: it['user_id'] in users_ids, votes_subset))
        _groups = itertools.groupby(_votes, lambda it: it['post_id'])
        _groups = {p: {it['user_id'] for it in g} for p, g in _groups}

        logger.debug('map_post_to_user: {}'.format(_groups))
        return _groups

    post_to_owners = {it['post_id']: {it['user_id']} for it in expired_posts if it['user_id'] in own_user_ids}

    result = {
        'owner': post_to_owners,
        'pinned': post_to_pinner,
        'upvote': map_post_to_users(True),
        'downvote': map_post_to_users(False),
    }

    logger.info('_get_post_for_users_push_list result is %s', result)

    return result


@shared_task(bind=False)
def send_expire_notifications():
    messages = {
        'owner': Notification.TEXT_END_SOON_OWNER,
        'pinned': Notification.TEXT_END_SOON_PINNER,
        'upvote': Notification.TEXT_END_SOON_UPVOTER,
        'downvote': Notification.TEXT_END_SOON_DOWNVOTER
    }

    post_dict = _get_post_for_users_push_list()
    if not post_dict:
        return

    logger.info('Sending expired PUSH to %s', post_dict)

    for category in post_dict:
        msg = messages[category]
        for post_id in post_dict[category]:
            users = post_dict[category][post_id]
            logger.info('Sending expired push %s %s %s', category, post_id, users)
            send_ending_soon_notification(post_id, users, msg)  # TODO: make async
