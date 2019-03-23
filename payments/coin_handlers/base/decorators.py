import functools
import logging
from time import sleep

DEF_RETRY_MSG = "Exception while running '%s', will retry %d more times."
DEF_FAIL_MSG = "Giving up after attempting to retry function '%s' %d times."

log = logging.getLogger(__name__)


def retry_on_err(max_retries: int = 3, delay: int = 3, retry_msg: str = DEF_RETRY_MSG, fail_msg: str = DEF_FAIL_MSG):
    """
    Decorates a function or class method, wraps the function/method with a try/catch block, and will automatically
    re-run the function with the same arguments up to `max_retries` time after any exception is raised, with a
    `delay` second delay between re-tries.

    If it still throws an exception after `tries` retries, it will log the exception details with `fail_msg`,
    and then re-raise it.

    :param delay:      Amount of time in seconds to sleep before re-trying the wrapped function
    :param max_retries:      Maximum total retry attempts before giving up
    :param retry_msg:  Override the log message used for retry attempts. First message param %s is func name,
                           second message param %d is retry attempts remaining
    :param fail_msg:   Override the log message used after all retry attempts are exhausted.
                       First message param %s is func name, and second param %d is amount of times retried.
    """

    def _decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            retries = 0
            if 'retry_attempts' in kwargs:
                retries = int(kwargs['retry_attempts'])
                del kwargs['retry_attempts']

            try:
                return f(*args, **kwargs)
            except Exception as e:
                if retries < max_retries:
                    log.exception(retry_msg, f.__name__, max_retries - retries)
                    sleep(delay)
                    kwargs['retry_attempts'] = retries + 1
                    return wrapper(*args, **kwargs)
                log.exception(fail_msg, f.__name__, max_retries)
                raise e
        return wrapper
    return _decorator

#
# class ClassProperty(property):
#     """
#     Taken from https://stackoverflow.com/a/7864317/2648583
#
#     Allows for static class property functions
#
#     Usage:
#
#     >>> @ClassProperty
#     >>>
#
#     """
#     def __get__(self, cls, owner):
#         return classmethod(self.fget).__get__(None, owner)()
