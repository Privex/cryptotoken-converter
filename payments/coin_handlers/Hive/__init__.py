"""
**Hive Coin Handler**

This python module is a **Coin Handler** for Privex's CryptoToken Converter, designed to handle all required
functionality for both receiving and sending tokens on the **Hive** network.

It will automatically handle any :class:`payments.models.Coin` which has it's type set to ``hivebase``

**Coin object settings**:

    For each :class:`payments.models.Coin` you intend to use with this handler, you should configure it as such:

    =============   ==================================================================================================
    Coin Key        Description
    =============   ==================================================================================================
    coin_type       This should be set to ``Hive Network (or compatible fork)`` (db value: hivebase)
    our_account     This should be set to the username of the account you want to use for receiving/sending
    setting_json    A JSON string for optional extra config (see below)
    =============   ==================================================================================================

    Extra JSON (Handler Custom) config options:

    - ``rpcs`` - A JSON list<str> of RPC nodes to use, with a full HTTP/HTTPS URL. If this is not specified, Beem
      will automatically try to use the best available RPC node for the Hive network.
    - ``pass_store`` - Generally you do not need to touch this. It controls where Beem will look for the wallet
      password. It defaults to ``environment``

    Example JSON custom config::

        {
            "rpcs": [
                "https://steemd.privex.io",
                "https://api.steemit.com",
                "https://api.steem.house"
            ],
            "pass_store": "environment"
        }



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
from payments.coin_handlers.Hive.HiveLoader import HiveLoader
from payments.coin_handlers.Hive.HiveManager import HiveManager
from django.conf import settings
import logging
from payments.models import Coin

log = logging.getLogger(__name__)

loaded = False


def reload():
    """
    Reload's the ``provides`` property for the loader and manager from the DB.

    By default, since new Hive forks are constantly being created, our classes can provide for any
    :class:`models.Coin` by scanning for coins with the type ``hivebase``. This saves us from hard coding
    specific coin symbols.
    """
    # Set loaded to True, so we aren't constantly reloading the ``provides``, only when we need to.
    global loaded
    loaded = True
    
    log.debug('Checking if hivebase is in COIN_TYPES')
    if 'hivebase' not in dict(settings.COIN_TYPES):
        log.debug('hivebase not in COIN_TYPES, adding it.')
        settings.COIN_TYPES += (('hivebase', 'Hive Network (or compatible fork)',),)
    
    # Grab a simple list of coin symbols with the type 'bitcoind' to populate the provides lists.
    provides = Coin.objects.filter(enabled=True, coin_type='hivebase').values_list('symbol', flat=True)
    HiveLoader.provides = provides
    HiveManager.provides = provides


# Only run the initialisation code once.
# After the first run, reload() will be called only when there's a change by the coin handler system
if not loaded:
    reload()

exports = {
    "loader":  HiveLoader,
    "manager": HiveManager
}
