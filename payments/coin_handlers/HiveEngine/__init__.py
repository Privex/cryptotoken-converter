"""
**HiveEngine Coin Handler**

This python module is a **Coin Handler** for Privex's CryptoToken Converter, designed to handle all required
functionality for both receiving and sending tokens on the **HiveEngine** network.

It will automatically handle any :class:`payments.models.Coin` which has it's type set to ``hiveengine``

**Global Settings**

The following global settings are used by this handler (set within :mod:`steemengine.settings.custom`). All of the below settings
can be specified with the same key inside of your ``.env`` file to override the defaults.

    =========================  ==================================================================================
    Setting                    Description
    =========================  ==================================================================================
    ``SENG_RPC_NODE``           The hostname for the contract API server, e.g. ``api.steem-engine.com``
    ``SENG_RPC_URL``            The URL for the contract API e.g. ``/rpc/contracts``
    ``SENG_HISTORY_NODE``       The hostname for the history API server, e.g. ``api.steem-engine.com``
    ``SENG_HISTORY_URL``        The URL for the history API e.g. ``accounts/history``
    ``SENG_NETWORK_ACCOUNT``    The "network account" for HiveEngine, e.g. ``ssc-mainnet1``
    =========================  ==================================================================================

**Coin object settings**:

    You can set the following JSON keys inside of a :class:`.Coin`'s "settings_json" field if you want to use
    an alternative HiveEngine RPC node, or history node just for that coin.

    =================  ==================================================================================================
    Coin Key           Description
    =================  ==================================================================================================
    rpc_node           The hostname for the contract API server, e.g. ``api.steem-engine.com``
    rpc_url            The URL for the contract API e.g. ``/rpc/contracts``
    history_node       The hostname for the history API server, e.g. ``api.steem-engine.com``
    history_url        The URL for the history API e.g. ``accounts/history``
    network_account    The "network account" for HiveEngine, e.g. ``ssc-mainnet1``
    =================  ==================================================================================================

    For example, placing the following JSON inside of ``settings_json`` for a certain coin, would result in the contract API
    ``https://api.hive-engine.com/contracts`` and history API ``https://accounts.hive-engine.com/accountHistory`` being used only
    for this particular coin, while coins without any ``settings_json`` overrides would continue using the global ``SENG_RPC_NODE`` etc.

    .. code-block:: json

        {
            "rpc_node": "api.hive-engine.com",
            "rpc_url": "/contracts",
            "history_node": "accounts.hive-engine.com",
            "history_url": "accountHistory"
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
import logging
from payments.coin_handlers.HiveEngine.HiveEngineLoader import HiveEngineLoader
from payments.coin_handlers.HiveEngine.HiveEngineManager import HiveEngineManager
from django.conf import settings

from payments.models import Coin

log = logging.getLogger(__name__)

loaded = False


def reload():
    """
    Reload's the ``provides`` property for the loader and manager from the DB.

    By default, since new tokens are constantly being created for HiveEngine, our classes can provide for any
    :class:`models.Coin` by scanning for coins with the type ``steemengine``. This saves us from hard coding
    specific coin symbols.
    """
    # Set loaded to True, so we aren't constantly reloading the ``provides``, only when we need to.
    global loaded
    loaded = True
    
    log.debug('Checking if hiveengine is in COIN_TYPES')
    if 'hiveengine' not in dict(settings.COIN_TYPES):
        log.debug('steemengine not in COIN_TYPES, adding it.')
        settings.COIN_TYPES += (('hiveengine', 'HiveEngine Token',),)
    
    # Grab a simple list of coin symbols with the type 'bitcoind' to populate the provides lists.
    provides = Coin.objects.filter(enabled=True, coin_type='hiveengine').values_list('symbol', flat=True)
    HiveEngineLoader.provides = provides
    HiveEngineManager.provides = provides


# Only run the initialisation code once.
# After the first run, reload() will be called only when there's a change by the coin handler system
if not loaded:
    reload()

exports = {
    "loader":  HiveEngineLoader,
    "manager": HiveEngineManager
}
