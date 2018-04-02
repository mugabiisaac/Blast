import json

import redis
from django.test import TestCase
from django.core.urlresolvers import reverse_lazy, reverse
from django.utils import timezone
from push_notifications.models import APNSDevice
from rest_framework import status

from countries.models import Country
from notifications.models import FollowRequest, Notification
from posts.models import Post
from reports.models import Report
from smsconfirmation.models import PhoneConfirmation
from tags.models import Tag
from users.models import User, UserSettings, Follower, BlockedUsers
from core.tests import BaseTestCase
from users.utils import mark_followee, mark_requested


class CheckUsernameAndPasswordTest(BaseTestCase):

    url = reverse_lazy('user-check')

    def test_taken_phone_and_username(self):
        data = {
            'username': self.username,
            'phone': self.phone
        }

        response = self.client.get(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('phone')[0], 'This phone is taken')
        self.assertEqual(response.data.get('username')[0], 'This username is taken')

    def test_taken_phone(self):
        data = {
            'username': self.username + '_555',
            'phone': self.phone
        }

        response = self.client.get(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNotNone(response.data.get('phone'))
        self.assertIsNone(response.data.get('username'))

    def test_untaken_phone_and_username(self):
        data = {
            'username': self.username + '_555',
            'phone': self.phone + '999'
        }

        response = self.client.get(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class RegisterTest(TestCase):

    fixtures = ('countries',)
    url = reverse_lazy('user-list')
    phone = '+79521234567'
    username = 'username'
    password = 'password123'
    country = 1

    def setUp(self):
        self.confirmation = PhoneConfirmation.objects.create(phone=self.phone,
                                                             is_confirmed=True,
                                                             request_type=PhoneConfirmation.REQUEST_PHONE)

    def test_user_unconfirmed_phone(self):
        data = {
            'phone': self.phone + '1',
            'username': self.username,
            'password': self.password,
            'country': self.country
        }

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # TODO: Check that user does not exist

    def test_user_register(self):
        """Should register user"""
        data = {
            'phone': self.phone,
            'username': self.username,
            'password': self.password,
            'country': self.country,
        }

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(phone=self.phone)

        self.assertEqual(self.phone, user.phone)
        self.assertEqual(self.username, user.username)
        self.assertTrue(user.check_password(self.password))

        # Check user settings
        settings = UserSettings.objects.get(user=user)

        # Useless assert
        self.assertEqual(settings.user.pk, user.pk)

    def test_min_password_length(self):
        """Checks that password length greater or equal 6"""

        data = {
            'phone': self.phone,
            'username': self.username,
            'password': '1234',
            'country': self.country
        }

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_password(self):
        data = {
            'phone': self.phone,
            'username': 'bob_dilan',
            'country': self.country
        }

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_username_max_length(self):
        """Checks that username length less than 15"""
        data = {
            'phone': self.phone,
            'username': 'string'*10,
            'password': 'cool_password',
            'country': self.country
        }

        response = self.client.post(self.url, data)

        user = None
        try:
            user = User.objects.get(phone=self.phone)
        except User.DoesNotExist:
            pass

        self.assertIsNone(user)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_username_taken(self):
        phone = self.phone + '1'
        country = Country.objects.get(pk=self.country)
        User.objects.create_user(username=self.username, password=self.password,
                                 country=country, phone=self.phone)

        self.confirmation = PhoneConfirmation.objects.create(phone=phone,
                                                             is_confirmed=True,
                                                             request_type=PhoneConfirmation.REQUEST_PHONE)
        data = {
            'phone': phone,
            'username': self.username.upper(),
            'password': self.password,
            'country': self.country,
        }

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['username'][0], 'This username is taken')


class UpdateProfileTest(BaseTestCase):

    bio = 'user bio text'
    website = 'www.google.com'
    fullname = 'Tiler'
    birthday = timezone.now()

    def setUp(self):
        super().setUp()

        self.url = reverse('user-profile')

    def test_edit_optional_data(self):
        # avatar = create_file('avatar.png', False)
        data = {
            'bio': self.bio,
            'website': self.website,
            'fullname': self.fullname,
            'is_private': not self.user.is_private,
            'is_safe_mode': not self.user.is_safe_mode,
            'avatar': None,
            'save_original_content': not self.user.save_original_content
        }

        response = self.client.patch(self.url, json.dumps(data),
                                     content_type='application/json')

        self.user.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.bio, self.bio)
        self.assertEqual(self.user.avatar.name, '')
        self.assertEqual(self.user.website, self.website)
        self.assertEqual(self.user.is_private, data['is_private'])
        self.assertEqual(self.user.is_safe_mode, data['is_safe_mode'])
        self.assertEqual(self.user.save_original_content, data['save_original_content'])
        self.assertEqual(self.user.fullname, self.fullname)

    def test_edit_private_data(self):
        data = json.dumps({
            'birthday': str(self.birthday),
            'gender': User.GENDER_FEMALE,
        })

        response = self.client.patch(self.url, data, content_type='application/json')

        self.user.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.gender, User.GENDER_FEMALE)
        self.assertEqual(self.user.birthday, self.birthday)


