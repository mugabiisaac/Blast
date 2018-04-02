import datetime

import itertools
from django.utils import timezone
from django.core.urlresolvers import reverse_lazy
from django.test import TestCase
from rest_framework import status

from core.tests import BaseTestCase, create_file
from countries.models import Country
from reports.models import Report
from users.models import User, Follower, UserSettings, PinnedPosts
from posts.models import Post, PostComment, PostVote
from posts.tasks import send_expire_notifications, _get_post_for_users_push_list


class AnyPermissionTest(TestCase):
    """
    Permissions test for unauthorized user
    """

    fixtures = ('countries.json',)

    def setUp(self):
        user = User.objects.create_user(phone='+1234567', password='123456', username='username')

        file = create_file('test.png')
        self.post = Post.objects.create(user=user, video=file)

    def test_any_view_posts(self):
        url = reverse_lazy('post-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_any_create_post(self):
        url = reverse_lazy('post-list')
        response = self.client.post(url, data={
            'video': create_file('test_01.png'),
            'user': 1,
            'text': 'spam'
        })

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Post.objects.count(), 1)

    def test_any_delete_post(self):
        url = reverse_lazy('post-detail', kwargs={'pk': self.post.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Post.objects.count(), 1)


class PostTest(BaseTestCase):
    def setUp(self):
        super().setUp()

        file = create_file('test.png')
        self.post = Post.objects.create(user=self.user, text='some_text', video=file)

    def test_create_post(self):
        url = reverse_lazy('post-list')

        response = self.client.post(url, {
            'text': 'text',
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['is_anonymous'], False)
        self.assertEqual(response.data['author']['username'], self.user.username)

    def test_create_anonymous_post(self):
        url = reverse_lazy('post-list')

        response = self.client.post(url, {
            'text': 'text',
            'is_anonymous': True
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['is_anonymous'], True)
        self.assertEqual(response.data['author']['username'], 'Anonymous')

    def test_hide_post(self):
        url = reverse_lazy('post-detail', kwargs={'pk': self.post.pk})

        response = self.client.put(url + 'hide/', content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(self.user.hidden_posts.filter(pk=self.post.pk).exists())

        response = self.client.put(url + 'show/', content_type='application/json')
        self.user.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(self.user.hidden_posts.filter(pk=self.post.pk).exists())

    # TODO: Add permission test
    def test_delete_post(self):
        url = reverse_lazy('post-detail', kwargs={'pk': self.post.pk})

        self.client.delete(url, content_type='application/json')

        self.assertEqual(Post.objects.all().count(), 0)

    def test_get_my_private_post(self):
        self.user.is_private = True
        self.user.save()

        url = reverse_lazy('post-detail', kwargs={'pk': self.post.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.post.pk)


class TestAnonymousPost(BaseTestCase):
    def setUp(self):
        super().setUp()

        url = reverse_lazy('post-list')
        response = self.client.post(url, data={
            'video': create_file('test_01.png'),
            'user': self.user.pk,
            'text': 'spam',
            'is_anonymous': True,
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.post = Post.objects.get(pk=response.data['id'])

    def test_get_anonymous_post(self):
        url = reverse_lazy('post-list')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['author']['username'], 'Anonymous')
        self.assertEqual(response.data['results'][0]['author']['avatar'], None)

        url = reverse_lazy('post-detail', kwargs={'pk': self.post.pk})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['author']['username'], 'Anonymous')
        self.assertEqual(response.data['author']['avatar'], None)

    def test_is_anonymous_post_pinned(self):
        """
        Checks is_anonymous post in pinned list.
        :return:
        """
        self.assertTrue(self.user.pinned_posts.filter(pk=self.post.pk).exists())


class TestIsPinnedPost(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.post = Post.objects.create(user=self.user)
        PinnedPosts.objects.create(user=self.user, post=self.post)

    def test_is_pinned_flag(self):
        url = reverse_lazy('post-list')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['is_pinned'], True)


class CommentTest(BaseTestCase):
    url = reverse_lazy('comment-list')

    def setUp(self):
        super().setUp()
        file = create_file('filename.txt')
        self.post = Post.objects.create(video=file, user=self.user, text='text')

    def test_create_comment(self):
        text = 'comment text'
        response = self.client.post(self.url, data={
            'post': self.post.pk,
            'text': text
        })

        comment = PostComment.objects.get(user=self.user)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(comment.text, text)
        self.assertEqual(comment.user, self.user)
        self.assertEqual(comment.post, self.post)
        self.assertIsNotNone(response.data.get('author'))

    def test_create_reply_comment(self):
        parent_text = 'parent comment text'
        reply_text = 'reply comment text'
        response = self.client.post(self.url, data={
            'post': self.post.pk,
            'text': parent_text
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['text'], parent_text)
        self.assertEqual(response.data['post'], self.post.pk)

        parent_id = response.data['id']
        response = self.client.post(self.url, data={
            'parent': parent_id,
            'post': self.post.pk,
            'text': reply_text
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(self.url + '?parent=' + str(parent_id))
        results = response.data['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['text'], reply_text)

    # TODO: Check permissions on delete method
    def test_delete_comment(self):
        text = 'comment text'
        comment = PostComment.objects.create(post=self.post, user=self.user, text=text)

        url = reverse_lazy('comment-detail', kwargs={'pk': comment.pk})
        self.client.delete(url, content_type='application/json')

        self.assertEqual(PostComment.objects.filter(post=self.post, user=self.user).count(), 0)

    def test_filter_comments(self):
        url = reverse_lazy('comment-list')
        parent = PostComment.objects.create(post=self.post, text='parent', user=self.user)

        for i in range(5):
            PostComment.objects.create(parent=parent, text=str(i),
                                       post=self.post, user=self.user)

        # Should return all comments
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 6)

        results = response.data['results']
        self.assertEqual(len(results), 6)

        groups = {}
        for k, v in itertools.groupby(results, lambda x: x['parent']):
            groups[k] = list(v)

        self.assertEqual(len(groups[None]), 1)
        self.assertEqual(len(groups[parent.pk]), 5)

        # Should return only parent comments
        response = self.client.get(url + '?parent__is_null=true')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], parent.pk)
        self.assertEqual(results[0]['id'], parent.post_id)

        # Should return only child comments
        response = self.client.get(url + '?parent__is_null=False')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']

        self.assertEqual(len(results), 5)
        results = sorted(results, key=lambda x: x['id'])
        for i in range(5):
            self.assertEqual(results[i]['text'], str(i))


class AuthorizedPermissionsTest(BaseTestCase):
    def setUp(self):
        super().setUp()

        self.user2 = User.objects.create_user(phone='+1231231',
                                              password='123456',
                                              username='user2')

        file = create_file('test.png')
        self.post = Post.objects.create(user=self.user2, text='some text', video=file)

    def test_other_get_posts(self):
        url = reverse_lazy('post-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_authorized_create_post(self):
        url = reverse_lazy('post-list')

        video = create_file('test.png', False)

        response = self.client.post(url, data={
            'video': video,
            'user': self.user.pk,
            'text': 'text'
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Post.objects.count(), 2)

    def test_authorized_delete_post(self):
        """
        self.user cannot delete post of self.user2
        """
        url = reverse_lazy('post-detail', kwargs={'pk': self.post.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Post.objects.count(), 1)


class VoteTest(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.user.is_private = True
        self.user.save()
        self.post = Post.objects.create(user=self.user)
        self.expired_at = self.post.expired_at

        self.url = reverse_lazy('post-detail', kwargs={'pk': self.post.pk})

    def test_vote_post(self):
        response = self.put_json(self.url + 'vote/')

        self.post.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.post.voted_count, 1)
        self.assertEqual(self.post.downvoted_count, 0)
        self.assertEqual(self.post.expired_at, self.expired_at + datetime.timedelta(minutes=5))

        url = reverse_lazy('post-list') + 'voted/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data.get('results')), 1)

        result = response.data.get('results')[0]
        self.assertEqual(result['id'], self.post.id)
        self.assertEqual(result['author']['username'], self.user.username)

    def test_downvote_post(self):
        response = self.put_json(self.url + 'downvote/')

        self.post.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.post.voted_count, 0)
        self.assertEqual(self.post.downvoted_count, 1)
        self.assertEqual(self.post.expired_at, self.expired_at - datetime.timedelta(minutes=10))

        url = reverse_lazy('post-list') + 'downvoted/'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data.get('results')), 1)

        result = response.data.get('results')[0]
        self.assertEqual(result['id'], self.post.id)
        self.assertEqual(result['author']['username'], self.user.username)

    def test_downvote_min_time(self):
        """Should not change expired_at for post with little expired_at"""
        expired_at = timezone.now() + datetime.timedelta(minutes=5)  # FIXME: hardcoded value
        self.post.expired_at = expired_at
        self.post.save()

        url = reverse_lazy('post-downvote', kwargs={'pk': self.post.pk})
        response = self.put_json(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.post.refresh_from_db()
        self.assertEqual(self.post.expired_at, expired_at)

    def test_downvote_time(self):
        """Should set expired_at time to 10 min for post with soon expired_at"""
        extra_time_in_minutes = 3
        expired_at = timezone.now() + datetime.timedelta(minutes=10 + extra_time_in_minutes)  # FIXME: hardcoded value
        self.post.expired_at = expired_at
        self.post.save()

        url = reverse_lazy('post-downvote', kwargs={'pk': self.post.pk})
        response = self.put_json(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.post.refresh_from_db()

        should_be = timezone.now() + datetime.timedelta(minutes=10)
        delta = (should_be - self.post.expired_at).total_seconds()

        self.assertLess(delta, 10)
        self.assertGreaterEqual(delta, 0)

        delta = (expired_at - self.post.expired_at).total_seconds()
        self.assertEqual(round(delta), extra_time_in_minutes * 60)

    def test_twice_vote(self):
        """Checks votes counter for twice vote request"""
        self.post.refresh_from_db()
        self.assertEqual(self.post.voted_count, 0)
        url = reverse_lazy('post-vote', kwargs={'pk': self.post.pk})

        response = self.put_json(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.post.refresh_from_db()
        self.assertEqual(self.post.voted_count, 1)

        response = self.put_json(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.post.refresh_from_db()
        self.assertEqual(self.post.voted_count, 1)


class ReportTest(BaseTestCase):
    text = 'report text'

    def setUp(self):
        super().setUp()

        video = create_file('test.png', False)

        self.post = Post.objects.create(user=self.user, video=video, text='text')

    def test_post_report(self):
        url = reverse_lazy('post-report', kwargs={'pk': self.post.pk})

        response = self.put_json(url, data={'reason': Report.OTHER, 'text': self.text})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Report.objects.count(), 1)

        report = Report.objects.get(user=self.user)
        self.assertEqual(report.reason, Report.OTHER)
        self.assertEqual(report.text, self.text)
        self.assertEqual(report.object_pk, self.post.pk)
        self.assertEqual(report.user_id, self.user.pk)

    def test_comment_report(self):
        comment = PostComment.objects.create(user=self.user, post=self.post, text='fuuuu')

        url = reverse_lazy('comment-report', kwargs={'pk': comment.pk})
        response = self.put_json(url, data={'reason': Report.BULLYING, 'text': self.text})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(Report.objects.all().count(), 1)

        report = Report.objects.get(user=self.user)
        self.assertEqual(report.reason, report.BULLYING)
        self.assertEqual(report.object_pk, comment.pk)
        self.assertEqual(report.user_id, self.user.pk)


class PinPost(BaseTestCase):
    posts_count = 10

    def setUp(self):
        super().setUp()

        video = create_file('test.png', False)

        self.post = Post.objects.create(user=self.user, video=video, text='text')

    def test_pin_post(self):
        url = reverse_lazy('post-detail', kwargs={'pk': self.post.pk}) + 'pin/'

        self.put_json(url)

        self.user.refresh_from_db()
        self.assertEqual(self.user.pinned_posts.count(), 1)

    def test_unpin_post(self):
        url = reverse_lazy('post-detail', kwargs={'pk': self.post.pk})

        self.put_json(url + 'pin/')
        self.user.refresh_from_db()
        self.assertEqual(self.user.pinned_posts.count(), 1)

        self.put_json(url + 'unpin/')
        self.user.refresh_from_db()
        self.assertEqual(self.user.pinned_posts.count(), 0)

    def tes_get_pinned_posts(self):
        url = reverse_lazy('post-list') + '?pinned'

        video = create_file('test.mp4', False)
        for it in range(10):
            Post.objects.create(user=self.user, video=video, text='text')

        self.put_json(reverse_lazy('post-detail', kwargs={'pk': self.post.pk}) + 'pin/')
        self.put_json(url)

        response = self.get(url)
        self.assertEqual(len(response.result), 1)
        self.assertEqual(response.result[0]['pk'], self.post.pk)


class FeedsTest(BaseTestCase):
    url = reverse_lazy('feed-list')

    def setUp(self):
        super().setUp()

        posts = []
        for it in range(10):
            posts.append(Post(user=self.user))

        Post.objects.bulk_create(posts)
        posts = Post.objects.all()
        self.posts = posts

    def test_feeds(self):
        response = self.client.get(self.url)
        self.assertEqual(len(response.data['results']), len(self.posts))

    def test_hidden_post(self):
        self.user.hidden_posts.add(self.posts[5])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), len(self.posts) - 1)

        should_be_hidden = self.posts[5].pk
        ids = [it['id'] for it in response.data['results']]

        self.assertNotIn(should_be_hidden, ids)

    def test_hide_voted_post(self):
        PostVote.objects.create(user=self.user, post=self.posts[0])

        response = self.client.get(self.url)

        self.assertEqual(len(response.data['results']), len(self.posts) - 1)

        should_be_hidden = self.posts[0].pk
        ids = [it['id'] for it in response.data['results']]

        self.assertNotIn(should_be_hidden, ids)

    def test_voted_and_hidden(self):
        PostVote.objects.create(user=self.user, post=self.posts[0])
        self.user.hidden_posts.add(self.posts[1])

        response = self.client.get(self.url)

        self.assertEqual(len(response.data['results']), len(self.posts) - 2)

        should_be_hidden = [self.posts[0].pk, self.posts[1]]
        self.assertNotIn(should_be_hidden[0], response.data['results'])
        self.assertNotIn(should_be_hidden[1], response.data['results'])


class VotersList(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.post = Post.objects.create(text='some text', user=self.user)

        country = Country.objects.get(pk=1)
        self.user1 = User.objects.create_user(phone='1', username='1', password='1', country=country)
        self.user2 = User.objects.create_user(phone='2', username='2', password='2', country=country)

        PostVote.objects.create(user=self.user, post=self.post, is_positive=True)
        PostVote.objects.create(user=self.user1, post=self.post, is_positive=True)
        PostVote.objects.create(user=self.user2, post=self.post, is_positive=False)

        Follower.objects.create(follower=self.user, followee=self.user1)
        # self.user.followees.add(self.user1)

    def test_votes_list(self):
        url = reverse_lazy('post-detail', kwargs={'pk': self.post.pk})
        url += 'voters/'

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)
        # TODO: Improve and check user[0]
        self.assertEqual(response.data['results'][1]['username'], '1')
        self.assertEqual(response.data['results'][1]['is_followee'], True)


class ExpiredNotificationsTest(BaseTestCase):
    def setUp(self):
        super().setUp()

        self.user1 = self.generate_user('voter')
        self.user2 = self.generate_user('downvoter')

        UserSettings.objects.all().update(notify_upvoted_blasts=True,
                                          notify_downvoted_blasts=True,
                                          notify_pinned_blasts=True)

    def test_check_notify_list_owners(self):
        expired_at = timezone.now() + datetime.timedelta(minutes=5)
        post1 = Post.objects.create(user=self.user, expired_at=expired_at)
        post2 = Post.objects.create(user=self.user1, expired_at=expired_at)
        post3 = Post.objects.create(user=self.user2, expired_at=expired_at)
        post4 = Post.objects.create(user=self.user2)

        PostVote.objects.create(user=self.user1, post=post1, is_positive=True)
        PostVote.objects.create(user=self.user2, post=post1, is_positive=True)
        PostVote.objects.create(user=self.user1, post=post2, is_positive=True)
        PostVote.objects.create(user=self.user2, post=post2, is_positive=False)

        # Pinned and voted
        # User pin and vote post, this post will be include in 'pinned' set only.
        PostVote.objects.create(user=self.user1, post=post3, is_positive=True)
        PinnedPosts.objects.create(user=self.user1, post=post3)

        # Owner pin his own post.
        # This post will not be included in 'pinned' set, but will be in 'owner' set.
        PinnedPosts.objects.create(user=self.user2, post=post3)

        should_be = {
            'owner': {
                post1.pk: {self.user.pk},
                post2.pk: {self.user1.pk},
                post3.pk: {self.user2.pk}
            },
            'pinned': {
                post3.pk: {self.user1.pk}
            },
            'upvote': {
                post1.pk: {self.user1.pk, self.user2.pk},
            },
            'downvote': {
                post2.pk: {self.user2.pk}
            }
        }

        result = _get_post_for_users_push_list()

        self.assertEqual(result, should_be)

    def test_check_notify_list_case_01(self):
        expired_at = timezone.now() + datetime.timedelta(minutes=5)

        post = Post.objects.create(user=self.user, expired_at=expired_at)

        PinnedPosts.objects.create(user=self.user1, post=post)

        result = _get_post_for_users_push_list()

        should_be = {
            'owner': {post.pk: {self.user.pk}},
            'pinned': {post.pk: {self.user1.pk}},
            'upvote': {},
            'downvote': {}
        }

        self.assertEqual(result, should_be)
