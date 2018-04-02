from django.contrib import admin

from posts.models import Post, PostComment, PostVote
from users.models import PinnedPosts
from django.db import models
from django import forms


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('pk', 'user', 'text', 'image', 'video', 'time_remains', 'created_at', 'is_marked_for_removal', 'post_type',
                    'media_width', 'media_height', 'caption_width', 'caption_height', 'caption_x_pos', 'caption_y_pos', 'cap_rotate_ang',
                    'lat', 'lon', 'location_name')
    readonly_fields = ('is_marked_for_removal', 'image_tag', 'video_tag')

    formfield_overrides = {
        models.DateTimeField: {'widget': forms.DateTimeInput(format='%Y-%m-%d %H:%M:%S.%f')},
    }
    search_fields = ('location_name', 'lat', 'lon')

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super(PostAdmin, self).get_search_results(request, queryset, search_term)
        
        # posts = request.user.pinned.filter().values('post_id')
        queryset = queryset.order_by('-created_at')
        if search_term in [None, '']:
            pass
        else:
            queryset = queryset[:3]

        
        return queryset, use_distinct

@admin.register(PostComment)
class PostCommentAdmin(admin.ModelAdmin):
    list_display = ('pk', 'user', 'post', 'text', 'created_at')


@admin.register(PostVote)
class PostVoteAdmin(admin.ModelAdmin):
    list_display = ('pk', 'post', 'user', 'is_positive', 'created_at')


@admin.register(PinnedPosts)
class PinnedPostsAdmin(admin.ModelAdmin):
    list_display = ('pk', 'post_id', 'user_id',)
