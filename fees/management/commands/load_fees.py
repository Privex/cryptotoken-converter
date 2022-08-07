import sys
from decimal import Decimal

from datetime import datetime
from django.core.management.base import BaseCommand

from fees.models import FeePayout


class Command(BaseCommand):
    help = 'Loads fees from tsv'

    def add_arguments(self, parser):
        parser.add_argument(
            'file',
            help='The .tsv file to load',
        )

    def handle(self, file, *args, **options):
        f = open(file, 'r')
        for line in f:
            line = line.split('\t')
            print(line)
            qs = FeePayout.objects
            if line[1] == 'SteemEngine':
                qs = qs.using('steemengine')
            elif line[1] != 'HiveEngine':
                continue
            qs.filter(id=qs.create(coin_id=line[3], amount=line[4].replace(',', '')).id).update(
                created_at=datetime.strptime(line[0], '%d %b %Y %M:%S'))
        f.close()
