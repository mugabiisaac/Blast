# -*- coding: utf-8 -*-
# Generated by Django 1.9.1 on 2017-01-12 16:20
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import posts.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Post',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('media_width', models.FloatField(default=0)),
                ('media_height', models.FloatField(default=0)),
                ('caption_width', models.FloatField(null=True, verbose_name='Caption Width')),
                ('caption_height', models.FloatField(null=True, verbose_name='Caption Height')),
                ('caption_x_pos', models.FloatField(null=True, verbose_name='Caption Center X Position')),
                ('caption_y_pos', models.FloatField(null=True, verbose_name='Caption Center Y Position')),
                ('cap_rotate_ang', models.FloatField(null=True, verbose_name='Caption Rotation Angle')),
                ('lat', models.FloatField(blank=True, null=True, verbose_name='Location Latitude')),
                ('lon', models.FloatField(blank=True, null=True, verbose_name='Location Longitude')),
                ('location_name', models.CharField(max_length=1024, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('expired_at', models.DateTimeField(default=posts.models.get_expiration_date)),
                ('text', models.CharField(blank=True, max_length=1024)),
                ('image', models.ImageField(blank=True, null=True, upload_to=posts.models.post_image_upload_dir)),
                ('video', models.FileField(blank=True, null=True, upload_to=posts.models.post_upload_dir)),
                ('downvoted_count', models.PositiveIntegerField(default=0)),
                ('voted_count', models.PositiveIntegerField(default=0)),
                ('is_marked_for_removal', models.BooleanField(default=False)),
            ],
            options={
                'ordering': ('-created_at',),
            },
            bases=(posts.models.PostAdminFields, posts.models.TextNotificationMixin, models.Model),
        ),
        migrations.CreateModel(
            name='PostComment',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('text', models.CharField(max_length=1024)),
            ],
            bases=(posts.models.TextNotificationMixin, models.Model),
        ),
        migrations.CreateModel(
            name='PostVote',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('is_positive', models.NullBooleanField()),
                ('post', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='posts.Post')),
            ],
        ),
    ]
