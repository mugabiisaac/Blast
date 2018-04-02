# -*- coding: utf-8 -*-

from django.dispatch import Signal

user_registered = Signal()

start_following = Signal(providing_args=['follower', 'followee'])
