import logging

from django.core.management import BaseCommand
from django.core.management.base import CommandParser
from django.db import transaction
from lockmgr.lockmgr import LockMgr, Locked

from payments import tasks
from payments.coin_handlers import get_loaders, has_loader
from payments.coin_handlers.base import BaseLoader
from payments.management import CronLoggerMixin
from payments.models import Coin, Deposit
from steemengine.helpers import empty

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


class Command(CronLoggerMixin, BaseCommand):
    help = 'Imports transactions from tokens and cryptos'

    def __init__(self):
        super(Command, self).__init__()
        self.coins = Coin.objects.filter(enabled=True)

    def add_arguments(self, parser: CommandParser):
        parser.add_argument('--coins', type=str, help='Comma separated list of symbols to load TXs for')

    def handle(self, *args, **options):
        coins = self.coins

        if not empty(options['coins']):
            coins = self.coins.filter(symbol__in=[c.upper() for c in options['coins'].split(',')])
            log.info('Option --coins was specified. Only loading TXs for coins: %s', [str(c) for c in coins])

        for c in coins:
            tasks.background_task(tasks.load_txs, 'commands.load_txs', symbol=c.symbol)

