# -*- coding: utf-8 -*-
# Generated by Django 1.9.1 on 2018-03-24 12:50
from __future__ import unicode_literals

from django.db import migrations, models
import smsconfirmation.models


class Migration(migrations.Migration):

    dependencies = [
        ('smsconfirmation', '0004_auto_20180320_1135'),
    ]

    operations = [
        migrations.AlterField(
            model_name='phoneconfirmation',
            name='code',
            field=models.CharField(default=smsconfirmation.models.get_phone_confirmation_code, max_length=6),
        ),
        migrations.AlterField(
            model_name='verifycreate',
            name='code',
            field=models.CharField(default=smsconfirmation.models.get_phone_confirmation_code, max_length=6),
        ),
    ]
