import logging

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction

from payments.coin_handlers import get_loaders
from payments.coin_handlers.base import BaseLoader
from payments.models import Coin, Deposit

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

log = logging.getLogger(__name__)


class Command(BaseCommand):
    # Amount of coin transactions to save per DB transaction
    BATCH = 100
    help = 'Imports transactions from tokens and cryptos'

    def __init__(self):
        super().__init__()
        self.coins = Coin.objects.all()

    def load_txs(self, symbol):
        log.info('Loading transactions for %s...', symbol)
        loaders = get_loaders(symbol)
        for l in loaders:   # type: BaseLoader
            log.debug('Scanning using loader %s', type(l))
            finished = False
            l.load(1000)
            txs = l.list_txs(self.BATCH)
            while not finished:
                log.debug('Loading batch of %s TXs for DB insert', self.BATCH)
                with transaction.atomic():
                    finished = self.import_batch(txs, self.BATCH)

    def import_batch(self, txs: iter, batch: int) -> bool:
        """
        Inserts up to `batch` amount of transactions from `txs` into the Deposit table per run
        Returns a boolean to determine if there are no more transactions to be loaded

        :param txs:   A generator of transactions to import into Deposit()
        :param batch: Amount of transactions to import from the generator
        :return bool: True if there are no more transactions to load
        :return bool: False if there may be more transactions to be loaded
        """
        i = 0
        # var `tx` should be in this format:
        # May contain either (from_account, to_account, memo) or (address,)
        # {txid:str, coin:str (symbol), vout:int, tx_timestamp:datetime, address:str,
        #                 from_account:str, to_account:str, memo:str, amount:Decimal}
        for tx in txs:
            try:
                dupes = Deposit.objects.filter(txid=tx['txid']).count()
                if dupes > 0:
                    log.debug('Skipping TX %s as it already exists', tx['txid'])
                    continue
                log.debug('Storing TX %s', tx['txid'])
                tx['coin'] = Coin.objects.get(symbol=tx['coin'])
                Deposit(**tx).save()
            except:
                log.exception('Error saving TX %s for coin %s, will skip.', tx['txid'], tx['coin'])
            finally:
                i += 1
                if i >= batch:
                    return False
        return i < batch

    def handle(self, *args, **options):
        for c in self.coins:
            try:
                self.load_txs(c.symbol)
            except:
                log.exception('Error loading transactions for coin %s. Moving onto the next coin.', c)

