#!/usr/bin/env python
import os
import sys

import dotenv
"""
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
if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'steemengine.settings')
    # Deal with the issue of conflicting dotenv packages by trying both methods...
    try:
        dotenv.load_dotenv()
    except AttributeError:
        dotenv.read_dotenv()
    
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)
