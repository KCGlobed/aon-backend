import os
import environ
from datetime import timedelta
from pathlib import Path
env = environ.Env()
environ.Env.read_env()
from google.oauth2 import service_account
import json


ENV = os.getenv('DJANGO_ENV', 'dev')
BASE_DIR = Path(__file__).resolve().parent.parent

if ENV == 'prod':
    environ.Env.read_env(os.path.join(BASE_DIR, '.env.prod'))
else:
    environ.Env.read_env(os.path.join(BASE_DIR, '.env.dev'))

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool('DEBUG', default=True)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1', "aon-devapi.kcglobed.com"])

CSRF_TRUSTED_ORIGINS = ["https://aon-devapi.kcglobed.com"]

ADMIN_URL = "https://aon-devapi.kcglobed.com"

ADMIN_BASE_URL = "https://aon-devapi.kcglobed.com"
# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'drf_standardized_errors',
    'corsheaders',
    'rest_framework_simplejwt.token_blacklist',
    'rolepermissions',
    "users",
    "configuration",
    "content",
    "assessment",
    "session",
    "candidate"
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'aon_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'aon_backend.wsgi.application'

# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env("DB_NAME"),
        'USER': env("DB_USER"),
        'PASSWORD': env("DB_PASSWORD"),
        'HOST': env("DB_HOST"),
        'PORT': env("DB_PORT"),
        "CONN_MAX_AGE": 600,  
    }
}


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
       'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PAGINATION_CLASS': 'aon_backend.pagination.CustomPageNumberPagination',
    "EXCEPTION_HANDLER": "drf_standardized_errors.handler.exception_handler",
    'PAGE_SIZE': 20,
}

DRF_STANDARDIZED_ERRORS = {
    "EXCEPTION_FORMATTER_CLASS": "aon_backend.exception_formatter.CustomExceptionFormatter",
}


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

# Everything the API reads and writes is in India time. Timestamps are still stored in UTC because
# USE_TZ is on; this is what they are converted to on the way in and out.
TIME_ZONE = 'Asia/Kolkata'

USE_I18N = True

USE_TZ = True

ROLEPERMISSIONS_MODULE = 'aon_backend.roles'


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

creds_raw = env("GOOGLE_CREDENTIALS_JSON")

if creds_raw:
    creds_dict = json.loads(creds_raw)
    GS_CREDENTIALS = service_account.Credentials.from_service_account_info(creds_dict)
else:
    GS_CREDENTIALS = None


STORAGES = {
    "default": {
        "BACKEND": 'aon_backend.gcloud.Media',
    },
    "staticfiles": {
        "BACKEND": 'aon_backend.gcloud.Static',
    },
}

GS_PROJECT_ID=env("GS_PROJECT_ID")
GS_BUCKET_NAME = env("GS_BUCKET_NAME")
GS_BUCKET_NAME_2 = env("GS_BUCKET_NAME_2")
GS_STATIC_BUCKET_NAME = env("GS_STATIC_BUCKET_NAME")
GS_FILE_OVERWRITE = False
MEDIA_ROOT = "media/"
STATIC_ROOT = "static/"
STATIC_URL = 'https://storage.googleapis.com/{}/static/'.format(GS_STATIC_BUCKET_NAME)
MEDIA_URL = 'https://storage.googleapis.com/{}/media/'.format(GS_BUCKET_NAME)
SECURE_MEDIA_URL = 'https://storage.googleapis.com/{}/media/'.format(GS_BUCKET_NAME_2)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'users.User'

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=2),

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',
    'JTI_CLAIM': 'jti',
}


# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
        "OPTIONS": {
            "HOST": env("EMAIL_HOST"),
            "PORT": 465,
            "HOST_USER": env("EMAIL_HOST_USER"),
            "HOST_PASSWORD": env("EMAIL_HOST_PASSWORD"),
            "USE_SSL": True,
        }
    },
}

# Session invite mails are handed to a background thread so the API returns without waiting on the
# mail server. Set this to False to have them go out inline, which is what a management command or
# a test wants when it needs the outcome in hand. Anything left Pending or Failed - a thread does
# not outlive a restart of the process - can be put through again with the resend-session-invite API.
SEND_SESSION_INVITES_IN_BACKGROUND = env.bool('SEND_SESSION_INVITES_IN_BACKGROUND', default=True)

# How long an SMTP call may block, in seconds. Invites go out on a background thread, so a mail
# server that accepts a connection and then stalls would otherwise hold that thread indefinitely.
EMAIL_SEND_TIMEOUT = env.int('EMAIL_SEND_TIMEOUT', default=30)
