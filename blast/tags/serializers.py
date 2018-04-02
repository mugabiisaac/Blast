from rest_framework import serializers

from tags.models import Tag


class TagPublicSerializer(serializers.ModelSerializer):
    total_posts = serializers.ReadOnlyField(source='posts_count')

    class Meta:
        model = Tag
        fields = ('title', 'total_posts',)