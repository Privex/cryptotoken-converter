from django.conf import settings
from steemengine.settings import config_logger
import steemengine.settings.log


class CronLoggerMixin:
    """
    A very simple class mixin which uses :py:func:`settings.log.config_logger` to reset all configured loggers
    and make sure they output their logs to the cron logs folder, not the normal web logs.
    """
    def __init__(self, *args, **kwargs):
        """
        A very simple class mixin which uses :py:func:`settings.log.config_logger` to reset all configured loggers
        and make sure they output their logs to the cron logs folder, not the normal web logs.

        Basic usage:

        >>> class MyCron(CronLoggerMixin, SomeOtherClass):
        >>>     def __init__(self):
        >>>         super(MyCron, self).__init__()

        :param args: Not necessary. Simply passed to any parent constructor.
        :param kwargs: Not necessary. Simply passed to any parent constructor.
        """
        # Make sure the default logger doesn't run after we've changed the logger settings.
        steemengine.settings.log.LOGGER_IS_SETUP = True
        # Point all configured loggers to output to the cron folder, ensuring all log output is correctly routed
        config_logger(*settings.LOGGER_NAMES, log_dir=settings.BASE_CRON_LOGS)
        super(CronLoggerMixin, self).__init__(*args, **kwargs)
