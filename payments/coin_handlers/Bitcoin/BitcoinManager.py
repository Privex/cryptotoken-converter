"""
**Copyright**::

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
from typing import List, Dict, Tuple

from decimal import Decimal, getcontext, ROUND_DOWN
from privex.jsonrpc import BitcoinRPC

from payments.coin_handlers.Bitcoin.BitcoinMixin import BitcoinMixin
from payments.coin_handlers.base import exceptions
from payments.coin_handlers.base import BaseManager

getcontext().rounding = ROUND_DOWN

log = logging.getLogger(__name__)


class BitcoinManager(BaseManager, BitcoinMixin):
    """
    BitcoinManager - Despite the name, handles sending, balance, and deposit addresses for any coin that has a
    bitcoind-compatible JsonRPC API

    Known to work with: bitcoind, litecoind, dogecoind

    **Copyright**::

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

    For the **required Django settings**, please see the module docstring in :py:mod:`coin_handlers.Bitcoin`

    """

    provides: List[str] = []
    """Dynamically populated by Bitcoin.__init__"""

    rpcs: Dict[str, BitcoinRPC] = {}
    """
    For each coin connection specified in `settings.COIND_RPC`, we map it's symbol to an instantiated instance
    of BitcoinRPC - stored as a static property, ensuring we don't have to constantly re-create them.
    """

    def health(self) -> Tuple[str, tuple, tuple]:
        """
        Return health data for the passed symbol.

        Health data will include: Symbol, Status, Current Block, Node Version, Wallet Balance,
        and number of p2p connections (all as strings)

        :return tuple health_data: (manager_name:str, headings:list/tuple, health_data:list/tuple,)
        """
        headers = ('Symbol', 'Status', 'Current Block', 'Version',
                   'Wallet Balance', 'P2P Connections',)
        class_name = type(self).__name__
        status = 'Unknown Error'
        current_block = version = balance = connections = ''
        # If the coin is based on a newer protocol, e.g. bitcoin core + litecoin, use the new methods
        try:
            b = self.rpc.getblockchaininfo()
            current_block = '{:,}'.format(b['blocks'])
            if 'headers' in b:
                current_block += ' (Headers: {:,})'.format(b['headers'])
            n = self.rpc.getnetworkinfo()
            version = '{} ({})'.format(n['version'], n['subversion'])
            connections = str(n['connections'])
            balance = '{0:,.8f}'.format(self.rpc.getbalance())
            status = 'Online'
        except:
            # If we get an error, try using the old method
            try:
                b = self.rpc.getinfo()
                current_block = '{:,}'.format(int(b['blocks']))
                version = b['version']
                balance = '{0:,.8f}'.format(b['balance'])
                connections = str(b['connections'])
                status = 'Online'
            except:
                log.exception('Exception during %s health check for symbol %s', class_name, self.symbol)
                # If this also errors, it's definitely offline
                status = 'Offline'

        if status == 'Online':
            status = '<b style="color: green">{}</b>'.format(status)
        else:
            status = '<b style="color: red">{}</b>'.format(status)

        data = (self.symbol, status, current_block, version, balance, connections,)
        return class_name, headers, data

    def __init__(self, symbol: str):
        super().__init__(symbol.upper())
        # Get all RPCs
        self.rpcs = self._get_rpcs()
        # Manager's only deal with one coin, so unwrap the generated dicts
        self.rpc = self.rpcs[symbol]           # type: BitcoinRPC

    def health_test(self) -> bool:
        """
        Check if the coin daemon is up or not, by requesting basic information such as current block and version.

        :return bool: True if the coin daemon appears to be working, False if it's not
        """
        try:
            _, _, health_data = self.health()
            if 'Online' in health_data[1]:
                return True
            return False
        except:
            return False

    @property
    def settings(self) -> Dict[str, dict]:
        """To ensure we always get fresh settings from the DB after a reload, self.settings gets _prep_settings()"""
        return self._prep_settings()

    @property
    def setting(self) -> Dict[str, any]:
        """Retrieve only our symbol from self.settings for convenience"""
        return self.settings[self.symbol]

    def balance(self, address: str = None, memo: str = None, memo_case: bool = False) -> Decimal:
        """
        Get the total amount received by an address, or the balance of the wallet if address not specified.

        :param address:    Crypto address to get balance for, if None, returns whole wallet balance
        :param memo:       NOT USED BY THIS MANAGER
        :param memo_case:  NOT USED BY THIS MANAGER
        :return: Decimal(balance)
        """

        return self.rpc.getreceivedbyaddress(address=address, confirmations=self.setting['confirms_needed'])

    def address_valid(self, address) -> bool:
        """If `address` is determined to be valid by the coind RPC, will return True. Otherwise False."""

        try:
            v = self.rpc.validateaddress(address)
            if v['isvalid'] in [True, 'true', 1]:
                return True
            return False
        except:
            log.exception('Something went wrong while running %s.address_valid. Returning NOT VALID.', type(self))
            return False

    def get_deposit(self) -> tuple:
        """
        Returns a deposit address for this symbol
        :return tuple: A tuple containing ('address', crypto_address)
        """

        return 'address', self.rpc.getnewaddress()

    def send(self, amount, address, memo=None, from_address=None) -> dict:
        """
        Send the amount `amount` of `self.symbol` to a given address.

        Example - send 0.1 LTC to LVXXmgcVYBZAuiJM3V99uG48o3yG89h2Ph

            >>> s = BitcoinManager('LTC')
            >>> s.send(address='LVXXmgcVYBZAuiJM3V99uG48o3yG89h2Ph', amount=Decimal('0.1'))

        :param Decimal amount:      Amount of coins to send, as a Decimal()
        :param address:             Address to send the coins to
        :param from_address:        NOT USED BY THIS MANAGER
        :param memo:                NOT USED BY THIS MANAGER
        :raises AccountNotFound:    The destination `address` isn't valid
        :raises NotEnoughBalance:   The wallet does not have enough balance to send this amount.
        :return dict: Result Information

        Format::

          {
              txid:str - Transaction ID - None if not known,
              coin:str - Symbol that was sent,
              amount:Decimal - The amount that was sent (after fees),
              fee:Decimal    - TX Fee that was taken from the amount,
              from:str       - The account/address the coins were sent from,
              send_type:str       - Should be statically set to "send"
          }

        """

        # To avoid issues with floats, we convert the amount to a string with 8DP
        if type(amount) == float:
            amount = '{0:.8f}'.format(amount)
        amount = Decimal(amount)

        # First let's make sure the destination address is valid
        try:
            v = self.rpc.validateaddress(address)
            if v['isvalid'] not in [True, 'true', 1]:
                raise Exception()
        except:
            raise exceptions.AccountNotFound('Invalid {} address {}'.format(self.symbol, address))
        # Now let's try to send the coins
        try:
            txid = self.rpc.sendtoaddress(address, str(amount), "", "", True,
                                          force_float=not self.setting['string_amt'])
            # Fallback values if getting TX data below fails.
            fee = Decimal(0)
            actual_amount = amount
            sender = None
            # To find out the fee, the amount after fee, and the sending addresses, we need to look up the TXID
            # This is wrapped in another try/catch to ensure badly formed TXs don't trigger the outer try/catch
            # and cause the caller to think the coins weren't sent.
            try:
                txdata = self.rpc.gettransaction(txid)
                fee = txdata['fee']
                if type(fee) == float:
                    fee = '{0:.8f}'.format(fee)
                fee = Decimal(fee)
                if fee < 0:
                    fee = -fee
                txam = txdata['amount']
                if type(txam) == float:
                    txam = '{0:.8f}'.format(txam)
                txam = Decimal(txam)
                actual_amount = txam if txam > 0 else -txam
                sender = ','.join([a['address'] for a in txdata['details'] if a['category'] == 'send'])

            except:
                log.exception('Something went wrong loading data for %s TXID %s', self.symbol, txid)
                log.error('The fee, amount, and "from" details may be inaccurate')

            return {
                'txid': txid,
                'coin': self.symbol,
                'amount': actual_amount,
                'fee': Decimal(fee),
                'from': sender,
                'send_type': 'send'
            }
        except Exception as e:
            log.exception("Something went wrong sending %f %s to %s", amount, self.symbol, address)
            raise e
