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
from decimal import Decimal, getcontext, ROUND_DOWN
from typing import Dict, List, Iterable, Generator, Union

import pytz
from beem.account import Account
from beem.asset import Asset
from dateutil.parser import parse
from django.utils import timezone

from payments.coin_handlers import BaseLoader
from payments.coin_handlers.Steem.SteemMixin import SteemMixin
from steemengine.helpers import empty

log = logging.getLogger(__name__)
getcontext().rounding = ROUND_DOWN


class SteemLoader(BaseLoader, SteemMixin):
    """
    SteemLoader - Loads transactions from the Steem network

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

    provides = ["STEEM", "SBD"]  # type: List[str]
    """
    This attribute is automatically generated by scanning for :class:`models.Coin` s with the type ``steembase``. 
    This saves us from hard coding specific coin symbols. See __init__.py for populating code.
    """

    def __init__(self, symbols):
        super(SteemLoader, self).__init__(symbols=symbols)
        self.tx_count = 100
        self.loaded = False
        self._rpc = None
        self._rpcs = {}

    @property
    def settings(self) -> Dict[str, dict]:
        """To ensure we always get fresh settings from the DB after a reload"""
        return dict(((sym, c.settings) for sym, c in self.coins.items()))

    def load(self, tx_count=10000):
        # Unlike other coins, it's important to load a lot of TXs, because many won't actually be transfers
        # Thus the default TX count for Steem is 10,000
        self.tx_count = tx_count
        for symbol, coin in self.coins.items():
            if not empty(coin.our_account):
                continue
            log.warning('The coin %s does not have `our_account` set. Refusing to load transactions.', coin)
            del self.coins[symbol]
            self.symbols = [s for s in self.symbols if s != symbol]

    def list_txs(self, batch=0) -> Generator[dict, None, None]:
        if not self.loaded:
            self.load()
        for symbol, c in self.coins.items():
            acc_name = c.our_account
            acc = Account(acc_name, steem_instance=self.get_rpc(c.symbol_id))
            # get_account_history returns a generator with automatic batching, so we don't have to worry about batches.
            txs = acc.get_account_history(-1, self.tx_count, only_ops=['transfer'])
            yield from self.clean_txs(symbol=c.symbol_id, transactions=txs, account=acc_name)

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
            try:
                t = self.clean_tx(tx, symbol, account)
                if t is None:
                    continue
                # Re-write the coin symbol into the database symbol
                t['coin'] = self.coins[symbol].symbol
                yield t
            except (AttributeError, KeyError) as e:
                log.warning('Steem TX missing important key? %s', str(e))
            except:
                log.exception('Error filtering Steem TX, skipping... TX data: %s', tx)

    def clean_tx(self, tx: dict, symbol: str, account: str, memo: str = None, memo_case: bool = False) -> Union[dict, None]:
        """Filters an individual transaction. See :meth:`.clean_txs` for info"""
        # log.debug(tx)
        if tx.get('type', 'NOT SET') != 'transfer':
            log.debug('Steem TX is not transfer. Type is: %s', tx.get('type', 'NOT SET'))
            return None

        txid = tx.get('trx_id', None)

        _am = tx['amount']  # Transfer ops contain a dict 'amount', containing amount:int, nai:str, precision:int

        if type(_am) is str:   # Extract and validate asset 'ABC' from '12.345 ABC'
            amt, _symbol = _am.split()
            _asset = Asset(symbol, steem_instance=self.get_rpc(symbol))
        else:  # Conv asset ID (e.g. @@000000021) to symbol, i.e. "STEEM"
            _asset = Asset(_am['nai'], steem_instance=self.get_rpc(symbol))
            # Convert integer amount/precision to Decimal's, preventing floating point issues
            amt_int = Decimal(_am['amount'])
            amt_prec = Decimal(_am['precision'])

            amt = amt_int / (Decimal(10) ** amt_prec)  # Use precision value to convert from integer amt to decimal amt
        # Get validated symbol from beem Asset
        amt_sym = str(_asset.symbol)
        if amt_sym != symbol:  # If the symbol doesn't match the symbol we were passed, skip this TX
            return None

        tx_memo = tx.get('memo')

        log.debug('Filtering/cleaning steem transaction, Amt: %f, TXID: %s', amt, txid)

        if tx['to'] != account or tx['from'] == account:
            return None    # If the transaction isn't to us (account), or it's from ourselves, ignore it.
        if not empty(memo) and (tx_memo != memo or (not memo_case and tx_memo.lower() != memo.lower())):
            return None

        d = parse(tx['timestamp'])
        d = timezone.make_aware(d, pytz.UTC)

        return dict(
            txid=txid,
            coin=symbol,
            vout=int(tx.get('op_in_trx', 0)),
            tx_timestamp=d,
            from_account=tx.get('from', None),
            to_account=tx.get('to', None),
            memo=tx_memo,
            amount=Decimal(amt)
        )
