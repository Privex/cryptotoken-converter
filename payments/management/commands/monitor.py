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
import subprocess

from django.core.management import BaseCommand
from django.db import transaction
from django.utils import timezone

from payments.management import CronLoggerMixin
from payments.models import Deposit

log = logging.getLogger(__name__)

# one hour in seconds
stuck_threshold = 3600

def checkAndProcess(plist, logline):
    log.info(logline)
    if len(plist) < 1:
        log.info('No work to be done.')
        return
    tokens = plist.split(' ')
    if len(tokens) < 1:
        log.info('No work to be done.')
        return
    next_is_pid = False
    for token in tokens:
        if 'hiveeng+' in token:
            next_is_pid = True
        elif next_is_pid == True:
            next_is_pid = False
            pid = token
            running_time = subprocess.run(['ps -p %s -o etimes' % pid], shell=True, capture_output=True, text=True).stdout
            rtime_array = running_time.split('ELAPSED')
            if len(rtime_array) >= 2:
                time_string = rtime_array[1].strip(' \n')
                if len(time_string) > 0:
                    seconds = int(time_string)
                    log.info('pid %s has been running for %s seconds' % (pid, seconds))
                    if (seconds > stuck_threshold):
                        log.info('killing pid %s' % pid)
                        err_result = subprocess.run(['kill %s' % pid], shell=True, capture_output=True, text=True).stderr
                        if (len(err_result) > 0):
                            log.info(err_result)


class Command(CronLoggerMixin, BaseCommand):

    help = 'Checks for any long running processes that may be stuck, and kills them so they will restart.'

    def __init__(self):
        super(Command, self).__init__()

    def handle(self, *args, **options):
        log.info('Checking for stuck processes...')
        plist1 = subprocess.run(['ps -ef | grep -i "ctc/manage.py" | grep -i "convert_coins"'], shell=True, capture_output=True, text=True).stdout
        plist2 = subprocess.run(['ps -ef | grep -i "ctc/manage.py" | grep -i "load_txs"'], shell=True, capture_output=True, text=True).stdout
        checkAndProcess(plist1, 'First pass: checking convert_coins')
        checkAndProcess(plist2, 'Second pass: checking load_txs')