class TestResetPasswordAuthorized(BaseTestCase):
    """Test case for authorized user"""

    url = reverse_lazy('user-password-auth')
    new_password = 'new_password'

    def test_change_password(self):
        data = {
            'old_password': self.password,
            'password1': self.new_password,
            'password2': self.new_password
        }

        response = self.patch_json(self.url, data)

        self.user.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(self.user.check_password(self.new_password))


class TestChangePhoneNumber(BaseTestCase):
    url = reverse_lazy('user-phone')
    new_phone = '+79551234567'

    def setUp(self):
        super().setUp()

        PhoneConfirmation.objects.create(phone=self.new_phone, is_confirmed=True,
                                         request_type=PhoneConfirmation.REQUEST_PHONE)

    def test_change_phone_wrong_password(self):
        data = {
            'password': 'wrong password',
            'current_phone': 'wrong phone',
            'new_phone': self.new_phone
        }

        response = self.patch_json(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNotNone(response.data['password'])
        self.assertIsNotNone(response.data['current_phone'])

        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, self.phone)

    def test_change_phone(self):
        # TODO: Check "bad" cases
        data = {
            'password': self.password,
            'current_phone': self.phone,
            'new_phone': self.new_phone,
        }

        response = self.patch_json(self.url, data)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.phone, self.new_phone)

    def test_change_unconfirmed_phone(self):
        data = {
            'passwrod': self.password,
            'current_phone': self.phone + '1',
            'new_phone': self.new_phone + '1'
        }

        response = self.patch_json(self.url, data)

        self.user.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.user.phone, self.phone)

    def test_change_phone_taken_number(self):
        phone = self.phone + '1'
        User.objects.create_user(username=self.username + '1', phone=phone, password=self.password)
        data = {
            'password': self.password,
            'current_phone': self.phone,
            'new_phone': phone
        }

        response = self.patch_json(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNotNone(response.data.get('new_phone'))


class TestUserSettings(BaseTestCase):

    def test_user_settings(self):
        url = reverse_lazy('user-settings')

        settings = UserSettings.objects.get(user=self.user)
        data = {
            'notify_my_blasts': not settings.notify_my_blasts,
            'notify_upvoted_blasts': not settings.notify_upvoted_blasts,
            'notify_downvoted_blasts': not settings.notify_downvoted_blasts,
            'notify_pinned_blasts': not settings.notify_pinned_blasts,

            'notify_votes': not settings.notify_votes,

            'notify_new_followers': UserSettings.OFF,
            'notify_comments': UserSettings.OFF,
            'notify_reblasts': UserSettings.EVERYONE,
        }

        response = self.patch_json(url, data)

        settings.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEquals(settings.notify_my_blasts, data['notify_my_blasts'])
        self.assertEquals(settings.notify_upvoted_blasts, data['notify_upvoted_blasts'])
        self.assertEquals(settings.notify_downvoted_blasts, data['notify_downvoted_blasts'])
        self.assertEquals(settings.notify_pinned_blasts, data['notify_pinned_blasts'])
        self.assertEquals(settings.notify_votes, data['notify_votes'])
        self.assertEquals(settings.notify_new_followers, data['notify_new_followers'])
        self.assertEquals(settings.notify_comments, data['notify_comments'])
        self.assertEquals(settings.notify_reblasts, data['notify_reblasts'])


class TestUserFollower(BaseTestCase):
    def setUp(self):
        super().setUp()

        self.other = User.objects.create_user(username='other_user',
                                              password=self.password, phone='-7')

    def test_user_follow(self):
        url = reverse_lazy('user-follow', kwargs={'pk': self.other.pk})

        response = self.client.put(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.other.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(self.other.followers.count(), 1)
        self.assertEqual(Follower.objects.filter(followee=self.other,
                                                 follower=self.user).count(), 1)

        # Check user list
        url = reverse_lazy('user-list')

        response = self.client.get(url)
        users = {it['id']: it for it in response.data['results']}

        user = users[self.user.pk]
        other = users[self.other.pk]

        self.assertEqual(user['followers'], 0)  # Nobody
        self.assertEqual(user['following'], 2)  # Anonymous and self.user

        self.assertEqual(other['followers'], 1)  # self.user only
        self.assertEqual(other['following'], 1)  # Anonymous

    def test_user_unfollow(self):
        # self.other.followers.add(Follower(follower=self.user, followee=self.other))

        url = reverse_lazy('user-unfollow', kwargs={'pk': self.other.pk})
        response = self.client.put(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.other.followers.count(), 1)


class TestFollowersList(BaseTestCase):
    def setUp(self):
        super().setUp()

        self.other1 = User.objects.create_user(username='username2', phone='+79111234567',
                                               password='password', country=self.country)
        self.other2 = User.objects.create_user(username='username3', phone='+79111234568',
                                               password='password', country=self.country)

        Follower.objects.create(follower=self.other1, followee=self.user)
        Follower.objects.create(follower=self.user, followee=self.other2)

        self.posts = [{
                'user': self.other1,
                'total': 3
            }, {
                'user': self.other2,
                'total': 1,
            }
        ]

        for post in self.posts:
            for it in range(post['total']):
                Post.objects.create(user=post['user'], text='text')

    def test_followers_is_followee_flag(self):
        url = reverse_lazy('user-detail', kwargs={'pk': self.user.pk})

        url += 'followers/'

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        result = response.data.get('results')

        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]['is_followee'])
        self.assertEqual(result[0]['username'], 'username2')

    def test_following_list(self):
        url = reverse_lazy('user-detail', kwargs={'pk': self.user.pk})
        url += 'following/'

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        result = response.data.get('results')
        self.assertEqual(len(result), 2)

        self.assertTrue(result[1]['is_followee'])
        self.assertEqual(result[1]['username'], 'username3')

    def test_followers_posts(self):
        Follower.objects.create(follower=self.other2, followee=self.user)

        url = reverse_lazy('user-followers', kwargs={'pk': self.user.pk})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data.get('results')

        for it in results:
            user = it['username']
            data = filter(lambda it: it['user'].username == user, self.posts)
            data = list(data)[0]
            self.assertIsNotNone(it.get('posts'))
            self.assertEqual(len(it['posts']), data['total'])

            for post in it['posts']:
                self.assertEqual(post['user'], it['id'])


