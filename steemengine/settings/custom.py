"""
This file contains settings that are specific to CryptoToken Converter, and do not affect the core Django
framework.

User specifiable environment variables:

- ``STEEM_RPC_NODES`` - Comma-separated list of one/more Steem RPC nodes. If not set, will use the default beem nodes.

- ``BITSHARES_RPC_NODE`` - Node to use to connect to Bitshares network if Bitshares coin handler is enabled. If not
  set, will default to wss://eu.nodes.bitshares.ws

- ``EX_FEE`` - Conversion fee taken by us, in percentage (i.e. "1" = 1%) **Default:** 0 (no fee)

- ``COIN_HANDLERS`` - A comma separated list of Coin Handler modules to load. **Default:** SteemEngine,Bitcoin

- ``COIN_HANDLERS_BASE`` - If your coin handlers are not located in ``payments.coin_handlers`` then you may change this
  to point to the base module where your coin handlers are located.

- ``LOWFUNDS_NOTIFY`` - If you're using the low wallet balance notifications, you can change how often it re-notifies
  the admin emails ``ADMINS`` if the balance is still too low to fulfill a conversion. (in hours).
  **Default:** ``12``   (hours)

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
from decimal import Decimal
from beem.steem import Steem
from beem.instance import set_shared_steem_instance
from bhive.hive import Hive
from bhive.instance import set_shared_hive_instance
from getenv import env

#########
# Steem Network related settings
####
from privex.helpers import env_csv

# Supply a list of one or more comma-separated Steem RPC nodes. If not set, will use the default beem nodes.
STEEM_RPC_NODES = env_csv('STEEM_RPC_NODES', None)
# Supply a list of one or more comma-separated Steem RPC nodes. If not set, will use the default beem nodes.
HIVE_RPC_NODES = env_csv('HIVE_RPC_NODES', ['https://anyx.io'])
# Set the shared Beem RPC instance to use the specified nodes
steem_ins = Steem(node=STEEM_RPC_NODES, num_retries=5, num_retries_call=3, timeout=20)
steem_ins.set_password_storage('environment')  # Get Beem wallet pass from env var ``UNLOCK``
set_shared_steem_instance(steem_ins)

# Set the shared Beem RPC instance to use the specified nodes
hive_ins = Hive(node=HIVE_RPC_NODES, num_retries=5, num_retries_call=3, timeout=20)
hive_ins.set_password_storage('environment')  # Get Beem wallet pass from env var ``UNLOCK``
set_shared_hive_instance(steem_ins)

#########
# SteemEngine Handler Network related settings
####
SENG_NETWORK_ACCOUNT = env('SENG_NETWORK_ACCOUNT', 'ssc-mainnet1')

SENG_RPC_NODE = env('SENG_RPC_NODE', 'api.steem-engine.com')
SENG_RPC_URL = env('SENG_RPC_URL', '/rpc/contracts')

SENG_HISTORY_NODE = env('SENG_HISTORY_NODE', 'api.steem-engine.com')
SENG_HISTORY_URL = env('SENG_HISTORY_URL', 'accounts/history')

#########
# Bitshares Network related settings
####

BITSHARES_RPC_NODE = env('BITSHARES_RPC_NODE', 'wss://eu.nodes.bitshares.ws')

#########
# General CryptoToken Converter settings
####


ENCRYPT_KEY = env('ENCRYPT_KEY')
"""
Used for encrypting and decrypting private keys so they cannot be displayed in plain text by the admin panel,
or external applications accessing the DB.
Generate an encryption key using ``./manage.py generate_key.``
To print just the key, use ``./manage.py generate_key 2> /dev/null``
"""
EX_FEE = Decimal(env('EX_FEE', '0'))
"""Conversion fee taken by us, in percentage (i.e. "1" = 1%)"""

COIN_TYPES = (
    ('crypto', 'Generic Cryptocurrency',),
    ('token', 'Generic Token'),
)
"""This is used for the dropdown "Coin Type" selection in the Django admin panel. Coin handlers may add to this list."""

COIN_HANDLERS_BASE = env('COIN_HANDLERS_BASE', 'payments.coin_handlers')
"""Load coin handlers from this absolute module path"""

COIN_HANDLERS = env_csv('COIN_HANDLERS', [
    'SteemEngine',
    'Bitcoin',
    'Steem',
    'Hive',
    'EOS',
    'Telos',
    'Bitshares',
    'Appics',
])
"""
Specify in the env var ``COIN_HANDERS`` a comma separated list of local coin handlers
:py:mod:`payments.coin_handlers` to load. If not specified, the default list will be used.
"""

PRIVEX_HANDLERS = env_csv('PRIVEX_HANDLERS', [
    'Golos'
])
"""
These handlers are from the :py:my:`privex.coin_handlers` package, so they're loaded differently to the
handlers listed in :py:attr:`.COIN_HANDLERS`
"""


LOWFUNDS_RENOTIFY = int(env('LOWFUNDS_RENOTIFY', 12))
"""
After the first email to inform admins a wallet is low, how long before we send out a second notification?
(in hours) (Default: 12 hrs)
"""

#########
# Defaults for pre-installed Coin Handlers, to avoid potential exceptions when accessing their settings.
####

COIND_RPC = {}  # Used by coin_handlers.Bitcoin if you don't want to store connection details in DB.
