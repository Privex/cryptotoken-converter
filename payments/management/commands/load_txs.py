import logging
import time
import requests

from random import seed
from random import randint

from django.conf import settings
from django.core.management import BaseCommand
from django.core.management.base import CommandParser
from django.db import transaction

from payments.coin_handlers import get_loaders, has_loader
from payments.coin_handlers.base import BaseLoader
from payments.management import CronLoggerMixin
from payments.models import Coin, Deposit
from steemengine.helpers import empty

from payments.coin_handlers.HiveEngine.HiveEngineLoader import HiveEngineLoader

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
seed_num = int(time.time())
seed(seed_num)

class Command(CronLoggerMixin, BaseCommand):
    # Amount of coin transactions to save per DB transaction
    BATCH = 100
    he_node = randint(0, len(settings.HE_RPC_NODES)-1)
    help = 'Imports transactions from tokens and cryptos'

    def __init__(self):
        super(Command, self).__init__()
        self.coins = Coin.objects.filter(enabled=True)

    def load_txs(self, symbol):
        log.info('Loading transactions for %s...', symbol)
        log.debug('%s has loader? %s', symbol, has_loader(symbol))
        if not has_loader(symbol):
            log.warning('Coin %s is enabled, but no Coin Handler has a loader setup for it. Skipping.', symbol)
            return
        loaders = get_loaders(symbol)
        for l in loaders:   # type: BaseLoader
            log.debug('Scanning using loader %s', type(l))
            finished = False
            l.load()
            txs = l.list_txs(self.BATCH)
            is_he_type = isinstance(l, HiveEngineLoader)
            if is_he_type:
                log.info('Initial HE node index: %s, based on random seed %s', self.he_node, seed_num)
            while not finished:
                log.debug('Loading batch of %s TXs for DB insert', self.BATCH)
                with transaction.atomic():
                    finished = self.import_batch(is_he_type, txs, self.BATCH)

    def make_he_url(self, node_num: int) -> str:
        base_url = settings.HE_RPC_NODES[node_num] + '/';
        if base_url[:8] == 'https://':
            base_url = base_url + 'rpc/'
        return base_url

    def call_he_api(self, post_data: dict, dest_type: str) -> dict:
        num_tries = 0

        while True:
            url = ''
            try:
                url = self.make_he_url(self.he_node) + dest_type
                r = requests.post(url, json = post_data).json()
                return r
            except Exception as e:
                num_tries += 1
                log.error('unable to connect to %s (attempt %s)', url, str(num_tries))
                if num_tries <= 5:
                    self.he_node += 1
                    if self.he_node >= len(settings.HE_RPC_NODES):
                        self.he_node = 0
                    log.info('switching to %s', self.make_he_url(self.he_node))
                    time.sleep(3)
                else:
                    log.error('giving up')
                    raise

    def get_tx_info(self, txid: str) -> dict:
        post_data = { 'jsonrpc': '2.0', 'id': 1, 'method': 'getTransactionInfo', 'params': { 'txid': txid } }
        tx_info = self.call_he_api(post_data, 'blockchain')
        return tx_info['result']

    def get_block_info(self, block_num: int) -> dict:
        post_data = { 'jsonrpc': '2.0', 'id': 1, 'method': 'getBlockInfo', 'params': { 'blockNumber': block_num } }
        block_info = self.call_he_api(post_data, 'blockchain')
        return block_info['result']

    def is_trx_verified(self, tx: dict) -> bool:
        log.info('verifying tx %s', str(tx))
        tx_info = self.get_tx_info(tx['txid'])
        block_num = tx_info['blockNumber']
        log.info('tx id %s found in block %s', tx['txid'], block_num)

        confirms = 0
        node_list = []
        block_round = 0
        block_round_hash = ''
        block_witness = ''
        block_signing_key = ''
        block_round_signature = ''
        while confirms < settings.HE_API_VERIFIES_NEEDED:
            self.he_node += 1
            if self.he_node >= len(settings.HE_RPC_NODES):
                self.he_node = 0
            url = self.make_he_url(self.he_node)
            if url in node_list:
                continue # need to make sure we query different nodes each time
            block_info = self.get_block_info(block_num)
            log.info('%s', str(block_info))
            # check url again in case it changed
            url2 = self.make_he_url(self.he_node)
            if url2 != url and url2 in node_list:
                continue

            if block_info['round'] is None or len(block_info['roundHash']) == 0 or len(block_info['witness']) == 0 or len(block_info['signingKey']) == 0 or len(block_info['roundSignature']) == 0:
                log.info('tx id %s not verified yet; skipping for now', tx['txid'])
                time.sleep(3)
                return False

            if len(node_list) == 0:
                block_round = block_info['round']
                block_round_hash = block_info['roundHash']
                block_witness = block_info['witness']
                block_signing_key = block_info['signingKey']
                block_round_signature = block_info['roundSignature']
            elif block_round != block_info['round'] or block_round_hash != block_info['roundHash'] or block_witness != block_info['witness'] or block_signing_key != block_info['signingKey'] or block_round_signature != block_info['roundSignature']:
                log.error('tx id %s: verification mismatch on %s , num confirms: %s , checked nodes: %s', tx['txid'], url2, confirms, str(node_list))
                time.sleep(3)
                return False

            node_list.append(url2)
            confirms += 1
            log.info('tx id %s: verified by %s (confirms: %s of %s', tx['txid'], url2, confirms, str(settings.HE_API_VERIFIES_NEEDED))
            time.sleep(3)

        log.info('tx id %s: verified by %s different nodes, proceeding to process', tx['txid'], confirms)
        return True

    def import_batch(self, is_he_type: bool, txs: iter, batch: int) -> bool:
        """
        Inserts up to `batch` amount of transactions from `txs` into the Deposit table per run
        Returns a boolean to determine if there are no more transactions to be loaded

        :param is_he_type: Indicates if we need to perform enhanced transaction verification for Hive Engine
        :param txs:        A generator of transactions to import into Deposit()
        :param batch:      Amount of transactions to import from the generator
        :return bool:      True if there are no more transactions to load
        :return bool:      False if there may be more transactions to be loaded
        """
        i = 0
        if is_he_type:
            log.info('HE coin type: will check for witness verifications across %s nodes', settings.HE_API_VERIFIES_NEEDED)
        # var `tx` should be in this format:
        # May contain either (from_account, to_account, memo) or (address,)
        # {txid:str, coin:str (symbol), vout:int, tx_timestamp:datetime, address:str,
        #                 from_account:str, to_account:str, memo:str, amount:Decimal}
        for tx in txs:
            try:
                tx = dict(tx)
                dupes = Deposit.objects.filter(txid=tx['txid']).count()
                if dupes > 0:
                    log.debug('Skipping TX %s as it already exists', tx['txid'])
                    continue
                if is_he_type and settings.HE_API_VERIFIES_NEEDED > 0 and not self.is_trx_verified(tx):
                    continue
                log.debug('Storing TX %s', tx['txid'])
                log.debug(f"From: '{tx.get('from_account', 'n/a')}' - Amount: {tx['amount']} {tx['coin']}")
                log.debug(f"Memo: '{tx.get('memo', '--NO MEMO--')}' - Time: {tx['tx_timestamp']}")
                tx['coin'] = Coin.objects.get(symbol=tx['coin'])
                with transaction.atomic():
                    Deposit(**tx).save()
            except:
                log.exception('Error saving TX %s for coin %s, will skip.', tx['txid'], tx['coin'])
            finally:
                i += 1
                if i >= batch:
                    return False
        return i < batch

    def add_arguments(self, parser: CommandParser):
        parser.add_argument('--coins', type=str, help='Comma separated list of symbols to load TXs for')

    def handle(self, *args, **options):
        coins = self.coins

        if not empty(options['coins']):
            coins = self.coins.filter(symbol__in=[c.upper() for c in options['coins'].split(',')])
            log.info('Option --coins was specified. Only loading TXs for coins: %s', [str(c) for c in coins])

        for c in coins:
            try:
                self.load_txs(c.symbol)
            except:
                log.exception('Error loading transactions for coin %s. Moving onto the next coin.', c)

