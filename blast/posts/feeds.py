from datetime import timezone

from django.db.models import Q
from rest_framework import viewsets

from core.pagination import DateTimePaginator
from core.views import ExtendableModelMixin
from posts.models import Post, PostVote
from posts.serializers import PostPublicSerializer
from posts.utils import extend_posts
from users.models import User, BlockedUsers
from users.utils import mark_followee, mark_requested


# TODO (VM): Add feeds test, check author, hidden posts and voted posts
# Order of posts should be by date, with newest appearing at the top:  
#
# - Blasts users currently Following (all post uploaded by users that you have chosen to follow) 
#
# - Within the posts of users you are currently following,
#   Anonymous posts will be displayed (1 in every 10 at random)
#   *Example: First 10 posts display 9 posts from users that you are following and
#   1 Anonymous at position 8. 
#
# - After all posts by users currently following has been viewed all other posts will
#   be rendered based on popularity with Anonymous posts being displayed in
#   the same manner as described above.


class BaseFeedView(ExtendableModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = PostPublicSerializer
    pagination_class = DateTimePaginator

    def extend_response_data(self, data):
        extend_posts(data, self.request.user, self.request)

        # Adds is_requested and is_followee flags
        authors = [it['author'] for it in data if it['author']]
        mark_followee(authors, self.request.user)
        mark_requested(authors, self.request.user)

    def get_queryset(self):
        qs = Post.objects.actual()

        user = self.request.user

        if not user.is_authenticated():
            return qs

        # Exclude blocked users
        # FIXME (VM): cache list in redis?
        blocked = BlockedUsers.objects.filter(user=user)
        blocked = {it.blocked_id for it in blocked}
        qs = qs.exclude(user__in=blocked)

        # Exclude hidden posts
        # FIXME (VM): cache list in redis?
        hidden = user.hidden_posts.all().values('pk')
        hidden = {it['pk'] for it in hidden}
        qs = qs.exclude(pk__in=hidden)

        # Exclude voted posts
        # FIXME (VM): votes list can be very large
        # FIXME (VM): cache list in redis?
        voted = PostVote.objects.filter(user=user.pk).values('post')
        voted = {it['post'] for it in voted}
        qs = qs.exclude(pk__in=voted)

        return qs.order_by('-created_at')

    def followees(self):
        user = self.request.user
        # FIXME: write method for getting all followees
        return User.get_followees(user.pk, 0, 1000)


class MainFeedView(BaseFeedView):
    """
    Returns list of posts from user followees
    """

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated():
            return Post.objects.filter(id__lt=0)  # Empty response :(

        qs = super().get_queryset()
        qs = qs.filter(Q(user__in=self.followees()) | Q(user_id=user.pk))

        if user.pk != User.objects.anonymous_id:
            qs = qs.exclude(user_id=User.objects.anonymous_id)

        return qs


class RecentFeedView(BaseFeedView):
    def get_queryset(self):
        qs = super().get_queryset()

        user = self.request.user
        if not user.is_authenticated():
            return qs

        followees = self.followees()
        if User.objects.anonymous_id in followees:
            followees.remove(User.objects.anonymous_id)

        show_anonymous = User.objects.anonymous_id in followees

        if show_anonymous:
            qs = qs.filter(user_id=user.pk)
            followees.remove(User.objects.anonymous_id)

        qs = qs.exclude(Q(user_id__in=followees))
        qs = qs.filter(user__is_private=False)
        qs = qs.exclude(user_id=user.pk)

        return qs
