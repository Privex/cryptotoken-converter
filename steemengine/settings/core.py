"""
This file contains the core settings of the application. Settings specified within this file are used directly by
the Django framework, or a third-party extension / application for Django.

**User specifiable environment variables:**

**Basic Config**

- ``DEBUG`` - If set to true, enable debugging features, such as **extremely verbose error pages** and automatic
  code reloading on edit. **DO NOT RUN WITH DEBUG IN PRODUCTION, IT IS NOT SAFE.**

  **Default:** ``False``

- ``SECRET_KEY`` - **MANDATORY** - A long random string used to encrypt user sessions, among other security features.

- ``CORS_ORIGIN_ALLOW_ALL`` - If True, allow all cross-origin requests (disable whitelist). **Default:** ``True``

- ``CORS_ORIGIN_WHITELIST`` - Comma separated list of domains and subdomains to allow CORS for. Adding a domain
  does not automatically include it's subdomains. All subdomains must be added manually. **Default:** Blank

- ``ALLOWED_HOSTS`` - Comma separated list of the domains you intend to run this on. For security
  (e.g. preventing cookie theft), Django requires that you specify each hostname that this application should be
  accessible from.
  **Default:** ``127.0.0.1,localhost`` (these are also auto added if DEBUG is True).

**Database Settings**

- ``DB_BACKEND`` - What type of DB are you using? ``mysql`` or ``postgresql`` **Default:** ``postgresql``
- ``DB_HOST`` - What hostname/ip is the DB on? **Default:** ``localhost``
- ``DB_NAME`` - What is the name of the database to use? **Default:** ``steemengine_pay``
- ``DB_USER`` - What username to connect with? **Default:** ``steemengine``
- ``DB_PASS`` - What password to connect with? **Default:** no password

For more information on this file, see
https://docs.djangoproject.com/en/2.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.1/ref/settings/

Copyright::

    +===================================================+
    |                 © 2019 Privex Inc.                |
    |               https://www.privex.io               |
    +===================================================+
    |                                                   |
    |        CryptoToken Converter                      |
    |                                                   |
    |        Core Developer(s):                         |
    |                                                   |
    |          (+)  Chris (@someguy123) [Privex]        |
    |                                                   |
    +===================================================+

"""

import os
import sys

import dotenv
from getenv import env
from steemengine.helpers import random_str

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

dotenv.read_dotenv(os.path.join(BASE_DIR, '.env'))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY', None)

if SECRET_KEY is None:
    print('Critical ERROR: No SECRET_KEY set in .env! Cannot continue.')
    print('Please generate a secure random string used to encrypt sensitive data such as user sessions')
    print("Place the following line into the file {} - for production we recommend generating it by hand."
          .format(os.path.join(BASE_DIR, '.env')))
    print()
    print('SECRET_KEY={}'.format(random_str(size=64)))
    print()
    sys.exit()


REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': ('django_filters.rest_framework.DjangoFilterBackend',)
}

# Ignore the whitelist and allow CORS from anywhere
CORS_ORIGIN_ALLOW_ALL = env('CORS_ORIGIN_ALLOW_ALL', True) in [True, 'true', 'True', 'TRUE', 1]
# A comma separated list of domains (must include each subdomain) that can send CORS requests
# This is ignored if you don't change CORS_ORIGIN_ALLOW_ALL to False.
CORS_ORIGIN_WHITELIST = env('CORS_ORIGIN_WHITELIST', '').split(',')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG', False) in [True, 'true', 'True', 'TRUE', 1]

# ALLOWED_HOSTS defines a list of hostnames/ips that this app can be accessed from
# In DEBUG, we add localhost/127.0.0.1 by default, as well as when ALLOWED_HOSTS isn't set in .env
# Specify allowed hosts in .env comma separated, e.g. ALLOWED_HOSTS=example.org,127.0.0.1,example.com
_allowed_hosts = env('ALLOWED_HOSTS', None)
ALLOWED_HOSTS = []
ALLOWED_HOSTS += ['127.0.0.1', 'localhost'] if _allowed_hosts is None or DEBUG else ALLOWED_HOSTS
ALLOWED_HOSTS += _allowed_hosts.split(',') if _allowed_hosts is not None else ALLOWED_HOSTS

# Administrator emails to notify of important issues
# Env var `ADMINS` should be formatted name:email,name:email
#
# Example: John Doe:john@example.com,Jane Doe:janed@example.com
# Results in: [('John Doe', 'john@example.com'), ('Jane Doe', 'janed@example.com')]
#
ADMINS = env('ADMINS', '')
ADMINS = [tuple(a.split(':')) for a in ADMINS.split(',')] if ADMINS != '' else []
ADMINS = [(a.strip(), b.strip()) for a, b in ADMINS]

