"""
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
import json
import logging

from celery.result import AsyncResult
from django.core.management import BaseCommand
from django.db import transaction
from lockmgr.lockmgr import LockMgr, Locked
from privex.helpers import is_true

from payments import tasks
from payments.coin_handlers import get_manager
from payments.coin_handlers.base import SettingsMixin
from payments.exceptions import ConvertError, ConvertInvalid, CTCException
from payments.lib import ConvertCore
from payments.lib.task_helpers import handle_deposit_errors
from payments.lib import task_helpers as t_help
from payments.management import CronLoggerMixin
from payments.models import Deposit, Coin, CoinPair, TaskLog
from steemengine.helpers import empty

log = logging.getLogger(__name__)


class Command(CronLoggerMixin, BaseCommand):

    help = 'Processes deposits, and handles coin conversions'

    def __init__(self):
        super(Command, self).__init__()

    def add_arguments(self, parser):
        # Named (optional) arguments
        parser.add_argument(
            '--dry',
            action='store_true',
            help="Dry run (don't actually send any coins, just print what would happen)",
        )

        parser.add_argument('--coins', type=str, help='Comma separated list of symbols to run conversions for')

    def handle(self, *args, **options):
        # Load all "new" deposits, max of 200 in memory at a time to avoid memory leaks.
        new_deposits = Deposit.objects.filter(status='new').iterator(200)
        log.info('Coin converter and deposit validator started')
        coins = None
        if not empty(options['coins']):
            coins = options['coins'].split(',')
            log.info('Option --coins was specified. Only loading TXs for coins: %s', [str(c) for c in coins])
        
        # ----------------------------------------------------------------
        # Validate deposits and map them to a destination coin / address
        # ----------------------------------------------------------------
        log.info('Queueing deposits for processing that are in state "new"')
        
        for d in new_deposits:
            try:
                if coins is not None and d.coin.symbol not in coins:
                    log.debug('Skipping deposit %s as --coins was specified, and did not match.', d)
                    continue
                log.debug('Validating and mapping deposit %s', d)
                tasks.background_task(
                    tasks.check_deposit, 'commands.convert_coins',
                    t_conf=dict(
                        link=tasks.convert_deposit.s().on_error(tasks.handle_errors.s(d.id)),
                        link_error=tasks.handle_errors.s(d.id)
                    ),
                    deposit_id=d.id
                )
            except:
                log.exception('SERIOUS ERROR: An unknown error occurred while queueing validation for deposit %s', d)

        log.info('Finished queueing new deposits for validation and conversion')

        log.debug('Resetting any Coins "funds_low" if they have no "mapped" deposits')
        for c in Coin.objects.filter(funds_low=True):
            log.debug(' -> Coin %s currently has low funds', c)
            map_deps = c.deposit_converts.filter(status='mapped').count()
            if map_deps == 0:
                log.debug(' +++ Coin %s has no mapped deposits, resetting funds_low to false', c)
                c.funds_low = False
                c.save()
            else:
                log.debug(' !!! Coin %s still has %d mapped deposits. Ignoring.', c, map_deps)
        log.debug('Finished resetting coins with "funds_low" that have been resolved.')

