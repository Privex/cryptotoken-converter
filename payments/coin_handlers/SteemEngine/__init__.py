"""
**SteemEngine Coin Handler**

This python module is a **Coin Handler** for Privex's CryptoToken Converter, designed to handle all required
functionality for both receiving and sending tokens on the **SteemEngine** network.

It will automatically handle any :class:`payments.models.Coin` which has it's type set to ``steemengine``

**Copyright**::

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
from payments.coin_handlers.SteemEngine.SteemEngineLoader import SteemEngineLoader
from payments.coin_handlers.SteemEngine.SteemEngineManager import SteemEngineManager
from django.conf import settings

from payments.models import Coin

log = logging.getLogger(__name__)

loaded = False


def reload():
    """
    Reload's the ``provides`` property for the loader and manager from the DB.

    By default, since new tokens are constantly being created for SteemEngine, our classes can provide for any
    :class:`models.Coin` by scanning for coins with the type ``steemengine``. This saves us from hard coding
    specific coin symbols.
    """
    # Set loaded to True, so we aren't constantly reloading the ``provides``, only when we need to.
    global loaded
    loaded = True

    log.debug('Checking if steemengine is in COIN_TYPES')
    if 'steemengine' not in dict(settings.COIN_TYPES):
        log.debug('steemengine not in COIN_TYPES, adding it.')
        settings.COIN_TYPES += (('steemengine', 'SteemEngine Token',),)

    # Grab a simple list of coin symbols with the type 'bitcoind' to populate the provides lists.
    provides = Coin.objects.filter(coin_type='steemengine').values_list('symbol', flat=True)
    SteemEngineLoader.provides = provides
    SteemEngineManager.provides = provides


# Only run the initialisation code once.
# After the first run, reload() will be called only when there's a change by the coin handler system
if not loaded:
    reload()


exports = {
    "loader": SteemEngineLoader,
    "manager": SteemEngineManager
}
