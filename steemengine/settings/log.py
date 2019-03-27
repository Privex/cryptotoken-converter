"""
Logging configuration for CryptoToken Converter.

Valid environment log levels (from least to most severe) are::

    DEBUG, INFO, WARNING
    ERROR, FATAL, CRITICAL


User customisable environment variables are:

- ``CONSOLE_LOG_LEVEL`` - Messages equal to and above this level will be logged to the console (i.e. the output of
  manage.py commands such as runserver or load_txs) **Default:** INFO in production, DEBUG when DEBUG setting is true

- ``DBGFILE_LEVEL`` - Messages equal to and above this level will be logged to the ``debug.log`` files.
  **Default:** INFO in production, DEBUG when DEBUG setting is true.

- ``ERRFILE_LEVEL`` - Same as DBGFILE_LEVEL but for ``error.log`` - Default: WARNING

- ``LOGGER_NAMES`` - A comma separated list of logger instance names to apply the default logging settings onto.
  **Default:** ``privex``  (Use same logging for Privex's python packages)

- ``BASE_LOGGER_NAME`` - The logger instance name to use for the main logger. If this is not specified, or is blank,
  then the logging API "RootLogger" will be used, which may automatically configure logging for various packages.

- ``BASE_LOG_FOLDER`` - A relative path from the root of the project (folder with manage.py) to the folder where
  log files should be stored. **Default:** ``logs``

- ``BASE_WEB_LOGS`` - Relative path from BASE_LOG_FOLDER where logs from the web app should be stored.
  **Default:** web

- ``BASE_CRON_LOGS`` - Relative path from BASE_LOG_FOLDER where logs from scheduled commands (load_txs etc.) should be
  stored. **Default:** crons


"""
from steemengine.helpers import empty
from steemengine.settings.core import env, BASE_DIR, DEBUG
from privex.loghelper import LogHelper
import logging
import os

##
# To use privex-loghelper in modules, import it like so:
#   >>> from django.conf import settings
#   >>> import logging
#   >>> log = logging.getLogger(settings.LOGGER_NAME)
#   >>> log.error('Something went wrong...')
#
# If your python file uses __name__ for the logger, simply add it's containing module, or full module path
# to LOGGER_NAMES, e.g. payments or payments.coin_handlers.Bitcoin
###

# Valid environment log levels (from least to most severe) are: DEBUG, INFO, WARNING, ERROR, FATAL, CRITICAL
# Log messages to the console which are above this level.
CONSOLE_LOG_LEVEL = env('CONSOLE_LOG_LEVEL', 'DEBUG') if DEBUG else env('LOG_LEVEL', 'INFO')
CONSOLE_LOG_LEVEL = logging.getLevelName(CONSOLE_LOG_LEVEL.upper())

# This default LOG_FORMATTER results in messages that look like this:
#
#   [2019-03-26 20:21:01,798]: payments.management.commands.convert_coins -> handle : INFO :: Coin converter
#    and deposit validator started
#
LOG_FORMATTER = logging.Formatter('[%(asctime)s]: %(name)-55s -> %(funcName)-20s : %(levelname)-8s:: %(message)s')

# Log messages equal/above the specified level to debug.log (default: DEBUG if debug enabled, otherwise INFO)
DBGFILE_LEVEL = env('DBGFILE_LEVEL', 'DEBUG') if DEBUG else env('LOG_LEVEL', 'INFO')
DBGFILE_LEVEL = logging.getLevelName(DBGFILE_LEVEL.upper())
# Log messages equal/above the specified level to error.log (default: WARNING)
ERRFILE_LEVEL = logging.getLevelName(env('ERRFILE_LEVEL', 'WARNING').upper())

# Use the same logging configuration for all privex modules
LOGGER_NAMES = env('LOGGER_NAMES', 'privex').split(',')
# If you don't want to apply the logger settings to the root logger, you should set BASE_LOGGER_NAME in your env file
# to something else, such as 'converter', or 'payments'.
# NOTE: if you set the base logger name, you should make sure you include both 'payments' and 'steemengine' in your
# LOGGER_NAMES or they will not be logged.
BASE_LOGGER = env('BASE_LOGGER_NAME', None)

# Output logs to respective files with automatic daily log rotation (up to 14 days of logs)
BASE_LOG_FOLDER = os.path.join(BASE_DIR, env('LOG_FOLDER', 'logs'))
# To make it easier to identify whether a log entry came from the web application, or from a cron (e.g. load_txs)
# we log to the sub-folder ``BASE_WEB_LOGS`` by default, and management commands such as load_txs will
# re-configure the logs to go to ``BASE_CRON_LOGS``
BASE_WEB_LOGS = os.path.join(BASE_LOG_FOLDER, env('BASE_WEB_LOGS', 'web'))
BASE_CRON_LOGS = os.path.join(BASE_LOG_FOLDER, env('BASE_CRON_LOGS', 'crons'))


def config_logger(*logger_names, log_dir=BASE_LOG_FOLDER):
    """
    Used to allow isolated parts of this project to easily change the log output folder, e.g. allow Django
    management commands to change the logs folder to ``crons/``

    Currently only used by :class:`payments.management.CronLoggerMixin`

    Usage:

    >>> config_logger('someapp', 'otherlogger', 'mylogger', log_dir='/full/path/to/log/folder')

    :param str logger_names: List of logger names to replace logging config for (see LOGGER_NAMES)
    :param str log_dir:      Fully qualified path. Set each logger's timed_file log directory to this
    :return: :class:`logging.Logger` instance of BASE_LOGGER
    """
    _lh = LogHelper(BASE_LOGGER, formatter=LOG_FORMATTER, handler_level=logging.DEBUG)
    _lh.log.handlers.clear()  # Force reset the handlers on the base logger to avoid double/triple logging.
    _lh.add_console_handler(level=CONSOLE_LOG_LEVEL)  # Log to console with CONSOLE_LOG_LEVEL

    _dbg_log = os.path.join(log_dir, 'debug.log')
    _err_log = os.path.join(log_dir, 'error.log')

    _lh.add_timed_file_handler(_dbg_log, when='D', interval=1, backups=14, level=DBGFILE_LEVEL)
    _lh.add_timed_file_handler(_err_log, when='D', interval=1, backups=14, level=ERRFILE_LEVEL)

    l = _lh.get_logger()

    # Use the same logging configuration for all privex modules
    _lh.copy_logger(*logger_names)

    return l


LOGGER_IS_SETUP = False

if not LOGGER_IS_SETUP:
    log = config_logger(*LOGGER_NAMES, log_dir=BASE_WEB_LOGS)
    LOGGER_IS_SETUP = True
else:
    log = logging.getLogger(BASE_LOGGER)
