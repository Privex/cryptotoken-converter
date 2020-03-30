"""
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
from typing import Dict, Any, List, Optional

from django.conf import settings
from privex.steemengine import SteemEngineToken

from payments.coin_handlers.base import SettingsMixin


log = logging.getLogger(__name__)


def mk_seng_rpc(rpc_settings: dict = None, **kwargs) -> SteemEngineToken:
    """
    Get a :class:`.SteemEngineToken` instance using the default settings::
    
        >>> rpc = mk_seng_rpc()

    Get a :class:`.SteemEngineToken` instance using dictionary settings (rpc_settings)::
    
        >>> rpc2 = mk_seng_rpc({'rpc_node' : 'api.hive-engine.com','network_account' : 'ssc-testnet'})

    Get a :class:`.SteemEngineToken` instance using individual kwarg settings::

        >>> rpc3 = mk_seng_rpc(rpc_node='api.hive-engine.com', network_account='ssc-testnet')
    
    :param dict rpc_settings:      Specify the settings as a dictionary (same keys as kwargs below)
    :param kwargs:                 Alternatively, specify the settings as keyword args
    
    :keyword str rpc_node:         The hostname for the contract API server, e.g. ``api.steem-engine.com``
    :keyword str rpc_url:          The URL for the contract API e.g. ``/rpc/contracts``
    :keyword str history_node:     The hostname for the history API server, e.g. ``api.steem-engine.com``
    :keyword str history_url:      The URL for the history API e.g. ``accounts/history``
    :keyword str network_account:  The "network account" for SteemEngine, e.g. ``ssc-mainnet1``
    :keyword str network:          Chain to run on (``steem`` or ``hive``)
    
    :return SteemEngineToken rpc:  An instance of :class:`.SteemEngineToken`
    """
    rpc_settings = {**kwargs} if not rpc_settings else rpc_settings
    
    rpc_node = rpc_settings.get('rpc_node', settings.SENG_RPC_NODE)
    rpc_url = rpc_settings.get('rpc_url', settings.SENG_RPC_URL)
    history_node = rpc_settings.get('history_node', settings.SENG_HISTORY_NODE)
    history_url = rpc_settings.get('history_url', settings.SENG_HISTORY_URL)
    network_account = rpc_settings.get('network_account', settings.SENG_NETWORK_ACCOUNT)
    network = rpc_settings.get('network', settings.SENG_NETWORK)

    return SteemEngineToken(
        network_account=network_account,
        network=network,
        history_conf=dict(hostname=history_node, url=history_url),
        hostname=rpc_node,
        url=rpc_url
    )


class SteemEngineMixin(SettingsMixin):
    _eng_rpc: Optional[SteemEngineToken]
    _eng_rpcs: Dict[str, SteemEngineToken]
    
    def __init__(self, *args, **kwargs):
        self._eng_rpc = None
        self._eng_rpcs = {}
        super(SteemEngineMixin, self).__init__(*args, **kwargs)

    @property
    def eng_rpc(self) -> SteemEngineToken:
        if not self._eng_rpc:
            # Use the symbol of the first coin for our settings.
            symbol = list(self.all_coins.keys())[0]
            _settings = self.all_coins[symbol].settings['json']
        
            # If you've specified custom RPC nodes in the custom JSON, make a new instance with those
            # Otherwise, use the global shared_steem_instance.
            log.info('Getting SteemEngine instance for coin %s - settings: %s', symbol, _settings)
            
            self._eng_rpc = mk_seng_rpc(rpc_settings=_settings)
            self._eng_rpcs[symbol] = self._eng_rpc
        return self._eng_rpc

    def get_rpc(self, symbol: str) -> SteemEngineToken:
        """
        Returns a SteemEngineToken instance for querying data and sending TXs.

        If a custom RPC config is specified in the Coin "custom json" settings, a new instance will be returned with the
        RPC config specified in the json.

        :param symbol: Coin symbol to get Beem RPC instance for
        :return beem.steem.Steem: An instance of :class:`beem.steem.Steem` for querying
        """
        if symbol not in self._eng_rpcs:
            _settings = self.all_coins[symbol].settings['json']
            log.info('Getting SteemEngine instance for coin %s - settings: %s', symbol, _settings)

            self._eng_rpcs[symbol] = mk_seng_rpc(rpc_settings=_settings)
        return self._eng_rpcs[symbol]

