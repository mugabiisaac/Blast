import logging
import re
import redis

from django.db import models

# Create your models here.
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from core.decorators import save_to_zset


logger = logging.Logger(__name__)
r = redis.StrictRedis(host='localhost', port=6379, db=0)


class Tag(models.Model):
    """
    Hast tag for Post model
    """
    title = models.CharField(max_length=30, unique=True, primary_key=True)

    # Total count of posts for current tag.
    total_posts = models.PositiveIntegerField(default=0)

    def posts_count(self):
        from posts.models import Post
        return Post.objects.filter(tags__title=self.title).count()
        # key = r.zcard(Tag.redis_posts_key(self.pk))
        # if not r.exists(key):
        #     posts = Post.objects.filter(tags__title=self.title).values_list('id', flat=True)
        #     result = []
        #     for it in posts:
        #         result.append(1)
        #         result.append(it)
        #     if result:
        #         r.zadd(key, *result)
        #
        # return r.zcard(key)

    @staticmethod
    def redis_posts_key(pk):
        return u'tag:{}:posts'.format(pk)

    @staticmethod
    @save_to_zset(u'tag:{}:posts')
    def get_posts(tag_pk, start, end):
        from posts.models import Post
        result = []
        posts = list(Post.objects.actual().filter(tags=tag_pk))
        for it in posts:
            result.append(it.popularity)
            result.append(it.pk)

        return result

    def save(self, **kwargs):
        self.title = self.title.lower()
        return super().save(**kwargs)

    def __str__(self):
        return u'{} - {}'.format(self.title, self.total_posts)


@receiver(pre_delete, sender=Tag, dispatch_uid='pre_deleted_tag')
def pre_delete_tag(sender, instance: Tag, **kwargs):
    r.delete(Tag.redis_posts_key(pk=instance.title))
