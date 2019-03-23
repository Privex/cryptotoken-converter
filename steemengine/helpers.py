"""
Various helper functions for use in CryptoToken Converter.

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
import random
import string

# characters that shouldn't be mistaken
SAFE_CHARS = 'abcdefhkmnprstwxyz2345679ACDEFGHJKLMNPRSTWXYZ'


def random_str(size=50, chars=SAFE_CHARS):
    return ''.join(random.SystemRandom().choice(chars) for _ in range(size))


def empty(v, zero=False, itr=False):
    """
    Quickly check if a variable is empty or not. By default only '' and None are checked, use `itr` and `zero` to
    test for empty iterable's and zeroed variables.

    Returns True if a variable is None or '', returns False if variable passes the tests

    :param v:    The variable to check if it's empty
    :param zero: if zero=True, then return True if the variable is 0
    :param itr:  if itr=True, then return True if the variable is ``[]``, ``{}``, or is an iterable and has 0 length
    :return bool is_blank: True if a variable is blank (``None``, ``''``, ``0``, ``[]`` etc.)
    :return bool is_blank: False if a variable has content (or couldn't be checked properly)
    """

    _check = [None, '']
    if zero: _check.append(0)
    if v in _check: return True
    if itr:
        if v == [] or v == {}: return True
        if hasattr(v, '__len__') and len(v) == 0: return True

    return False

