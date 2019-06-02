import logging
from decimal import Decimal
from typing import Generator, List, Iterable

import pytz
from dateutil.parser import parse
from django.core.cache import cache
from django.utils import timezone

from payments.coin_handlers.EOS.EOSMixin import EOSMixin
from payments.coin_handlers.base import retry_on_err, AccountNotFound, BaseLoader
from steemengine.helpers import empty

log = logging.getLogger(__name__)


class EOSLoader(BaseLoader, EOSMixin):

    def __init__(self, symbols):
        super().__init__(symbols=symbols)
        self.tx_count = 1000
        self.loaded = False

    # except AccountNotFound:
    #     log.warning(f'The coin {coin} does not have `our_account` set. Refusing to load transactions.')
    # except TokenNotFound:
    #     log.warning(f'The coin {coin} does not exist in {__name__}.settings. Refusing to load transactions.')
    # except MissingTokenMetadata:
    #     log.warning(f'The coin {coin} does not have `contract` set. Refusing to load transactions.')
    def load(self, tx_count=1000):
        """
        Prepares the loader by disabling any symbols / coin objects that don't have an `our_account` set, or don't
        have a `contract` set in either :py:attr:`models.Coin.settings_json` or :py:attr:`.default_contracts`

        :param tx_count: Amount of transactions to load per account, most recent first
        :return: None
        """
        log.info('Loading EOS transactions...')

        self.tx_count = tx_count
        # Loop over each Coin we're responsible for, make sure every EOS token has both an `our_account` and
        # a contract set (either in Coin.setting_json or EOSMixin.default_contracts). Disable any that don't.
        for symbol, coin in self.coins.items():
            safe = False   # Assume a token is not valid by default.
            symbol = symbol.upper()
            try:
                if empty(coin.our_account):
                    raise AccountNotFound(f'EOS token "{coin}" has blank `our_account`. Refusing to load TXs.')
                self.get_contract(symbol)
            except Exception as e:
                log.warning(f'Refusing to load TXs for EOS token "{coin}". Reason: {type(e)} - {str(e)}')
            else:
                log.debug(f'EOS token with symbol "{coin}" passed tests. Has non-empty our_account and contract.')
                safe = True
            # If a token didn't pass basic sanity checks (has our account + contract), remove it from coins and symbols.
            if not safe:
                log.debug(f'Removing symbol "{symbol}" from self.coins and self.symbols...')
                del self.coins[symbol]
                self.symbols = [s for s in self.symbols if s != symbol]
        log.debug('Remaining EOSLoader symbols that were not disabled: %s', self.symbols)
        self.loaded = True

    def list_txs(self, batch=100) -> Generator[dict, None, None]:
        """
        Get transactions for all coins in `self.coins` where the 'to' field matches coin.our_account
        If :meth:`.load()` hasn't been ran already, it will automatically call self.load()

        :param batch: Amount of transactions to load per batch
        :return: Generator yielding dict's that conform to :class:`models.Deposit`
        """
        if not self.loaded:
            self.load()

        for symbol, c in self.coins.items():
            try:
                sym = c.symbol.upper()
                log.debug(f'Loading EOS actions for token "{sym}", received to "{c.our_account}"')
                actions = self.get_actions(c.our_account, self.tx_count)
                yield from self.clean_txs(c.our_account, sym, self.get_contract(sym), actions)
            except:
                log.exception('Something went wrong while loading transactions for coin %s. Skipping for now.', c)
                continue

    def clean_txs(self, account, symbol, contract, transactions: Iterable[dict]) -> Generator[dict, None, None]:
        """
        Filters a given Iterable of dict's containing raw EOS "actions":

         - Finds only incoming `transfer` transactions from accounts that are not us (`account`)
         - Filters transactions by both `symbol` and verifies they're from the `contract` account
         - Outputs valid incoming TXs in the standardised Deposit format.

        :param str account:         The account which should be receiving `symbol`
        :param str symbol:          The coin symbol to search for, e.g. "EOS"
        :param str contract:        The EOS contract account to filter by, e.g. "eosio.token"
        :param Iterable[dict] transactions:   An iterable list/generator of EOS actions as dict's
        :return Generator cleaned_txs:  A generator yielding valid Deposit TXs as dict's
        """
        for tx in transactions:
            try:
                # Decompose various information from the complex EOS transaction format
                #  - The `action_trace` contains most of the information about the transaction
                #  - The `receipt` contains information about the receiver
                #  - The `act` contains metadata about the transaction such as the contract account, tx type, and body
                #  - The `data` of `act` contains the actual sender username, and the memo
                tr = tx['action_trace']
                txid, rec, act = tr['trx_id'], tr['receipt'], tr['act']
                to_acc = rec['receiver']
                contract_acc, tx_type, tx_data = act['account'], act['name'], act['data']
                # Some transfers might not contain a memo key at all, so fallback to '' if the key doesn't exist.
                memo, from_acc = tx_data.get('memo', ''), tx_data['from']

                # In EOS, the act['account'] (contract_acc) account is the owner of the smart contract
                # not the actual user who sent it. The "receiver" (to_acc) however, should be us.
                if contract_acc != contract or to_acc != account:
                    continue

                if tx_type != 'transfer':
                    continue  # if the transaction isn't a transfer, we don't care.
                if from_acc == account:
                    continue  # skip our own transactions

                amount, txcurrency = tuple(tx_data['quantity'].split(' '))
                if txcurrency != symbol:
                    continue  # skip foreign currency

                ts = parse(tx['block_time'])
                ts = timezone.make_aware(ts, pytz.UTC)

                yield dict(
                    txid=txid, coin=symbol, tx_timestamp=ts, from_account=tx_data['from'],
                    to_account=to_acc, memo=memo, amount=Decimal(amount)
                )
            except Exception:
                log.exception('Error parsing transaction data. Skipping this TX. tx = %s', tx)
                continue

    @retry_on_err(3, 3)     # Auto-retry on exception up to 3 times, with 3 seconds delay between attempts
    def get_actions(self, account: str, count=100) -> List[dict]:
        """
        Loads EOS transactions for a given account, and caches them per account to avoid constant queries.

        :param account:  The EOS account to load transactions for
        :param count:    Amount of transactions to load
        :return list transactions: A list of EOS transactions as dict's
        """
        cache_key = f'eos_actions:{account}'
        actions = cache.get(cache_key)

        if empty(actions):
            log.info('Loading EOS actions for %s from node %s', account, self.url)
            c = self.eos
            data = c.get_actions(account, pos=-1, offset=-count)
            actions = data['actions']
            cache.set(cache_key, actions, timeout=60)

        return actions
