# -*- coding: utf-8 -*-
# Generated by Django 1.9.1 on 2017-01-12 16:54
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('posts', '0003_post_post_type'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='post',
            name='cap_rotate_ang',
        ),
        migrations.RemoveField(
            model_name='post',
            name='caption_height',
        ),
        migrations.RemoveField(
            model_name='post',
            name='caption_width',
        ),
        migrations.RemoveField(
            model_name='post',
            name='caption_x_pos',
        ),
        migrations.RemoveField(
            model_name='post',
            name='caption_y_pos',
        ),
        migrations.RemoveField(
            model_name='post',
            name='lat',
        ),
        migrations.RemoveField(
            model_name='post',
            name='location_name',
        ),
        migrations.RemoveField(
            model_name='post',
            name='lon',
        ),
        migrations.RemoveField(
            model_name='post',
            name='media_height',
        ),
        migrations.RemoveField(
            model_name='post',
            name='media_width',
        ),
        migrations.RemoveField(
            model_name='post',
            name='post_type',
        ),
    ]
