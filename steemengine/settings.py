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

if STEEM_RPC_NODES is not None:
    STEEM_RPC_NODES = STEEM_RPC_NODES.split(',')

steem_ins = Steem(node=STEEM_RPC_NODES)
steem_ins.set_password_storage('environment')
set_shared_steem_instance(steem_ins)

# This is used for the dropdown "Coin Type" selection in the Django admin panel.
# Coin handlers may add to this list.
COIN_TYPES = (
    ('crypto', 'Generic Cryptocurrency',),
    ('token', 'Generic Token'),
)

COIND_RPC = {}

EX_FEE = Decimal(env('EX_FEE', '0'))

# Load coin handlers from this absolute module path
COIN_HANDLERS_BASE = 'payments.coin_handlers'
# The env variable 'COIN_HANDLERS' is a comma separated list of module names to load
COIN_HANDLERS = env('COIN_HANDLERS', 'SteemEngine,Bitcoin').split(',')

REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': ('django_filters.rest_framework.DjangoFilterBackend',)
}

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True if env('DEBUG', False) in [True, 'true', 'True', 'TRUE', 1] else False

# Specify allowed hosts in .env comma separated, e.g. ALLOWED_HOSTS=example.org,127.0.0.1,example.com
ALLOWED_HOSTS = []

_allowed_hosts = env('ALLOWED_HOSTS', None)

if _allowed_hosts is None or DEBUG:
    ALLOWED_HOSTS += ['127.0.0.1']
if _allowed_hosts is not None:
    ALLOWED_HOSTS += _allowed_hosts.split(',')

# Valid environment log levels (from least to most severe) are:
# DEBUG, INFO, WARNING, ERROR, FATAL, CRITICAL
CONSOLE_LOG_LEVEL = env('LOG_LEVEL', None)
CONSOLE_LOG_LEVEL = logging.getLevelName(str(CONSOLE_LOG_LEVEL).upper()) if CONSOLE_LOG_LEVEL is not None else None

if CONSOLE_LOG_LEVEL is None:
    CONSOLE_LOG_LEVEL = logging.DEBUG if DEBUG else logging.INFO

LOG_FORMATTER = logging.Formatter('[%(asctime)s]: %(name)-55s -> %(funcName)-20s : %(levelname)-8s:: %(message)s')
LOGGER_NAME = 'steemengine'
_lh = LogHelper(LOGGER_NAME, formatter=LOG_FORMATTER, handler_level=logging.DEBUG)

# Log to console with CONSOLE_LOG_LEVEL

_lh.add_console_handler(level=CONSOLE_LOG_LEVEL)

# Output logs >=info / >=warning to respective files with automatic daily log rotation (up to 14 days of logs)
log_folder = os.path.join(BASE_DIR, 'logs')
_dbg_log = os.path.join(log_folder, 'debug.log')
_err_log = os.path.join(log_folder, 'error.log')

_lh.add_timed_file_handler(_dbg_log, when='D', interval=1, backups=14, level=logging.INFO)
_lh.add_timed_file_handler(_err_log, when='D', interval=1, backups=14, level=logging.WARNING)

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
        'DIRS': [],
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




