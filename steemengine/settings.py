"""
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

import logging
import os
import sys
from decimal import Decimal
from importlib import import_module

import dotenv
from beem.steem import Steem
from beem.instance import set_shared_steem_instance
from getenv import env
from privex.loghelper import LogHelper
from steemengine.helpers import random_str

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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

# Supply a list of one or more comma-separated Steem RPC nodes. If not set, will use the default beem nodes.
STEEM_RPC_NODES = env('STEEM_RPC_NODES', None)
STEEM_RPC_NODES = STEEM_RPC_NODES.split(',') if STEEM_RPC_NODES is not None else None
# Set the shared Beem RPC instance to use the specified nodes
steem_ins = Steem(node=STEEM_RPC_NODES)
steem_ins.set_password_storage('environment')    # Get Beem wallet pass from env var ``UNLOCK``
set_shared_steem_instance(steem_ins)

# This is used for the dropdown "Coin Type" selection in the Django admin panel. Coin handlers may add to this list.
COIN_TYPES = (
    ('crypto', 'Generic Cryptocurrency',),
    ('token', 'Generic Token'),
)

COIND_RPC = {}     # Used by coin_handlers.Bitcoin

EX_FEE = Decimal(env('EX_FEE', '0'))           # Conversion fee taken by us, in percentage (i.e. "1" = 1%)

COIN_HANDLERS_BASE = 'payments.coin_handlers'  # Load coin handlers from this absolute module path
COIN_HANDLERS = env('COIN_HANDLERS', 'SteemEngine,Bitcoin').split(',')  # A comma separated list of modules to load

REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': ('django_filters.rest_framework.DjangoFilterBackend',)
}

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG', False) in [True, 'true', 'True', 'TRUE', 1]

# ALLOWED_HOSTS defines a list of hostnames/ips that this app can be accessed from
# In DEBUG, we add localhost/127.0.0.1 by default, as well as when ALLOWED_HOSTS isn't set in .env
# Specify allowed hosts in .env comma separated, e.g. ALLOWED_HOSTS=example.org,127.0.0.1,example.com
_allowed_hosts = env('ALLOWED_HOSTS', None)
ALLOWED_HOSTS = []
ALLOWED_HOSTS += ['127.0.0.1', 'localhost'] if _allowed_hosts is None or DEBUG else ALLOWED_HOSTS
ALLOWED_HOSTS += _allowed_hosts.split(',') if _allowed_hosts is not None else ALLOWED_HOSTS

# Valid environment log levels (from least to most severe) are: DEBUG, INFO, WARNING, ERROR, FATAL, CRITICAL
# Log messages to the console which are above this level.
CONSOLE_LOG_LEVEL = env('CONSOLE_LOG_LEVEL', 'DEBUG') if DEBUG else env('LOG_LEVEL', 'INFO')
CONSOLE_LOG_LEVEL = logging.getLevelName(CONSOLE_LOG_LEVEL.upper())

LOG_FORMATTER = logging.Formatter('[%(asctime)s]: %(name)-55s -> %(funcName)-20s : %(levelname)-8s:: %(message)s')
LOGGER_NAME = 'steemengine'

# Log messages equal/above the specified level to debug.log (default: DEBUG if debug enabled, otherwise INFO)
DBGFILE_LEVEL = env('DBGFILE_LEVEL', 'DEBUG') if DEBUG else env('LOG_LEVEL', 'INFO')
DBGFILE_LEVEL = logging.getLevelName(DBGFILE_LEVEL.upper())
# Log messages equal/above the specified level to error.log (default: WARNING)
ERRFILE_LEVEL = logging.getLevelName(env('ERRFILE_LEVEL', 'WARNING').upper())

_lh = LogHelper(LOGGER_NAME, formatter=LOG_FORMATTER, handler_level=logging.DEBUG)
_lh.add_console_handler(level=CONSOLE_LOG_LEVEL)  # Log to console with CONSOLE_LOG_LEVEL
# Output logs to respective files with automatic daily log rotation (up to 14 days of logs)
log_folder = os.path.join(BASE_DIR, 'logs')
_dbg_log = os.path.join(log_folder, 'debug.log')
_err_log = os.path.join(log_folder, 'error.log')

_lh.add_timed_file_handler(_dbg_log, when='D', interval=1, backups=14, level=DBGFILE_LEVEL)
_lh.add_timed_file_handler(_err_log, when='D', interval=1, backups=14, level=ERRFILE_LEVEL)

# Use the same logging configuration for all privex modules
_lh.copy_logger('privex')

# Use the same logging configuration for the payments app
_lh.copy_logger('payments')

##
# To use privex-loghelper in modules, import it like so:
#   >>> from django.conf import settings
#   >>> import logging
#   >>> log = logging.getLogger(settings.LOGGER_NAME)
#   >>> log.error('Something went wrong...')
###
log = _lh.get_logger()


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'django_filters',
    'payments',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
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




