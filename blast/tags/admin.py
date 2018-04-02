from django.contrib import admin

from tags.models import Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('title', 'total_posts', 'posts_count')
    readonly_fields = ('title', 'total_posts', 'posts_count')
    search_fields = ('title',)