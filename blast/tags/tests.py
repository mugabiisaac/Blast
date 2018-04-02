import redis
from django.core.urlresolvers import reverse_lazy
from django.test import TestCase
from rest_framework import status

from core.tests import BaseTestCase
from posts.models import Post
from tags.models import Tag


class PostTagsTest(BaseTestCase):
    text = u'Post text with #hashtag1, #hashtag2, #hashtag3'

    def setUp(self):
        super().setUp()
        Tag.objects.create(title='hashtag1')

    def test_post_tags(self):
        post = Post.objects.create(text=self.text,
                                   user=self.user)

        tags = Tag.objects.all()

        self.assertEqual(len(tags), 3)
        self.assertEqual(len(post.tags.all()), 3)

        titles = [it.title for it in tags]
        self.assertIn('hashtag1', titles)
        self.assertIn('hashtag2', titles)
        self.assertIn('hashtag3', titles)

        for it in tags:
            self.assertEqual(it.total_posts, 1)

    def test_post_deleted(self):
        total = 5

        for it in range(total):
            Post.objects.create(text=self.text, user=self.user)

        tags = Tag.objects.all()
        for it in tags:
            self.assertEqual(it.total_posts, total)

        Post.objects.first().delete()

        tags = Tag.objects.all()
        for it in tags:
            self.assertEqual(it.total_posts, total - 1)

        Post.objects.all().delete()
        tags = Tag.objects.all()

        self.assertEqual(len(tags), 3)
        for it in tags:
            self.assertEqual(it.total_posts, 0)


class TagSearchTest(BaseTestCase):
    tags = ['testtag1', 'testtag2', 'testtag3', 'othertag']

    def setUp(self):
        super().setUp()

        text = ', '.join(['#' + it for it in self.tags])

        # Clear cache
        r = redis.StrictRedis(host='localhost', port=6379, db=0)
        for tag in self.tags:
            key = Tag.redis_posts_key(tag)
            r.delete(key)

        for it in range(5):
            post = Post(text=text, user=self.user)
            post.save()

        self.posts = list(Post.objects.all())
        self.user.pinned_tags.add(Tag.objects.get(title__iexact=self.tags[1]))
        self.user.save()

    def test_tag_search(self):
        """Should return unpinned tags"""
        url = reverse_lazy('tag-list') + '?search={}'.format('testtag')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        self.assertEqual(len(results), 3)

        for tag in ('testtag1', 'testtag3'):
            result = list(filter(lambda it: it['title'] == tag, results))
            self.assertEqual(len(result), 1)
            result = result[0]

            self.assertEqual(len(result['posts']), 3)

    def test_post_rank(self):
        """Checks that posts up to top in tag.posts after voting"""
        # Upvote last post
        post = self.posts[-1]
        url = reverse_lazy('post-vote', kwargs={'pk': post.pk})
        response = self.put_json(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Search first tag
        url = reverse_lazy('tag-list') + '?search={}'.format(self.tags[0])

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        result = response.data['results'][0]
        posts = result['posts']

        self.assertEqual(posts[0]['id'], post.pk)


class TestCacheHeatUp(BaseTestCase):
    tags = ['tag1', 'tag2', 'tag3']

    def setUp(self):
        super().setUp()

        text = ', '.join(['#' + it for it in self.tags])

        self.posts = []
        for it in range(5):
            post = Post.objects.create(user=self.user, text=text)
            self.posts.append(post)

    def test_heat_up(self):
        r = redis.StrictRedis(host='localhost', port=6379, db=0)
        for it in self.tags:
            key = Tag.redis_posts_key(it)
            self.assertTrue(r.exists(key))

            # Clear cache
            r.delete(key)

        for it in self.tags:
            self.assertFalse(r.exists(Tag.redis_posts_key(it)))

        # Heat up cache
        post_ids = [it.pk for it in self.posts]
        post_ids = reversed(post_ids)
        for tag in self.tags:
            tag_posts = Tag.get_posts(tag, 0, 5)

            # Check cache values
            for it1, it2 in zip(tag_posts, post_ids):
                self.assertEqual(it1, it2)

            # Check cache keys
            key = Tag.redis_posts_key(tag)
            self.assertTrue(r.exists(key))


class TestPostCounterInTagModel(BaseTestCase):
    def setUp(self):
        super().setUp()

        self.tags = []
        count = 5
        for i in range(1, count):
            self.tags.append('tag{}'.format(i))
            text = ', '.join(['#{}'.format(it) for it in self.tags])
            Post.objects.create(user=self.user, text=text)

    def test_posts_count(self):
        """Should check count of posts in tag"""
        tags_db = Tag.objects.all()
        for tag in tags_db:
            should_be = Post.objects.filter(tags=tag).count()
            self.assertEqual(tag.posts_count(), should_be)
            self.assertEqual(tag.total_posts, should_be)

        posts = Post.objects.filter(tags__title__in=['tag4', 'tag3'])
        for it in posts:
            it.delete()

        tags_db = Tag.objects.all()
        for tag in tags_db:
            should_be = Post.objects.filter(tags=tag).count()
            self.assertEqual(tag.posts_count(), should_be)
            self.assertEqual(tag.total_posts, should_be)

        self.clear_cache()
        for tag in tags_db:
            should_be = Post.objects.filter(tags=tag).count()
            self.assertEqual(tag.posts_count(), should_be)
            self.assertEqual(tag.total_posts, should_be)

        # class TagPinnedSearch(BaseTestCase):
        #
        #     tag_count = 10
        #
        #     def setUp(self):
        #         super().setUp()
        #
        #         tags = [Tag(title='tag{}'.format(it)) for it in range(TagPinnedSearch.tag_count)]
        #         Tag.objects.bulk_create(tags)
        #
        #     def test_pin_tag(self):
        #         index = TagPinnedSearch.tag_count // 2
        #         title = 'tag{}'.format(index)
        #         url = reverse_lazy('tag-detail', kwargs={'pk': title})
        #         url += 'pin/'
        #
        #         response = self.put_json(url, {})
        #
        #         self.assertEqual(response.status_code, status.HTTP_200_OK)
        #
        #         self.user.refresh_from_db()
        #
        #         self.assertEqual(self.user.pinned_tags.count(), 1)
        #         self.assertTrue(self.user.pinned_tags.filter(title=title))
        #
        #     def test_unpin_tag(self):
        #         tag = Tag.objects.get(title='tag5')
        #
        #         self.user.pinned_tags.add(tag)
        #
        #         url = reverse_lazy('tag-detail', kwargs={'pk': tag.title})
        #         url += 'unpin/'
        #
        #         response = self.put_json(url, {})
        #         self.user.refresh_from_db()
        #
        #         self.assertEqual(response.status_code, status.HTTP_200_OK)
        #         self.assertEqual(self.user.pinned_tags.count(), 0)
        #
        #     def test_pinned_tag_list(self):
        #         limit = 5
        #         tags = Tag.objects.all()[:limit]
        #
        #         for it in tags:
        #             self.user.pinned_tags.add(it)
        #
        #         url = reverse_lazy('tag-list')
        #         url += 'pinned/'
        #
        #         response = self.client.get(url)
        #
        #         self.assertEqual(response.status_code, status.HTTP_200_OK)
        #
        #         self.assertEqual(len(response.data['results']), limit)
        #
        #         tags = {it.title for it in tags}
        #         titles = {it['title'] for it in response.data['results']}
        #
        #         self.assertEqual(tags, titles)