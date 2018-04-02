from blast.settings import *

DEBUG = False

ALLOWED_HOSTS = ['*']

SINCH = {
    'APP_KEY': '155edefb-991d-4e14-864e-4e9451a21bd6',
    'APP_SECRET': '2JS8PKvSyk2AgNf+3DIvZQ==',
}

CELERYBEAT_SCHEDULE = {
    'clear-expired-posts': {
        'task': 'posts.tasks.clear_expired_posts',
        'schedule': timedelta(seconds=60*5),
    },
    'send-notifications': {
        'task': 'posts.tasks.send_expire_notifications',
        'schedule': timedelta(seconds=30)
    }
}

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'blast',
        'USER': 'blastadmin',
        'PASSWORD': '123456',
        'HOST': 'localhost',
        'PORT': '5432',
        'ATOMIC_REQUESTS': True
    }
}
