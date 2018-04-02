import redis
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import filters
from rest_framework import viewsets, mixins, permissions, status
from rest_framework.decorators import detail_route, list_route
from rest_framework.response import Response

from core.views import ExtendableModelMixin

from posts.models import Post, PostComment, PostVote
from posts.serializers import (PostSerializer, PostPublicSerializer,
                               CommentSerializer, CommentPublicSerializer,
                               VoteSerializer)

from datetime import timedelta

from notifications.tasks import send_share_notifications

from reports.serializers import ReportSerializer
from tags.models import Tag
from users.models import User, Follower, BlockedUsers, PinnedPosts

from users.serializers import UsernameSerializer

from posts.utils import attach_users, extend_posts
from users.utils import mark_followee
from users.utils import mark_requested

import datetime
from django.utils import timezone

r = redis.StrictRedis(host='localhost', port=6379, db=0)


# FIXME: Replace by custom permission class
class PerObjectPermissionMixin(object):

    public_serializer_class = None
    private_serializer_class = None

    def get_serializer_class(self):
        if self.request.method in permissions.SAFE_METHODS:
            return self.public_serializer_class
        else:
            return self.private_serializer_class

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return permissions.AllowAny(),
        else:
            return permissions.IsAuthenticated(),

    def check_object_permissions(self, request, obj: Post):
        if request.method in permissions.SAFE_METHODS:
            return

        if obj.user.pk is not request.user.pk:
            return self.permission_denied(self.request, 'You are not owner of this object')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class PostsViewSet(PerObjectPermissionMixin,
                   ExtendableModelMixin,
                   viewsets.ModelViewSet):
    """
    ---
    create:
        parameters:
            - name: post_type
              type: integer
            - name: video
              type: file
            - name: image
              type: file
            - name: caption_height
              type: float
              description: caption height
            - name: caption_x_pos
              type: float
              description: caption center position Y
            - name: caption_y_pos
              type: float
              description: caption center position X
            - name: cap_rotate_ang
              type: float
              description: caption rotation angle
            - name: caption_width
              type: float
              description: caption width
            - name: lat
              type: float
              description: Location Latitude
            - name: lon
              type: float
              description: Location Longitude
            - name: location_name
              type: string
              description: location name
    """
    queryset = Post.objects.public()

    public_serializer_class = PostPublicSerializer
    private_serializer_class = PostSerializer

    filter_backends = (filters.DjangoFilterBackend,)
    filter_fields = ('user', 'tags',)

    def extend_response_data(self, data):
        extend_posts(data, self.request.user, self.request)

    def get_queryset(self):
        if not self.request.user.is_authenticated():
            return self.queryset.filter(user__is_private=False)

        followees = Follower.objects.filter(follower=self.request.user.pk)
        followees = {it.followee_id for it in followees}

        qs = Post.objects.actual()
        qs = qs.filter(Q(user__is_private=False) | Q(user=None) |
                       Q(user__in=followees) |
                       Q(user=self.request.user.pk))

        return qs

    # TODO: Move to mixin
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)

        # Changes response use PostPublicSerializer
        data = PostPublicSerializer(serializer.instance, context=self.get_serializer_context()).data
        data = extend_posts([data], request.user, request)

        return Response(data[0], status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save()
        post = serializer.instance
        if post.is_anonymous:
            PinnedPosts.objects.create(user=self.request.user, post=post)

    def destroy(self, request, *args, **kwargs):
        """
        Deletes user post

        ---
        omit_serializer: true
        parameters:
            - name: pk
              description: user post id
        """
        return super().destroy(request, *args, **kwargs)

    def _update_vote(self, request, is_positive, pk=None,):
        if not self.request.user.is_authenticated():
            return self.permission_denied(self.request, 'You are not authenticated')

        try:
            post = self.get_queryset().get(pk=pk)
        except Post.DoesNotExist:
            raise Http404()

        try:
            vote = PostVote.objects.get(user=request.user, post=post)
        except PostVote.DoesNotExist:
            vote = PostVote(user=request.user, post=post, is_positive=is_positive)
        # vote, created = PostVote.objects.get_or_create(user=request.user, post=post)
        vote.is_positive = is_positive
        vote.save()

        # Increase popularity in tags cache
        # TODO: Move to post_save for vote?
        tags = post.get_tag_titles()
        for tag in tags:
            key = Tag.redis_posts_key(tag)
            r.zincrby(key, post.pk, 1 if is_positive else -1)

        if is_positive:
            post.expired_at += timedelta(minutes=5)
        else:
            min_time_in_seconds = 60 * 10

            remains = post.time_remains.total_seconds()
            if remains > min_time_in_seconds: # Is enough time to downvote?
                post.expired_at -= timedelta(seconds=min_time_in_seconds)
                remains = post.time_remains.total_seconds()

                if remains < min_time_in_seconds:  # Is too much taken away?
                    post.expired_at = timezone.now() + timedelta(seconds=min_time_in_seconds)

        post.save()

        serializer = PostPublicSerializer(instance=post)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @detail_route(methods=['get'])
    def voters(self, request, pk=None):
        qs = PostVote.objects.filter(post=pk)
        qs = qs.prefetch_related('user')

        page = self.paginate_queryset(qs)
        users = [it.user for it in page]

        serializer = UsernameSerializer(users, many=True,
                                        context=self.get_serializer_context())

        mark_followee(serializer.data, self.request.user)
        mark_requested(serializer.data, self.request.user)

        return self.get_paginated_response(serializer.data)

    @detail_route(methods=['put'])
    def vote(self, request, pk=None):
        """
        Add vote to post

        ---
        omit_serializer: true
        parameters_strategy:
            form: replace
        """
        return self._update_vote(request, True, pk)

    @detail_route(methods=['put'])
    def downvote(self, request, pk=None):
        """
        Downvote post
        ---
        omit_serializer: true
        parameters_strategy:
            form: replace
        """
        return self._update_vote(request, False, pk)

    def _update_visibility(self, pk, is_hidden):
        post = get_object_or_404(Post, pk=pk)
        user = self.request.user
        exists = user.hidden_posts.filter(pk=post.pk).exists()

        if is_hidden and not exists:
            user.hidden_posts.add(post)

        if not is_hidden and exists:
            user.hidden_posts.remove(post)

        return Response()

    @detail_route(methods=['put'])
    def hide(self, request, pk=None):
        """
        Hide post

        ---
        omit_serializer: true
        parameters_strategy:
            form: replace
        """
        return self._update_visibility(pk, True)

    @detail_route(methods=['put'])
    def show(self, request, pk=None):
        """
        Show post

        ---
        omit_serializer: true
        parameters_strategy:
            form: replace
        """
        return self._update_visibility(pk, False)

    @detail_route(methods=['put'], permission_classes=[permissions.IsAuthenticated])
    def report(self, request, pk=None):
        """

        ---
        serializer: reports.serializers.ReportSerializer
        parameters:
            - name: pk
              description: post id
              type: query
            - name: reason
              description: OTHER = 0, SENSITIVE_CONTENT = 1, SPAM = 2, DUPLICATED_CONTENT = 3,
                           BULLYING = 4, INTEL_VIOLATION = 5
            - name: text
              description: length < 128
        """
        instance = get_object_or_404(Post, pk=pk)
        serializer = ReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user, object_pk=instance.pk,
                        content_type=ContentType.objects.get(app_label='posts', model='post'))

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @detail_route(methods=['put'])
    def pin(self, request, pk=None):
        """
        Adds post to user pinned posts list
        ---
        omit_serializer: true
        parameters_strategy:
            form: replace
        """
        if self.request.user.is_anonymous():
            return self.permission_denied(request)
        instance = get_object_or_404(Post, pk=pk)
        if not PinnedPosts.objects.filter(user_id=self.request.user.pk, post=instance).exists():
            PinnedPosts.objects.create(user_id=self.request.user.pk, post=instance)

        return Response()

    @detail_route(methods=['put'])
    def unpin(self, request, pk=None):
        """
        Removes post from user pinned posts list
        ---
        omit_serializer: true
        parameters_strategy:
            form: replace
        """
        if self.request.user.is_anonymous():
            return self.permission_denied(request)

        instance = get_object_or_404(Post, pk=pk)
        PinnedPosts.objects.filter(user_id=self.request.user.pk, post_id=pk).delete()

        return Response()

    @detail_route(methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def share(self, request, pk=None):
        """

        ---
        omit_serializer: true
        parameters:
            - name: pk
              description: post id
              type: query
            - name: users
              description: list of id of followers
        """
        users = request.data['users']

        send_share_notifications.delay(user_id=self.request.user.pk, post_id=pk, users=users)

        return Response({'users': users})


class PinnedPostsViewSet(ExtendableModelMixin,
                         mixins.ListModelMixin,
                         viewsets.GenericViewSet):
    serializer_class = PostPublicSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def extend_response_data(self, data):
        extend_posts(data, self.request.user, self.request)

    def get_queryset(self):
        posts = self.request.user.pinned.filter().values('post_id')
        return Post.objects.filter(expired_at__gte=timezone.now(), id__in=posts)


class VotedPostBaseView(mixins.ListModelMixin,
                        viewsets.GenericViewSet):

    permission_classes = (permissions.IsAuthenticated,)

    serializer_class = PostPublicSerializer

    # TODO: Exclude hidden posts
    def get_queryset(self):
        # FIXME: This list can be big.
        voted_ids = PostVote.objects.filter(user=self.request.user,
                                            is_positive=self.is_positive)
        voted_ids = [it.post_id for it in voted_ids]
        return Post.objects.filter(pk__in=voted_ids,
                                   expired_at__gte=timezone.now())

    def list(self, request, *args, **kwargs):
        response = super().list(self, request, *args, **kwargs)
        extend_posts(response.data['results'], request.user, request)

        return response

class VotersListViewSet(mixins.ListModelMixin,
                     viewsets.GenericViewSet):
    """
    Returns list of Voters.
    """
    serializer_class = PostPublicSerializer
    queryset = PostVote.objects.all()


class VotedPostsViewSet(VotedPostBaseView):
    is_positive = True


class DonwvotedPostsViewSet(VotedPostBaseView):
    is_positive = False


# TODO (VM): Check if post is hidden
# TODO (VM): Remove Update actions
class CommentsViewSet(PerObjectPermissionMixin,
                      ExtendableModelMixin,
                      viewsets.ModelViewSet):
    queryset = PostComment.objects.all().order_by('-created_at')
    public_serializer_class = CommentPublicSerializer
    private_serializer_class = CommentSerializer

    filter_backends = (filters.DjangoFilterBackend,)
    filter_fields = ('user', 'post', 'parent',)

    def get_queryset(self):
        qs = super().get_queryset()

        query_params = self.request.query_params
        if query_params.get('parent__is_null', '').lower() == 'true':
            qs = qs.filter(parent=None)
        elif query_params.get('parent__is_null', '').lower() == 'false':
            qs = qs.exclude(parent=None)

        return qs

    def extend_response_data(self, data):
        attach_users(data, self.request.user, self.request)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)

        # Changes response use PostPublicSerializer
        data = self.public_serializer_class(serializer.instance).data
        data = attach_users([data], request.user, request)
        return Response(data[0], status=status.HTTP_201_CREATED, headers=headers)

    def destroy(self, request, *args, **kwargs):
        """
        Deletes user comment
        ---
        omit_serializer: true
        parameters:
            - name: pk
              description: comment id
        """
        return super().destroy(request, *args, **kwargs)

    @detail_route(methods=['put'], permission_classes=[permissions.IsAuthenticated])
    def report(self, request, pk=None):
        """

        ---
        serializer: reports.serializers.ReportSerializer
        parameters:
            - name: pk
              description: post id
              type: query
            - name: reason
              description: OTHER = 0, SENSITIVE_CONTENT = 1, SPAM = 2, DUPLICATED_CONTENT = 3,
                           BULLYING = 4, INTEL_VIOLATION = 5
            - name: text
              description: length < 128
        """
        instance = get_object_or_404(PostComment, pk=pk)
        serializer = ReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user, object_pk=instance.pk,
                        content_type=ContentType.objects.get(app_label='posts', model='postcomment'))

        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PostSearchViewSet(mixins.ListModelMixin,
                        viewsets.GenericViewSet):
    serializer_class = PostPublicSerializer

    queryset = Post.objects.all()

    def get_queryset(self):
        tag = self.request.query_params.get('tag', '')
        tags = Tag.objects.filter(title__istartswith=tag)
        tags = tags.order_by('-total_posts')[:100]
        time_24_hours_ago = timezone.now() - datetime.timedelta(days=1)

        # Select first 100 posts assume that search output will be short
        pinned = self.request.user.pinned
        #pinned = pinned.filter(tags__in=tags, expired_at__gte=timezone.now())
        pinned = pinned.filter(created_at__lt=time_24_hours_ago)
        #pinned = pinned.order_by('-expired_at').distinct()[:100]
        pinned = pinned.order_by('created_at').distinct()[:100]


        #posts = Post.objects.filter(tags__in=tags, expired_at__gte=timezone.now())
        posts = Post.objects.filter(created_at__lt=time_24_hours_ago)
        posts = posts.exclude(pk__in={it.pk for it in pinned}).distinct()
        #posts = posts.order_by('-expired_at')
        posts = posts.order_by('created_at')

        return posts
