import random
from decimal import Decimal
from typing import Generator, Iterable

from faker import Faker

from payments.coin_handlers import BaseManager
from payments.coin_handlers.base.BatchLoader import BatchLoader
from payments.coin_handlers.base import exceptions

fake = Faker()


def fake_amt(_min=0.01, _max=20) -> Decimal:
    return Decimal('{0:.8f}'.format(random.uniform(_min, _max)))


def fake_txid():
    return fake.sha1(raw_output=False)


def fake_addr():
    return fake.md5()


def fake_user():
    return fake.user_name()


class MockLoader(BatchLoader):
    """
    This is a mock Loader class, used for testing code which uses Coin Handlers.

    If you don't change ``fake_all`` to False, the :py:meth:`.load` method will generate ``tx_count`` fake transactions
    made of random data.

    For precise testing, set ``fake_all`` to False, and manually add the transactions you want to test with
    to the attribute ``fake_txs``
    """
    provides = ['MOCKTESTCOIN', 'FAKEDESTCOIN']

    fake_txs = []

    fake_all = True
    """If this is true, load() will automatically fill fake_txs with generated fake txs for scanning"""

    def __init__(self, symbols):
        super().__init__(symbols=symbols)
        self.tx_count = 100
        self.loaded = False

    @staticmethod
    def reset():
        """Reset static attributes to default"""
        MockLoader.fake_txs = []
        MockLoader.fake_all = True
        MockLoader.provides = ['MOCKTESTCOIN', 'FAKEDESTCOIN']

    def load_batch(self, symbol, limit=10, offset=0, account=None):
        self.transactions = self.fake_txs[offset:offset + limit]

    def clean_txs(self, symbol: str, transactions: Iterable[dict], account: str = None) -> Generator[dict, None, None]:
        for tx in transactions:
            if tx['coin'].upper() != symbol: continue
            if account is not None and tx.get('to_account') != account: continue
            yield tx

    def fake_memo(self, coin=provides[1], address=None, dest_memo=None) -> str:
        """Generate a fake memo. Set dest_memo to False to disable destination memo in output"""
        if address is None:
            address = fake.user_name()
        if dest_memo is None:
            dest_memo = fake.sentence(nb_words=6, variable_nb_words=True, ext_word_list=None)
        if dest_memo is False:
            return '{} {}'.format(coin, address)
        return '{} {} {}'.format(coin, address, dest_memo)

    def gen_fake_tx(self, use_acc=True, **overrides) -> dict:
        """Output fake deposit tx, use_acc decides whether to gen with acc/memo or address, kwargs override tx keys"""
        tx = dict(
            txid=fake_txid(), coin=self.provides[0],
            tx_timestamp=fake.past_datetime(start_date="-30d", tzinfo=None),
            amount=fake_amt()
        )
        if use_acc:
            tx = {**tx, **dict(from_account=fake_user(), to_account=fake_user(), memo=self.fake_memo())}
        else:
            tx = {**tx, 'address': fake_addr()}
        return {**tx, **overrides}

    def add_fake_txs(self, count, use_acc=True):
        for _ in range(count):
            self.fake_txs.append(self.gen_fake_tx(use_acc=use_acc))

    def load(self, tx_count=100):
        self.tx_count = tx_count
        if self.fake_all:
            if len(self.fake_txs) < tx_count:
                self.add_fake_txs(tx_count - len(self.fake_txs))
            if len(self.fake_txs) > tx_count:
                self.fake_txs = self.fake_txs[:tx_count]

        self.loaded = True


class MockManager(BaseManager):
    """
    This is a mock Manager class, used for testing code which uses Coin Handlers.

    If you don't modify any of the static attributes, methods use fake.pybool to randomly raise exceptions
    or return False to test error handling.

    For precise testing, set ``validate_addresses`` to True, ``random_balances`` to False, and use the static methods
    :py:meth:`.add_valid_address` and :py:meth:`.set_balance` to set up a fake coin network.

    """
    provides = ['MOCKTESTCOIN', 'FAKEDESTCOIN']

    fake_balances = {}
    """Dict mapping addresses to Decimal balances"""

    valid_addresses = []
    """List of addresses which should always be accepted"""

    random_balances = True
    """If this is true, `balance()` will return a random number for addresses not listed in `fake_balances`"""

    validate_addresses = False
    """If this is true, methods will always check existence in fake_balances/valid_addresses"""

    @staticmethod
    def reset():
        """Reset static attributes to default"""
        MockManager.valid_addresses = []
        MockManager.fake_balances = {}
        MockManager.random_balances = True
        MockManager.validate_addresses = False
        MockManager.provides = ['MOCKTESTCOIN', 'FAKEDESTCOIN']

    def address_valid(self, address) -> bool:
        """
        Returns True if address in valid_addresses, and False if validate_addresses enabled and not in list.
        If validate_addresses is false, this will return a random true/false if the address isn't in the list
        """
        if self.validate_addresses or address in self.valid_addresses:
            return address in self.valid_addresses
        return fake.pybool()

    def get_deposit(self) -> tuple:
        """Randomly return either a deposit account, or deposit address"""
        if fake.pybool():
            return 'account', fake_user()
        return 'address', fake_addr()

    @staticmethod
    def set_balance(address, balance: Decimal):
        """Set balance for a fake address, and add to valid addresses"""
        MockManager.fake_balances[address] = balance
        MockManager.add_valid_address(address)

    @staticmethod
    def add_valid_address(address):
        """Add a valid to/from address"""
        if address not in MockManager.valid_addresses:
            MockManager.valid_addresses.append(address)

    def balance(self, address: str = None, memo: str = None, memo_case: bool = False) -> Decimal:
        """
        Returns fake balance for an address.
        If validate_addresses is disabled, will return a random number for addresses not in fake_balances
        """
        if address in self.fake_balances:
            return self.fake_balances[address]
        if self.random_balances and not self.validate_addresses:
            return fake_amt()
        raise exceptions.AccountNotFound('Address {} does not exist in self.fake_balances'.format(address))

    def send(self, amount, address, from_address=None, memo=None) -> dict:
        amount = Decimal(amount)
        fee = fake_amt(0, amount / 2)
        # If validate_addresses is true, verify the address from the static list
        if not self.address_valid(address):
            raise exceptions.AccountNotFound('(random/fake) Dest addr {} is not valid'.format(address))

        bal = self.balance(from_address) if from_address is not None else fake_amt()
        from_address = fake_user() if from_address is None else from_address
        if bal < amount:
            raise exceptions.NotEnoughBalance('Tried sending {} from {} but addr only has {}'
                                              .format(amount, from_address, bal))
        return {
            'txid': fake_txid(),
            'coin': self.symbol,
            'amount': amount - fee,
            'fee': fee,
            'from': from_address,
            'send_type': 'send'
        }
