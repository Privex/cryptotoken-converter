import sys
from decimal import Decimal

from datetime import datetime
from django.core.management.base import BaseCommand

from fees.admin import get_payout_table, do_payout, get_native_coin
from fees.models import FeePayout
from payments.models import Coin

import logging

log = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Creates and pays out FeePayouts'

    def add_arguments(self, parser):
        parser.add_argument(
            'coin',
            help='The coin to payout (optional)',
            nargs='?'
        )

    def handle(self, *args, **options):
        for coin, p in get_payout_table():
            if options['coin'] and get_native_coin(coin) != options['coin'].upper():
                self.stdout.write(self.style.NOTICE(f'Ignoring coin {coin}'))
                continue
            try:
                if not Coin.objects.get(symbol=coin).enabled:
                    continue
            except Coin.DoesNotExist:
                continue
            if p.get('he_cut', 0) > 0:
                fp = FeePayout.objects.create(coin_id=coin, amount=p['he_cut'], notes='hive engine')
            elif p.get('privex_cut', 0) > 0:
                fp = FeePayout.objects.create(coin_id=coin, amount=p['privex_cut'], notes='privex')
            else:
                self.stdout.write(self.style.NOTICE('Payout amount is zero'))
                continue
            try:
                status, msg = do_payout(fp)
            except Exception as e:
                log.exception(e)
                fp.last_error = f"{e.__class__.__name__}: {e}"
                fp.save(update_fields=['last_error', 'updated_at'])
                self.stderr.write(self.style.ERROR(f'Unable to payout coin {coin}'))
                continue
            if status:
                self.stdout.write(self.style.SUCCESS(msg))
            else:
                self.stderr.write(self.style.ERROR(msg))
