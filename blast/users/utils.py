import itertools
import redis

from notifications.models import FollowRequest
from posts.serializers import PreviewPostSerializer
from posts.utils import mark_voted
from users.models import User, Follower
from posts.models import Post

from typing import List, Set, Dict, Iterable

r = redis.StrictRedis(host='localhost', port=6379, db=0)


def filter_followee_users(user: User, user_ids: list or set):
    if not user.is_authenticated():
        return set()

    result = Follower.objects.filter(follower=user,
                                     followee_id__in=user_ids).values_list('followee_id', flat=True)
    return set(result)


def mark_followee(users: List[Dict], user: User) -> List[Dict]:
    if not user.is_authenticated():
        for it in users:
            it['is_followee'] = False
        return users

    followees = filter_followee_users(user, {it['id'] for it in users})
    for it in users:
        pk = it['id']
        it['is_followee'] = pk in followees

    return users


def mark_requested(users: List[Dict], user: User) -> List[Dict]:
    if not user.is_authenticated():
        for it in users:
            it['is_requested'] = False

        return users

    requests = FollowRequest.objects.filter(follower=user, followee_id__in={it['id'] for it in users})
    requests = set(requests.values_list('followee_id', flat=True))
    for it in users:
        it['is_requested'] = it['id'] in requests

    return users


def get_recent_posts(users: List[int] or Set[int], count: int) -> Dict:
    """Returns last posts for each user in users list"""
    # users = User.objects.filter(id__in=users)

    post_ids = []
    for it in users:
        ids = User.get_recent_posts(it, 0, count - 1)
        post_ids.extend(ids)

    posts = list(Post.objects.filter(id__in=post_ids))

    posts = sorted(posts, key=lambda post: post.user_id)
    grouped = itertools.groupby(posts, lambda post: post.user_id)
    result = {k: list(v) for k, v in grouped}

    for it in users:
        if it not in result:
            result[it] = []

    return result


def attach_recent_posts_to_users(data: Iterable, request):
    user_ids = {it['id'] for it in data}

    user_to_posts = get_recent_posts(user_ids, 3)
    for user_pk in user_to_posts:
        posts = user_to_posts[user_pk]
        user_to_posts[user_pk] = PreviewPostSerializer(posts, many=True, context={'request': request}).data

    posts = user_to_posts.values()
    posts = [it for sublist in posts for it in sublist]  # Flat list of posts

    mark_voted(posts, request.user)

    for it in data:
        pk = it['id']

        is_owner = it['id'] == request.user.pk
        is_visible = (not it['is_private'] or it['is_followee']) or is_owner
        it['posts'] = user_to_posts[pk] if is_visible else []

