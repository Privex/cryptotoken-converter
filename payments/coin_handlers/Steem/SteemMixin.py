from typing import Optional, Dict

from beem.asset import Asset
from beem.blockchain import Blockchain
from privex.helpers import empty

from payments.coin_handlers.base import SettingsMixin
from beem.steem import Steem
from beem.instance import shared_steem_instance


class SteemMixin(SettingsMixin):
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

        self._rpc = None

        # List of Steem instances mapped by symbol
        self._rpcs = {}   # type: Dict[str, Steem]

        # Internal storage variables for the properties ``asset`` and ``precisions``
        self._asset = self._precision = None
        super(SteemMixin, self).__init__(*args, **kwargs)

    @property
    def rpc(self) -> Steem:
        if not self._rpc:
            # Use the symbol of the first coin for our settings.
            symbol = list(self.all_coins.keys())[0]
            settings = self.all_coins[symbol].settings['json']
            rpcs = settings.get('rpcs')

            # If you've specified custom RPC nodes in the custom JSON, make a new instance with those
            # Otherwise, use the global shared_steem_instance.
            rpc_conf = dict(num_retries=5, num_retries_call=3, timeout=20, node=rpcs)
            self._rpc = shared_steem_instance() if empty(rpcs, itr=True) else Steem(**rpc_conf)  # type: Steem
            self._rpc.set_password_storage(settings.get('pass_store', 'environment'))
            self._rpcs[symbol] = self._rpc
        return self._rpc

    def get_rpc(self, symbol: str) -> Steem:
        """
        Returns a Steem instance for querying data and sending TXs. By default, uses the Beem shared_steem_instance.

        If a custom RPC list is specified in the Coin "custom json" settings, a new instance will be returned with the
        RPCs specified in the json.

        :param symbol: Coin symbol to get Beem RPC instance for
        :return beem.steem.Steem: An instance of :class:`beem.steem.Steem` for querying
        """
        if symbol not in self._rpcs:
            rpcs = self.settings[symbol]['json'].get('rpcs')
            rpc_conf = dict(num_retries=5, num_retries_call=3, timeout=20, node=rpcs)
            self._rpcs[symbol] = self.rpc if empty(rpcs, itr=True) else Steem(**rpc_conf)
        return self._rpcs[symbol]

    @property
    def asset(self, symbol=None) -> Optional[Asset]:
        """Easy reference to the Beem Asset object for our current symbol"""
        if not self._asset:
            if empty(symbol):
                if not hasattr(self, 'symbol'):
                    return None
                symbol = self.symbol
            self._asset = Asset(symbol, steem_instance=self.rpc)
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
        chain = Blockchain(steem_instance=self.rpc, mode='head')
        current_num = chain.get_current_block_num()
        for block in chain.blocks(start=current_num - last_blocks, stop=current_num + 5):
            for tx in block.transactions:
                if sorted(tx["signatures"]) == sorted(tx_data["signatures"]):
                    return tx
        return None
