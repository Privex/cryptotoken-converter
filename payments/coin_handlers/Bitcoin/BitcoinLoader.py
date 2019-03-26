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
import pytz
from datetime import datetime
from decimal import Decimal
from typing import Generator, Iterable, List, Dict
from requests.exceptions import ConnectionError
from django.utils import timezone
from privex.jsonrpc import BitcoinRPC
from urllib3.exceptions import NewConnectionError
from payments.coin_handlers.Bitcoin.BitcoinMixin import BitcoinMixin
from payments.coin_handlers.base.BatchLoader import BatchLoader
from payments.coin_handlers.base.decorators import retry_on_err
from payments.coin_handlers.base.exceptions import DeadAPIError
from steemengine.helpers import empty


log = logging.getLogger(__name__)


class BitcoinLoader(BatchLoader, BitcoinMixin):
    """
    BitcoinLoader - Despite the name, loads TXs from any coin that has a bitcoind-compatible JsonRPC API

    Known to work with: bitcoind, litecoind, dogecoind

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

    For the **required Django settings**, please see the module docstring in :py:mod:`coin_handlers.Bitcoin`

    """

    provides: List[str] = []
    """Dynamically populated by Bitcoin.__init__"""

    rpcs: Dict[str, BitcoinRPC] = {}
    """
    For each coin connection specified in `settings.COIND_RPC`, we map it's symbol to an instantiated instance
    of BitcoinRPC - stored as a static property, ensuring we don't have to constantly re-create them.
    """

    def __init__(self, symbols):
        super(BitcoinLoader, self).__init__(symbols=symbols)
        self.tx_count = 1000
        self.loaded = False
        # Get all RPC objects
        self.rpcs = self._get_rpcs()

    @property
    def settings(self) -> Dict[str, dict]:
        """To ensure we always get fresh settings from the DB after a reload, self.settings gets _prep_settings()"""
        return self._prep_settings()

    @retry_on_err(fail_on=[DeadAPIError])
    def load_batch(self, symbol, limit=100, offset=0, account=None):
        """
        Loads a batch of transactions for `symbol` in their original format into `self.transactions`

        :param str symbol: The coin symbol to load TXs for
        :param int limit:  The amount of transactions to load
        :param int offset: The amount of most recent TXs to skip (for pagination)
        :param str account: NOT USED BY THIS LOADER
        """

        log.debug('Loading batch of %d transactions for %s', int(limit), symbol)
        rpc = self.rpcs[symbol]
        try:
            self.transactions = rpc.listtransactions(count=int(limit), skip=int(offset))
        except (ConnectionRefusedError, ConnectionError, NewConnectionError) as e:
            raise DeadAPIError("{} daemon is not responding! Original exception: {} {}".format(symbol, type(e), str(e)))

    def clean_txs(self, symbol: str, transactions: Iterable[dict], account: str = None) -> Generator[dict, None, None]:
        """
        Filters a list of transactions `transactions` as required, yields dict's conforming with :class:`models.Deposit`

        - Filters out transactions that are not marked as 'receive'
        - Filters out mining transactions
        - Filters by address if `account` is specified
        - Filters out transactions that don't have enough confirms, and are not reported as 'trusted'

        :param symbol:           Symbol of coin being cleaned
        :param transactions:     A ``list<dict>`` or generator producing dict's
        :param account:          If not None, only return TXs sent to this address.
        :return Generator<dict>: A generator outputting dictionaries formatted as below

        Output Format::

          {
            txid:str, coin:str (symbol), vout:int,
            tx_timestamp:datetime, address:str, amount:Decimal
          }

        """

        log.debug('Filtering transactions for %s', symbol)
        for tx in transactions:
            t = self._clean_tx(tx, symbol, account)
            if t is None:
                continue
            yield t

    def _clean_tx(self, tx, symbol, address):
        """Filters an individual transaction. See :meth:`.clean_txs` for info"""

        need_confs = self.settings[symbol]['confirms_needed']
        use_trusted = self.settings[symbol]['use_trusted']

        txid = tx.get('txid', None)
        category = tx.get('category', 'UNKNOWN')
        trust = tx.get('trusted', False)
        amt = tx['amount']
        # To avoid issues with floats, we convert the amount to a string with 8DP
        if type(amt) == float:
            amt = '{0:.8f}'.format(amt)

        log.debug('Filtering/cleaning transaction, Cat: %s, Amt: %s, TXID: %s', category, amt, txid)

        if category != 'receive': return None                                       # Ignore non-receive transactions
        if 'generated' in tx and tx['generated'] in [True, 'true', 1]: return None  # Ignore mining transactions
        # Filter by receiving address if needed
        if not empty(address) and tx['address'] != address: return None
        # If a TX has less confirmations than needed, check if we can trust unconfirmed TXs.
        # If not, we can't accept this TX.
        if int(tx['confirmations']) < need_confs:
            if not use_trusted or trust not in [True, 'true', 1]:
                log.debug('Got %s transaction %s, but only has %d confs, needs %d', symbol, txid,
                          tx['confirmations'], need_confs)
                return None
        d = datetime.utcfromtimestamp(tx['time'])
        d = timezone.make_aware(d, pytz.UTC)

        return dict(
            txid=txid,
            coin=symbol,
            vout=int(tx['vout']),
            tx_timestamp=d,
            address=tx['address'],
            amount=Decimal(amt)
        )