class TestFollowingLastPosts(BaseTestCase):
    usernames = ['username1', 'username2', 'username3']

    post_count = 3

    def setUp(self):
        super().setUp()

        for username in self.usernames:
            user = self.generate_user(username)
            for i in range(self.post_count * 2):  # FIXME: magic number
                Post.objects.create(text='text {} {}'.format(i, username), user=user)

            url = reverse_lazy('user-follow', kwargs={'pk': user.pk})
            response = self.client.put(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Unfollow anonymous
        url = reverse_lazy('user-unfollow', kwargs={'pk': User.objects.anonymous_id})
        self.client.put(url)

    def test_empty_following_list(self):
        url = reverse_lazy('user-following', kwargs={'pk': self.user.pk})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        results = data['results']

        self.assertEqual(data['count'], len(self.usernames))
        self.assertEqual(len(results), len(self.usernames))

        for it in results:
            user = it['username']
            user = User.objects.filter(username=user)
            posts = it['posts']
            posts_db = Post.objects.filter(user=user).order_by('-created_at')[:self.post_count]

            self.assertEqual(len(posts), self.post_count)
            for i in range(self.post_count):
                self.assertEqual(posts[i]['id'], posts_db[i].id)


class TestPrivateUserUnfollow(BaseTestCase):
    def setUp(self):
        super().setUp()

        self.private = self.generate_user()
        self.private.is_private = True
        self.private.save()

    def test_follow_crash(self):
        """
        1. self.user sends follow request to self.private
        2. self.private accepts request
        3. self.user unfollow self.private and gets 500.
        :return:
        """
        # 1
        url = reverse_lazy('user-detail', kwargs={'pk': self.private.pk})
        url += 'follow/'

        response = self.put_json(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Follower.objects.filter(follower=self.user, followee=self.private).exists())

        # 2
        self.login(self.private)
        follow_request = FollowRequest.objects.get(followee=self.private, follower=self.user)
        url = reverse_lazy('followrequest-detail', kwargs={'pk': follow_request.pk})

        response = self.put_json(url, {"accept": True})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(Follower.objects.filter(follower=self.user, followee=self.private).exists())
        self.assertFalse(FollowRequest.objects.filter(follower=self.user, followee=self.private).exists())

        # 3
        self.login(self.user)
        url = reverse_lazy('user-detail', kwargs={'pk': self.private.pk})
        url += 'unfollow/'

        response = self.put_json(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Follower.objects.filter(follower=self.user, followee=self.private).exists())


class TestBlockUser(BaseTestCase):
    def setUp(self):
        super().setUp()

        self.blocked = self.generate_user()

    def test_block_user(self):
        url = reverse_lazy('user-detail', kwargs={'pk': self.blocked.pk})

        response = self.put_json(url + 'block/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(BlockedUsers.objects.filter(user=self.user, blocked=self.blocked).exists())

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('is_blocked'), True)

    def test_unblock_user(self):
        BlockedUsers.objects.create(user=self.user, blocked=self.blocked)
        url = reverse_lazy('user-detail', kwargs={'pk': self.blocked.pk})

        response = self.put_json(url + 'unblock/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(BlockedUsers.objects.filter(user=self.user, blocked=self.blocked).exists())

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('is_blocked'), False)


class TestUserSearch(BaseTestCase):
    url = reverse_lazy('user-search-list')

    def setUp(self):
        super().setUp()

        self.other = self.generate_user()

        for it in range(5):
            Post.objects.create(user=self.user)

        self.posts = list(Post.objects.all())

        # Clear test
        key = User.redis_posts_key(self.user.pk)
        self.r.delete(key)

    def test_visibility_of_private_post(self):
        """Should show posts for owner private accaunt"""
        url = self.url + '?search={}'.format(self.username)

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        posts = response.data['results'][0]['posts']
        self.assertEqual(len(posts), 3)

    def test_search_empty_result(self):
        """Should returns empty list for non existing user"""
        url = self.url + '?search={}'.format('000')

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_search(self):
        """Should find user by username"""
        url = self.url + '?search={}'.format(self.user.username)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['username'], self.user.username)

        posts = results[0]['posts']

        self.assertEqual(len(posts), 3)
        for i in range(len(posts)):
            self.assertEqual(posts[i]['id'], self.posts[i].pk)

        # Vote for last post
        vote_url = reverse_lazy('post-vote', kwargs={'pk': self.posts[-1].pk})

        response = self.put_json(vote_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # check new order
        new_order = [self.posts[-1], self.posts[0], self.posts[1]]

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        posts = response.data['results'][0]['posts']
        # for i in range(len(new_order)):
        #     self.assertEqual(posts[i]['id'], new_order[i].pk)

    # TODO: Write test
    def test_search_feeds(self):
        page_size = 25
        url = reverse_lazy('user-search-feeds')

        users = [self.generate_user() for it in range(50)]

        response = self.client.get(url + '?page_size={}'.format(page_size))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(len(results), page_size)

    def test_search_feeds_full_page(self):
        page_size = 50
        url = reverse_lazy('user-search-feeds')

        users = [self.generate_user() for it in range(50)]

        response = self.client.get(url + '?page_size={}'.format(page_size))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(len(results), page_size)


class TestUserSearchOrder(BaseTestCase):
    url = reverse_lazy('user-search-list')

    def setUp(self):
        super().setUp()

        self.users = [
            {'username': 'test_aaa', 'posts': 5},
            {'username': 'test_bbb', 'posts': 4},
            {'username': 'test_ccc', 'posts': 4},
            {'username': 'test_aab', 'posts': 3},
            {'username': 'test_aac', 'posts': 3},
            {'username': 'test_aad', 'posts': 2},
            {'username': 'test_aae', 'posts': 1},
            {'username': 'test_aaf', 'posts': 1}
        ]

        r = redis.StrictRedis(host='localhost', port=6379, db=0)
        for u in self.users:
            user = self.generate_user(username=u['username'])

            # Clear cache
            key = User.redis_posts_key(user.pk)
            r.delete(key)

            for post in range(u['posts']):
                Post.objects.create(user=user, text='text')

    def test_search_order(self):
        db_users = User.objects.filter(username__in={it['username'] for it in self.users})
        db_users = {it.username: it for it in db_users}

        for user in self.users:
            db_user = db_users[user['username']]
            self.assertLessEqual(db_user.search_range, 4)
            self.assertEqual(db_user.search_range, min(user['posts'], 4))

        url = self.url + '?search=test'
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data['results']

        self.assertEqual(len(results), len(self.users))

        for i in range(len(results)):
            user = self.users[i]
            res = response.data['results'][i]

            self.assertEqual(user['username'], res['username'])


class TestAnonymousPost(BaseTestCase):
    def setUp(self):
        super().setUp()

    def test_anonymous_post(self):
        url = reverse_lazy('post-list')

        response = self.client.post(url, {
            'is_anonymous': True,
            'text': 'text'
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['author']['username'], 'Anonymous')

        self.assertEqual(Post.objects.all().count(), 1)
        post = Post.objects.all().first()

        self.assertEqual(post.text, 'text')
        self.assertEqual(post.user.pk, User.objects.anonymous_id)


class TestCache(BaseTestCase):
    def setUp(self):
        super().setUp()

    def test_blasts_count(self):
        """
        Checks blasts count for user with "cold" cache.
        :return:
        """
        self.clear_cache()

        count = 5
        for it in range(count):
            Post.objects.create(user=self.user, text='text')

        self.assertEqual(self.user.blasts_count(), count)

        for it in range(count):
            Post.objects.create(user=self.user, text='text')

        self.clear_cache()

        self.assertEqual(self.user.blasts_count(), count * 2)

    def test_followers_count(self):
        count = 5
        users = []
        for it in range(count):
            users.append(self.generate_user())

        self.clear_cache()

        self.assertEqual(self.user.following_count(), 1)  # Anonymous only
        self.assertEqual(self.user.followers_count(), 0)

        for it in users:
            Follower.objects.create(follower=it, followee=self.user)

        self.assertEqual(self.user.following_count(), 1)
        self.assertEqual(self.user.followers_count(), count)

        self.clear_cache()

        self.assertEqual(self.user.following_count(), 1)
        self.assertEqual(self.user.followers_count(), count)

        for it in Follower.objects.all():
            it.delete()

        self.assertEqual(self.user.followers_count(), 0)
        self.assertEqual(self.user.followers_count(), 0)

        self.clear_cache()

        self.assertEqual(self.user.followers_count(), 0)
        self.assertEqual(self.user.followers_count(), 0)


class ReportTest(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.other = self.generate_user('other')

    def test_report_route(self):
        url = reverse_lazy('user-report', kwargs={'pk': self.other.pk})

        text = 'text'
        response = self.put_json(url, data={'reason': Report.DUPLICATED_CONTENT, 'text': text})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        report = Report.objects.all()[0]
        self.assertEqual(report.reason, Report.DUPLICATED_CONTENT)
        self.assertEqual(report.text, text)
        self.assertEqual(report.user.pk, self.user.pk)
        self.assertEqual(report.object_pk, self.other.pk)


class ShareTest(BaseTestCase):
    def setUp(self):
        super().setUp()

        self.post = Post.objects.create(user=self.user, text='cool video! #tag')
        self.followers = {self.generate_user('follower{}'.format(it)) for it in range(10)}

        followers = []
        for f in self.followers:
            followers.append(Follower(followee=self.user, follower=f))
        Follower.objects.bulk_create(followers)

    def test_share_post(self):
        url = reverse_lazy('post-share', kwargs={'pk': self.post.pk})

        count = 5
        users = [it.pk for it in self.followers][:count]

        response = self.post_json(url, {'users': users})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notifications = list(Notification.objects.filter(user__in=users))

        self.assertEqual(len(notifications), count)
        notifications = {it.user_id: it for it in notifications}
        for pk in users:
            self.assertIn(pk, notifications)
            self.assertEqual(notifications[pk].type, Notification.SHARE_POST)
            self.assertEqual(notifications[pk].post_id, self.post.id)
            self.assertEqual(notifications[pk].text, Notification.TEXT_SHARE_POST)
            self.assertEqual(notifications[pk].user_id, pk)
            self.assertEqual(notifications[pk].other_id, self.user.pk)

    def test_share_tag(self):
        tag = Tag.objects.get(title='tag')
        url = reverse_lazy('tag-share', kwargs={'pk': tag.pk})

        count = 5
        users = [it.pk for it in self.followers][:count]
        response = self.post_json(url, {'users': users})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notifications = list(Notification.objects.filter(user__in=users))

        self.assertEqual(len(notifications), count)
        notifications = {it.user_id: it for it in notifications}
        for pk in users:
            self.assertIn(pk, notifications)
            self.assertEqual(notifications[pk].type, Notification.SHARE_TAG)
            self.assertEqual(notifications[pk].tag_id, tag.pk)
            self.assertEqual(notifications[pk].user_id, pk)
            self.assertEqual(notifications[pk].other_id, self.user.pk)
            self.assertEqual(notifications[pk].text, Notification.TEXT_SHARE_TAG.format(tag.pk))


class TestDevices(BaseTestCase):
    url = reverse_lazy('apns-device-list')

    id_1 = '4bbc959de41a9632af05244e84b35296b47906dad6d60824a8801ccaf23e9dc7'
    id_2 = '4bbb959de41a9632af05244e84b35296b47906dad6d60824a8801ccaf23e9dc7'

    def test_user_register_new_device(self):
        """
        User has no device in db and register new device
        """
        response = self.post_json(self.url, data={
            'registration_id': self.id_1
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['registration_id'], self.id_1)
        self.assertEqual(APNSDevice.objects.filter(user=self.user, registration_id=self.id_1).count(), 1)

    def test_same_user_register_same_device(self):
        """
        User has device in db and register it again
        :return:
        """
        # Same user with other device
        data = {
            'registration_id': self.id_1
        }

        response = self.post_json(self.url, data=data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(APNSDevice.objects.filter(user=self.user).count(), 1)

        # --- --- --- --- ---
        response = self.post_json(self.url, data=data)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(APNSDevice.objects.filter(user=self.user).count(), 1)
        self.assertEqual(APNSDevice.objects.filter(user=self.user, registration_id=self.id_1).count(), 1)

    def test_same_user_other_device(self):
        """
        User has some device in db and register new device
        """
        response = self.post_json(self.url, data={
            'registration_id': self.id_1
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(APNSDevice.objects.filter(user=self.user).count(), 1)

        response = self.post_json(self.url, data={
            'registration_id': self.id_2
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(APNSDevice.objects.filter(user=self.user).count(), 1)
        self.assertEqual(APNSDevice.objects.filter(user=self.user, registration_id=self.id_2).count(), 1)

    def test_other_user_register_same_device(self):
        other = self.generate_user()

        response = self.post_json(self.url, data={
            'registration_id': self.id_1
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(APNSDevice.objects.filter(user=self.user).count(), 1)

        self.login(other)

        response = self.post_json(self.url, data={
            'registration_id': self.id_1
        })

        # TODO: Check push notifincation
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(APNSDevice.objects.filter(user=self.user).count(), 0)
        self.assertEqual(APNSDevice.objects.filter(user=other).count(), 1)


class TestUtils(BaseTestCase):
    count = 5

    def setUp(self):
        super().setUp()

    def test_followee(self):
        users = []
        for i in range(self.count * 2):
            other = self.generate_user()
            users.append(other)

            if i < self.count:
                Follower.objects.create(follower=self.user, followee=other)

        users = [{'id': it.id} for it in users]
        mark_followee(users, self.user)

        for i, v in enumerate(users):
            if i < self.count:
                self.assertTrue(v['is_followee'])
            else:
                self.assertFalse(v['is_followee'])

    def test_follow_request(self):
        users = []
        for i in range(self.count * 2):
            other = self.generate_user(is_private=True)

            if i < self.count:
                FollowRequest.objects.create(followee=other, follower=self.user)

        users = [{'id': it.id} for it in users]
        mark_requested(users, self.user)

        for i, v in enumerate(users):
            if i < self.count:
                self.assertTrue(v['is_requested'])
            else:
                self.assertFals(v['is_requested'])


class TestPopularity(BaseTestCase):

    def setUp(self):
        super().setUp()

    def test_follower_up_down_popularity(self):
        user = self.generate_user()

        # Test up popularity
        url = reverse_lazy('user-follow', kwargs={'pk': user.pk})

        response = self.client.put(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        user.refresh_from_db()
        self.assertEqual(user.popularity, 1)

        # Test down popularity
        url = reverse_lazy('user-unfollow', kwargs={'pk': user.pk})
        response = self.client.put(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        user.refresh_from_db()
        self.assertEqual(user.popularity, 0)

    def test_post_up_down_popularity(self):
        # Test up popularity
        url = reverse_lazy('post-list')

        response = self.post_json(url, data={
            'text': 'Hello',
            'is_anonymous': False
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.user.refresh_from_db()
        self.assertEqual(self.user.popularity, 1)

        # Test down popularity
        url = reverse_lazy('post-detail', kwargs={'pk': response.data.get('id')})

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.user.refresh_from_db()
        self.assertEqual(self.user.popularity, 0)
