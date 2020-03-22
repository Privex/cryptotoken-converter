from typing import Optional, Dict

from bhive.asset import Asset
from bhive.blockchain import Blockchain
from privex.helpers import empty

from payments.coin_handlers.Steem.SteemMixin import SteemMixin
from payments.coin_handlers.base import SettingsMixin
from bhive.hive import Hive
from bhive.instance import shared_hive_instance
from django.conf import settings
import logging

log = logging.getLogger(__name__)


class HiveMixin(SettingsMixin):
    """
    SteemMixin - Shared code between SteemManager and SteemLoader

    Designed for the Steem Network with SBD and STEEM support. May or may not work with other Graphene coins.

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

    For **additional settings**, please see the module docstring in :py:mod:`coin_handlers.Steem`

    """
    
    def __init__(self, *args, **kwargs):
        super(HiveMixin, self).__init__(*args, **kwargs)
        self._rpc = None
        
        # List of Steem instances mapped by symbol
        self._rpcs = {}  # type: Dict[str, Hive]
        
        # Internal storage variables for the properties ``asset`` and ``precisions``
        self._asset = self._precision = None
    
    @property
    def rpc(self) -> Hive:
        if not self._rpc:
            # Use the symbol of the first coin for our settings.
            symbol = list(self.all_coins.keys())[0]
            _settings = self.all_coins[symbol].settings['json']
            rpcs = _settings.get('rpcs', settings.HIVE_RPC_NODES)
            
            # If you've specified custom RPC nodes in the custom JSON, make a new instance with those
            # Otherwise, use the global shared_hive_instance.
            rpc_conf = dict(num_retries=5, num_retries_call=3, timeout=20, node=rpcs)
            log.info('Getting BHive instance for coin %s - settings: %s', symbol, rpc_conf)
            
            self._rpc = Hive(node=rpcs, **rpc_conf) if empty(rpcs, itr=True) else Hive(**rpc_conf)  # type: Hive
            self._rpc.set_password_storage(_settings.get('pass_store', 'environment'))
            self._rpcs[symbol] = self._rpc
        return self._rpc
    
    def get_rpc(self, symbol: str) -> Hive:
        """
        Returns a Hive instance for querying data and sending TXs. By default, uses the BHive shared_hive_instance.

        If a custom RPC list is specified in the Coin "custom json" settings, a new instance will be returned with the
        RPCs specified in the json.

        :param symbol: Coin symbol to get BHive RPC instance for
        :return beem.steem.Hive: An instance of :class:`beem.steem.Hive` for querying
        """
        if symbol not in self._rpcs:
            _settings = self.settings[symbol]['json']
            rpcs = _settings.get('rpcs', settings.HIVE_RPC_NODES)
            rpc_conf = dict(num_retries=5, num_retries_call=3, timeout=20, node=rpcs)
            log.info('Getting BHive instance for coin %s - settings: %s', symbol, rpc_conf)
            self._rpcs[symbol] = self.rpc if empty(rpcs, itr=True) else Hive(**rpc_conf)
            self._rpcs[symbol].set_password_storage(_settings.get('pass_store', 'environment'))
        return self._rpcs[symbol]
    
    @property
    def asset(self, symbol=None) -> Optional[Asset]:
        """Easy reference to the BHive Asset object for our current symbol"""
        if not self._asset:
            if empty(symbol):
                if not hasattr(self, 'symbol'):
                    return None
                symbol = self.symbol
            self._asset = Asset(symbol, hive_instance=self.rpc)
        return self._asset
    
    @property
    def precision(self) -> Optional[int]:
        if not hasattr(self, 'symbol'):
            return None
        """Easy reference to the precision for our current symbol"""
        if not self._precision:
            self._precision = int(self.asset.precision)
        return self._precision
    
    def find_steem_tx(self, tx_data, last_blocks=15) -> Optional[dict]:
        """
        Used internally to get the transaction ID after a transaction has been broadcasted

        :param dict tx_data:      Transaction data returned by a beem broadcast operation, must include 'signatures'
        :param int last_blocks:   Amount of previous blocks to search for the transaction
        :return dict:             Transaction data from the blockchain {transaction_id, ref_block_num, ref_block_prefix,
                                  expiration, operations, extensions, signatures, block_num, transaction_num}

        :return None:             If the transaction wasn't found, None will be returned.
        """
        # Code taken/based from @holgern/beem blockchain.py
        chain = Blockchain(hive_instance=self.rpc, mode='head')
        current_num = chain.get_current_block_num()
        for block in chain.blocks(start=current_num - last_blocks, stop=current_num + 5):
            for tx in block.transactions:
                if sorted(tx["signatures"]) == sorted(tx_data["signatures"]):
                    return tx
        return None
