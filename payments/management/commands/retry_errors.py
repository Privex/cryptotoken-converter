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
import logging
import datetime

from django.core.management import BaseCommand
from django.db import transaction
from django.utils import timezone

from payments.management import CronLoggerMixin
from payments.models import Deposit

log = logging.getLogger(__name__)


class Command(CronLoggerMixin, BaseCommand):

    help = 'Retries SWAP.WAX withdrawals that are in an error state.'

    def __init__(self):
        super(Command, self).__init__()

    def handle(self, *args, **options):
        start_date = datetime.datetime.now() - datetime.timedelta(hours = 24*3)
        error_deposits = Deposit.objects.filter(status='err',coin__symbol='SWAP.WAX',tx_timestamp__gte=start_date).order_by('-id').iterator(200)
        log.info('Checking for SWAP.WAX errors...')
        for d in error_deposits:
            log.info('found error, setting status to "new" for %s', d)
            d.status = 'new'
            d.save()
        log.info('Finished retrying SWAP.WAX errors.')
