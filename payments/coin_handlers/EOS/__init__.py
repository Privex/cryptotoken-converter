"""
**EOS Coin Handler**

This python module is a **Coin Handler** for Privex's CryptoToken Converter, designed to handle all required
functionality for both receiving and sending tokens on the **EOS** network.

It will automatically handle any :class:`payments.models.Coin` which has it's type set to ``eos``

To use this handler, you must first create the base coin with symbol ``EOS``:

    Coin Name:  EOS
    Symbol:     EOS
    Our Account: (username of account used for sending/receiving native EOS token)
    Custom JSON: {"contract": "eosio.token"}

To change the RPC node from the admin panel, simply set the host/port/username/password on the EOS Coin:

    # Below are the defaults used if you don't configure the EOS coin:
    Host: eos.greymass.com
    Port: 443
    User: (leave blank)
    Pass: (leave blank)
    Custom JSON: {"ssl": True}

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
from payments.coin_handlers.EOS.EOSLoader import EOSLoader
from payments.coin_handlers.EOS.EOSManager import EOSManager
from django.conf import settings

from payments.models import Coin

log = logging.getLogger(__name__)

loaded = False


def reload():
    """
    Reload's the ``provides`` property for the loader and manager from the DB.

    By default, since new tokens are constantly being created for EOS, our classes can provide for any
    :class:`models.Coin` by scanning for coins with the type ``eos``. This saves us from hard coding
    specific coin symbols.
    """
    # Set loaded to True, so we aren't constantly reloading the ``provides``, only when we need to.
    global loaded
    loaded = True

    log.debug('Checking if eos is in COIN_TYPES')
    if 'eos' not in dict(settings.COIN_TYPES):
        log.debug('eos not in COIN_TYPES, adding it.')
        settings.COIN_TYPES += (('eos', 'EOS Token',),)

    # Grab a simple list of coin symbols with the type 'bitcoind' to populate the provides lists.
    provides = Coin.objects.filter(coin_type='eos').values_list('symbol', flat=True)
    EOSLoader.provides = provides
    EOSManager.provides = provides


# Only run the initialisation code once.
# After the first run, reload() will be called only when there's a change by the coin handler system
if not loaded:
    reload()

exports = {
    "loader": EOSLoader,
    "manager": EOSManager
}