###
# Outgoing Email config, for notifications
###

# Used as a subject prefix for emails sent to admins from the app
EMAIL_SUBJECT_PREFIX = env('EMAIL_SUBJECT_PREFIX', '[ConverterApp] ')

# Emails have no idea what domain they're running on.
SITE_URL = env('SITE_URL', None)

# The email to use by default when sending outgoing emails
SERVER_EMAIL = env('SERVER_EMAIL', 'noreply@example.com')

EMAIL_BACKEND = env('EMAIL_BACKEND', None)
if not EMAIL_BACKEND:
    EMAIL_BACKEND = 'django.core.mail.backends.' + ('console.EmailBackend' if DEBUG else 'smtp.EmailBackend')

# Hostname / IP of SMTP server, must be set in production for outgoing SMTP emails
EMAIL_HOST = env('EMAIL_HOST', None)
if EMAIL_HOST is not None:
    EMAIL_PORT = int(env('EMAIL_PORT', 587))            # Port number to connect to email server
    EMAIL_HOST_USER = env('EMAIL_USER', 'steemengine')  # Username for email server login
    EMAIL_HOST_PASSWORD = env('EMAIL_PASSWORD', '')     # Password for email server login
    # True = Use TLS for SMTP, False = Do not use any encryption
    EMAIL_USE_TLS = env('EMAIL_TLS', True) in [True, 'true', 'True', 'TRUE', 1]
else:
    # If you're using the SMTP backend in production, and you don't have an email server hostname/ip set
    # then we change your email backend to dummy (outgoing emails are simply dropped)
    if EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend':
        EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'django_filters',
    'payments',
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

ROOT_URLCONF = 'steemengine.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': ['payments/templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'steemengine.wsgi.application'


# Database
# https://docs.djangoproject.com/en/2.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.' + env('DB_BACKEND', 'postgresql'),
        'NAME': env('DB_NAME', 'steemengine_pay'),
        'USER': env('DB_USER', 'steemengine'),
        'PASSWORD': env('DB_PASS', ''),
        'HOST': env('DB_HOST', 'localhost'),
    },
}

# By default, caching is done in local memory of the app, which is fine for development, or small scale production.
# In production, you should probably use Memcached or database caching.
# See https://docs.djangoproject.com/en/2.1/topics/cache/
#
# If you want to use Memcached, install memcached + dev headers, and pylibmc (pip3 install pylibmc)
# then set env var CACHE_BACKEND to 'django.core.cache.backends.memcached.PyLibMCCache', and CACHE_LOCATION to
# ``ip:port`` where 'ip' is the IP/hostname of the memcached server, and 'port' is the memcached port.

# If CACHE_LOCATION is specified, we split the CACHE_LOCATION by comma to allow multiple locations
_ch_loc = env('CACHE_LOCATION', None)
CACHE_LOCATION = str(_ch_loc).split(',') if _ch_loc is not None else None

CACHES = {
    'default': {
        'BACKEND': env('CACHE_BACKEND', 'django.core.cache.backends.locmem.LocMemCache'),
        'LOCATION': CACHE_LOCATION,
    }
}

# Password validation
# https://docs.djangoproject.com/en/2.1/ref/settings/#auth-password-validators

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

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'privex': {
            'format': '[%(asctime)s]: %(name)-55s -> %(funcName)-20s : %(levelname)-8s:: %(message)s',
            'style': '%'
        }
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'privex'
        },
        # Include the default Django email handler for errors
        # This is what you'd get without configuring logging at all.
        'mail_admins': {
            'class': 'django.utils.log.AdminEmailHandler',
            'level': 'ERROR',
            # But the emails are plain text by default - HTML is nicer
            'include_html': True,
        },
        'logfile': {
            'class': 'logging.handlers.WatchedFileHandler',
            'filename': os.path.join(BASE_DIR, 'django.log'),
            'formatter': 'privex'
        },
    },
    'loggers': {
        # Again, default Django configuration to email unhandled exceptions
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
        # Might as well log any errors anywhere else in Django
        'django': {
            'handlers': ['logfile'],
            'level': 'ERROR',
            'propagate': False,
        },
    }
}

if DEBUG:
    LOGGING['loggers']['django.request']['handlers'] = ['console', 'logfile']

# Internationalization
# https://docs.djangoproject.com/en/2.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.1/howto/static-files/

STATIC_URL = '/static/'

if DEBUG:
    STATICFILES_DIRS = [
        os.path.join(BASE_DIR, "static"),
    ]
else:
    STATIC_ROOT = os.path.join(BASE_DIR, 'static')




