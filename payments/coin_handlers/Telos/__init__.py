"""
**Telos Coin Handler**

This python module is a **Coin Handler** for Privex's CryptoToken Converter, designed to handle all required
functionality for both receiving and sending tokens on the **Telos** network.

It will automatically handle any :class:`payments.models.Coin` which has it's type set to ``telos``

To use this handler, you must first create the base coin with symbol ``Telos``::

    Coin Name:  TLOS
    Symbol:     TLOS
    Our Account: (username of account used for sending/receiving native Telos token)
    Custom JSON: {"contract": "eosio.token"}

To change the RPC node from the admin panel, simply set the host/port/username/password on the Telos Coin::

    # Below are the defaults used if you don't configure the Telos coin::
    Host: telos.caleos.io
    Port: 443
    User: (leave blank)
    Pass: (leave blank)
    Custom JSON: {"ssl": True}



**Coin Settings (Custom JSON settings)**
    
    .. Tip::  You can override the defaults for all Telos coins by setting the ``settings_json`` for a coin with the symbol ``TLOS``.
              
              All :class:`.Coin`'s handled by the Telos handler will inherit the ``TLOS`` coin's custom JSON settings, which can be
              overrided via the individual coin's ``settings_json``.
    
    You can set the following JSON keys inside of a :class:`.Coin`'s "settings_json" field to adjust settings such as the
    "contract account" for the token, whether or not to use SSL with the RPC node, as well as the precision (DP) of the coin, if
    it's different from the default of ``4`` decimal places.

    =================  ==================================================================================================
    Coin Key           Description
    =================  ==================================================================================================
    endpoint           (str) The base URI to query against, e.g. ``/telos_rpc/``
    ssl                (bool) Whether or not to use SSL (https). Boolean ``true`` or ``false``
    contract           (str) The contract account for this token, e.g. ``eosio.token`` or ``steemenginex``
    precision          (int) The precision (decimal places) of this coin (defaults to ``4``)
    
    load_method        (str) Either ``actions`` to use v1/history, or ``pvx`` to use Privex EOS History
    history_url        (str) (if load_method is pvx) Privex history URL, e.g. ``https://eos-history.privex.io``
    =================  ==================================================================================================


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
from payments.coin_handlers.Telos.TelosLoader import TelosLoader
from payments.coin_handlers.Telos.TelosManager import TelosManager
from django.conf import settings

from payments.coin_handlers.Telos.TelosMixin import TelosMixin
from payments.models import Coin

log = logging.getLogger(__name__)

loaded = False


def reload():
    """
    Reload's the ``provides`` property for the loader and manager from the DB.

    By default, since new tokens are constantly being created for Telos, our classes can provide for any
    :class:`models.Coin` by scanning for coins with the type ``telos``. This saves us from hard coding
    specific coin symbols.
    """
    # Set loaded to True, so we aren't constantly reloading the ``provides``, only when we need to.
    global loaded
    loaded = True
    
    log.debug(f'Checking if {TelosMixin.chain_type} is in COIN_TYPES')
    if TelosMixin.chain_type not in dict(settings.COIN_TYPES):
        log.debug(f'{TelosMixin.chain_type} not in COIN_TYPES, adding it.')
        settings.COIN_TYPES += ((TelosMixin.chain_type, 'Telos Token',),)
    
    # Grab a simple list of coin symbols with the type 'bitcoind' to populate the provides lists.
    provides = Coin.objects.filter(enabled=True, coin_type=TelosMixin.chain_type).values_list('symbol', flat=True)
    TelosLoader.provides = provides
    TelosManager.provides = provides


# Only run the initialisation code once.
# After the first run, reload() will be called only when there's a change by the coin handler system
if not loaded:
    reload()

exports = {
    "loader":  TelosLoader,
    "manager": TelosManager
}
