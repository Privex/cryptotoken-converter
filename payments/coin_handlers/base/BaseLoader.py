import logging
from abc import ABC, abstractmethod
from typing import Generator
from django.conf import settings
from payments.models import Coin

"""
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


class BaseLoader(ABC):
    """
    BaseLoader - Base class for Transaction loaders

    A transaction loader loads incoming transactions from one or more cryptocurrencies or tokens, whether through
    a block explorer, or through a direct connection to a local RPC node such as steemd or bitcoind using connection
    settings set by the user in their Django settings.

    Transaction loaders must be able to initialise themselves using the following data:

    - The coin symbols ``self.symbols`` passed to the constructor
    - The setting_xxx fields on ``self.coin`` :class:`payments.models.Coin`
    - The Django settings `from django.conf import settings`
    - They should also use the logging instance ``settings.LOGGER_NAME``

    If your class requires anything to be added to the Coin object settings, or the Django ``settings`` file,
    you should write a comment listing which settings are required, which are optional, and their format/type.

    e.g. (Optional) settings.STEEM_NODE - list of steem RPC nodes, or string of individual node, URL format

    They must implement all of the methods in this class, as well as configure the `provides` list to display
    the tokens/coins that this loader handles.
    """

    # A list of token/coin symbols in uppercase that this loader supports e.g.
    # provides = ["LTC", "BTC", "BCH"]
    provides = []

    def __init__(self, symbols: list = None):
        """
        When a transaction loader is initialised, it receives purely the coin that it should be importing transactions
        for. It may also receive symbol=None, which means it should return transactions for ALL possible coins,
        in the same list.

        The class should assume that the developer using it, has already added any additional configuration details
        for your class to their Django settings file.

        Ensure that if you override __init__ that you add super().__init__(any, params, needed) to the start or
        end of your constructor

        :param symbols: A list of coin/token symbols that you should be scanning transactions for.
        """

        self.log = logging.getLogger(__name__)
        symbols = self.provides if symbols is None else symbols

        # Pre-load Coin objects, and filter our symbols to only match those that are enabled.
        # self.coins is a dictionary mapping symbols to their Coin objects, for easy lookup.
        # e.g. self.coins['BTC'].display_name
        coins = Coin.objects.filter(symbol__in=symbols, enabled=True)
        self.coins = {c.symbol: c for c in coins}
        self.symbols = self.coins.keys()

        # For your convenience, self.transactions is pre-defined as a list, for loading into by your functions.
        self.transactions = []

    @abstractmethod
    def list_txs(self, batch=100) -> Generator[dict, None, None]:
        """
        The list_txs function processes the transaction data from :meth:`.load`, as well as handling any
        pagination, if it's required (e.g. only retrieve `batch` transactions at a time from the data source)

        It should first check that :meth:`.load` has been ran if it's required, if the data required
        has not been loaded, it should call self.load()

        To prevent memory leaks, this must be a generator function.

        Below is an example of a generator function body, it loads `batch` transactions from the full transaction
        list, pretends to processes them into `txs`, yields them, then loads another batch after the calling function
        has iterated over the current `txs`

        >>> t = self.transactions   # All transactions
        >>> b = batch
        >>> finished = False
        >>> offset = 0
        >>> # To save memory, process 100 transactions per iteration, and yield them (generator)
        >>> while not finished:
        >>>     txs = []    # Processed transactions
        >>>     # If there are less remaining TXs than batch size, get remaining txs and finish.
        >>>     if (len(t) - offset) < batch:
        >>>         finished = True
        >>>     # Do some sort-of processing on the tx to make it conform to `Deposit`, then append to txs
        >>>     for tx in t[offset:offset + batch]:
        >>>         txs.append(tx)
        >>>     offset += b
        >>>     for tx in txs:
        >>>         yield tx
        >>>     # At this point, the current batch is exhausted. Destroy the tx array to save memory.
        >>>     del txs

        :param int batch:   Amount of transactions to process/load per each batch
        :returns Generator: A generator returning dictionaries that can be imported into :class:`models.Deposit`

        Dict format::

          {txid:str, coin:str (symbol), vout:int, tx_timestamp:datetime,
           address:str, from_account:str, to_account:str, memo:str, amount:Decimal}

        ``vout`` is optional. One of either {from_account, to_account, memo} OR {address} must be included.
        """

        raise NotImplemented("{}.list_txs must be implemented!".format(type(self).__name__))

    @abstractmethod
    def load(self, tx_count=1000):
        """
        The load function should prepare your loader, by either importing all of the data required for filtering,
        or setting up a generator for the :meth:`.list_txs` method to load them paginated.

        It does NOT return anything, it simply creates any connections required, sets up generator functions
        if required for paginating the data, and/or pre-loads the first batch of transaction data.

        :param tx_count: The total amount of transactions that should be loaded PER SYMBOL, most recent first.
        :return: None
        """

        raise NotImplemented("{}.load must be implemented!".format(type(self).__name__))
