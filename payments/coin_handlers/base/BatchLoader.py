import logging
from abc import abstractmethod, ABC
from typing import Generator, Iterable

from django.conf import settings

from payments.coin_handlers import BaseLoader
from payments.coin_handlers.base.decorators import retry_on_err
from payments.coin_handlers.base.exceptions import DeadAPIError
from payments.models import Coin
from steemengine.helpers import empty

log = logging.getLogger(__name__)


class BatchLoader(BaseLoader, ABC):
    """
    BatchLoader - An abstract sub-class of BaseLoader which comes with some pre-written batching/chunking functions

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

    This class is designed to save you time from re-writing your own "batching" / "chunking" functions.

    Batching / chunking is a memory efficiency technique to prevent RAM leaks causing poor performance or crashes.
    Instead of loading all 1K - 10K transactions into memory, you load only a small amount of transactions, such as
    100 transactions, then you use a Python generator (the yield keyword) to return individual transactions, quietly
    loading the next "batch" / "chunk" of 100 TXs after the first set has been processed, without interrupting the
    caller's `for` loop or other iteration.

    This allows other functions to iterate over the transactions and process them on the fly, instead of having to load
    the entire 1-10K transaction list into memory first.

    The use of generators throughout this class helps to prevent the problem of RAM leaks due to constant
    duplication of the transaction list (e.g. self.transactions, self.filtered_txs, self.cleaned_txs), especially
    when the transaction lists contains thousands of transactions.

    To use this class, simply extend it (instead of BaseLoader), and make sure to implement the two abstract methods:

     - `load_batch` - Loads and stores a small batch of raw (original format) transactions for a given coin
     - `clean_txs`  - Filters the loaded TXs, yielding TXs (conformed to be compatible with :class:`models.Deposit`)
                      that were received by us (not sent), and various sanity checks depending on the type of coin.

    If your Loader is for a coin which uses an account/memo system, set `self.need_account = True` before calling
    BatchLoader's constructor, and it will remove coins in self.symbols/coins that do not have a non-empty/null
    `our_account` column.

    You're free to override any methods if you need to, just make sure to call this class's constructor __init__
    before/after your own constructor, otherwise some methods may break.

    Flow of this class::

      Transaction loading cron
         |
         V--> __init__(symbols:list)
         |--> load(tx_count:int)
         |--> list_txs(batch:int) -> _list_txs(coin:Coin, batch:int)
         V                              |--> load_batch(account, symbol, offset)
                                        V--> clean_txs(account, symbol, txs)

    """

    def __init__(self, symbols: list = None):
        super(BatchLoader, self).__init__(symbols)
        self.tx_count = 1000
        self.loaded = False
        # If you want to filter out database coin objects that don't have `our_account` set, then set
        # `self.need_account` to True in your constructor before calling this parent constructor
        if not hasattr(self, 'need_account'):
            self.need_account = False

    def _list_txs(self, coin: Coin, batch=100) -> Generator[dict, None, None]:
        """
        Loads transactions for an individual coin using :meth:`.load_batch` in batches of `batch`, filters transactions
        and conforms them to Deposit using :meth:`.clean_txs`, then yields each one as a dict using a generator for
        memory efficiency.

        :param models.Coin   coin:    The coin to list TXs for - as an individual coin object from the database
        :param         int  batch:    The amount of transactions to load per iteration
        """

        finished = False
        offset = txs_loaded = 0
        while not finished:
            account = coin.our_account if self.need_account else None
            self.load_batch(symbol=coin.symbol_id, limit=batch, offset=offset, account=account)
            txs_loaded += len(self.transactions)
            # If there are less remaining TXs than batch size - this usually means we've hit the end of the results.
            # If that happens, or we've hit the transaction limit, then yield the remaining txs and exit.
            if len(self.transactions) < batch or txs_loaded >= self.tx_count:
                finished = True
            # Convert the transactions to Deposit format (clean_txs is generator, so must iterate it into list)
            txs = list(self.clean_txs(account=account, symbol=coin.symbol_id, transactions=self.transactions))
            del self.transactions  # For RAM optimization, destroy the original transaction list, as it's not needed.
            offset += batch
            for tx in txs:
                yield tx
            del txs  # At this point, the current batch is exhausted. Destroy the tx array to save memory.

    def list_txs(self, batch=100) -> Generator[dict, None, None]:
        """
        Yield transactions for all coins in `self.coins` as a generator, loads transactions in batches of `batch`
        and returns them seamlessly using a generator.

        If :meth:`.load()` hasn't been ran already, it will automatically call self.load()

        :param batch: Amount of transactions to load per batch
        :return Generator[dict, None, None]: Generator yielding dict's that conform to :class:`models.Deposit`
        """

        if not self.loaded:
            self.load()

        for symbol, c in self.coins.items():
            try:
                for tx in self._list_txs(coin=c, batch=batch):
                    yield tx
            except DeadAPIError as e:
                log.error('Skipping coin %s as API/Daemon is not responding: %s', c, str(e))
            except:
                log.exception('Something went wrong while loading transactions for coin %s. Skipping for now.', c)
                continue

    def load(self, tx_count=1000):
        """
        Simply imports `tx_count` into an instance variable, and then sets `self.loaded` to True.

        If `self.need_account` is set to True by a child/parent class, this method will remove any coins from
        `self.coins` and `self.symbols` which have a blank/null `our_account` in the DB, ensuring that you can trust
        that all coins listed in symbols/coins have an `our_account` which isn't empty or None.

        :param int tx_count:  The amount of transactions to load per symbol specified in constructor
        """

        log.debug('Initialising %s with TX count %d', type(self).__name__, tx_count)
        self.tx_count = tx_count
        if not self.need_account:
            self.loaded = True
            return
        for symbol, coin in self.coins.items():
            if not empty(coin.our_account):
                continue
            log.warning('The coin %s does not have `our_account` set. Refusing to load transactions.', coin)
            del self.coins[symbol]
            self.symbols = [s for s in self.symbols if s != symbol]

        self.loaded = True

    @abstractmethod
    def load_batch(self, symbol, limit=100, offset=0, account=None):
        """
        This function should load `limit` transactions in their raw format from your data source, skipping
        the `offset` newest TXs efficiently, and store them in the instance var `self.transactions`

        If you use the included decorator :py:func:`decorators.retry_on_err`, if any exceptions are thrown by your
        method, it will simply re-run it with the same arguments up to 3 tries by default.

        Basic implementation:

        >>> @retry_on_err()
        >>> def load_batch(self, symbol, limit=100, offset=0, account=None):
        >>>     self.transactions = self.my_rpc.get_tx_list(limit, offset)

        :param symbol:   The symbol to load a batch of transactions for
        :param limit:    The amount of transactions to load
        :param offset:   Skip this many transactions (most recent first)
        :param account:  An account name, or coin address to filter transactions using
        """

        raise NotImplemented('{}.load_batch is not implemented!'.format(type(self).__name__))

    @abstractmethod
    def clean_txs(self, symbol: str, transactions: Iterable[dict], account: str = None) -> Generator[dict, None, None]:
        """
        Filters a list of transactions ``transactions`` as required, yields dict's conforming
        with :class:`models.Deposit`

        Important things when implementing this function:

        - Make sure to filter out transactions that were sent from our own wallet/account - otherwise internal
          transfers will cause problems.
        - Make sure each transaction is destined to us

          - If your loader is account-based, make sure to only yield transactions where tx["to_account"] == account.
          - If your loader is address-based, make sure that you only return transactions that are being received by
            our wallet, not being sent from it.

            - If ``account`` isn't None, assume that you must yield TXs sent to the given crypto address ``account``

        - If your loader deals with smart contract networks e.g. ETH, EOS, make sure that you only return transactions
          valid on the matching smart contract, don't blindly trust the symbol!
        - Make sure that every dict that you ``yield`` conforms with the return standard shown for
          :py:meth:`BaseLoader.list_txs`

        - While transactions is normally a list<dict> you should assume that it could potentially be a
          Generator, writing the code Generator-friendly will ensure it can handle both lists and Generator's.


        Example:

        >>> def clean_txs(self, symbol: str, transactions: Iterable[dict],
        >>>               account: str = None) -> Generator[dict, None, None]:
        >>>     for tx in transactions:
        >>>         try:
        >>>             if tx['from'].lower() == 'tokens': continue       # Ignore token issues
        >>>             if tx['from'].lower() == account: continue        # Ignore transfers from ourselves.
        >>>             if tx['to'].lower() != account.lower(): continue  # If we aren't the receiver, we don't need it.
        >>>             clean_tx = dict(
        >>>                 txid=tx['txid'], coin=symbol, tx_timestamp=parse(tx['timestamp']),
        >>>                 from_account=tx['from'], to_account=tx['to'], memo=tx['memo'],
        >>>                 amount=Decimal(tx['quantity'])
        >>>             )
        >>>             yield clean_tx
        >>>         except:
        >>>             log.exception('Error parsing transaction data. Skipping this TX. tx = %s', tx)
        >>>             continue

        :param symbol:        The symbol of the token being filtered
        :param transactions:  A list<dict> of transactions to filter
        :param account:       The 'to' account or crypto address to filter by (only required for account-based loaders)
        :return:              A generator yielding dict's conforming to :class:`models.Deposit`, check the PyDoc
                              return info for :py:meth:`coin_handlers.base.BaseLoader.list_txs` for current format.
        """

        raise NotImplemented('{}.clean_txs is not implemented!'.format(type(self).__name__))


