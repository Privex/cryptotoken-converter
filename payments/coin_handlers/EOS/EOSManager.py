import logging
from datetime import timedelta, datetime
from decimal import Decimal, getcontext, ROUND_DOWN
from typing import Union, Tuple

import pytz
from requests import HTTPError

from payments.coin_handlers import BaseManager
from payments.coin_handlers.EOS.EOSMixin import EOSMixin
from payments.coin_handlers.base import TokenNotFound, CoinHandlerException, AccountNotFound, AuthorityMissing, \
    NotEnoughBalance
from payments.models import CryptoKeyPair, Coin
from steemengine.helpers import empty, decrypt_str

getcontext().rounding = ROUND_DOWN

log = logging.getLogger(__name__)


class EOSManager(BaseManager, EOSMixin):

    can_issue = True

    def address_valid(self, *addresses: str) -> bool:
        """
        Check if one or more account usernames exist on the EOS network.

        Example:

        >>> if not self.address_valid('someguy12333', 'steemenginex'):
        ...     print('The EOS account "someguy12333" and/or "steemenginex" does not exist. ')

        :param str addresses: One or more EOS usernames to verify the existence of
        :return bool account_exists: True if all of the given accounts in `addresses` exist on the EOS network.
        :return bool account_exists: False if at least one account in `addresses` does not exist on EOS.
        """
        for address in addresses:
            try:
                acc = self.eos.get_account(address)
                if 'account_name' not in acc:
                    log.warning(f'"account_name" not in data returned by eos.get_account("{address}")...')
                    return False
            except HTTPError as e:
                log.info(f'HTTPError while verifying EOS account "{address}" - this is probably normal: {str(e)}')
                return False
        return True

    def address_valid_ex(self, *addresses: str):
        """
        Check if one or more account usernames exist on the EOS network. Throws an exception if any do not exist.

        A slightly different version of :py:meth:`.address_valid` which raises AccountNotFound with the
        username that failed the test, instead of simply returning True / False.

        :param str addresses: One or more EOS usernames to verify the existence of
        :raises AccountNotFound: When one of the accounts in `addresses` does not exist.
        """
        for address in addresses:
            if not self.address_valid(address):
                raise AccountNotFound(f'The EOS account "{address}" does not exist...')
        return True

    def get_deposit(self) -> tuple:
        return 'account', self.coin.our_account

    def balance(self, address: str = None, memo: str = None, memo_case: bool = False) -> Decimal:
        if not address:
            address = self.coin.our_account

        if not empty(memo):
            raise NotImplemented('Filtering by memos not implemented yet for EOSManager!')
        sym = self.symbol

        contract = self.get_contract(sym)

        bal = self.eos.get_currency_balance(address, code=contract, symbol=sym)
        if len(bal) < 1:
            raise TokenNotFound(f'Balance list for EOS symbol {sym} with contract {contract} was empty...')

        amt, curr = bal[0].split()
        amt = Decimal(amt)
        if curr.upper() != sym:
            raise CoinHandlerException(f'Expected balance currency of {sym} but got {curr} - aborting')

        return amt

    def send(self, amount, address, from_address=None, memo=None) -> dict:
        """
        Send a given ``amount`` of EOS (or a token on EOS) from ``from_address`` to ``address`` with the memo ``memo``.

        Only ``amount`` and ``address`` are mandatory.

        :param Decimal amount:      Amount of coins/tokens to send, as a Decimal()
        :param str address:         Destination EOS account to send the coins/tokens to
        :param str memo:            Memo to send coins/tokens with (default: "")
        :param str from_address:    EOS Account to send from (default: uses Coin.our_account)
        :raises AuthorityMissing:   Cannot send because we don't have authority to (missing key etc.)
        :raises AccountNotFound:    The requested account doesn't exist
        :raises NotEnoughBalance:   Sending account/address does not have enough balance to send
        :return dict:  Result Information

        Format::

          dict {
            txid:str       - Transaction ID - None if not known,
            coin:str       - Symbol that was sent,
            amount:Decimal - The amount that was sent (after fees),
            fee:Decimal    - TX Fee that was taken from the amount (static Decimal(0) for EOS)
            from:str       - The account the coins were sent from.
            send_type:str  - Statically set to "send"
          }

        """
        # Fallback to the coin's `our_account` if `from_address` is not specified
        from_address = self.coin.our_account if not from_address else from_address

        # Some basic sanity checks, e.g. do the from/to account exist? validate/cast the sending amount
        self.address_valid_ex(from_address, address)
        memo = "" if empty(memo) else memo
        amount = self.validate_amount(amount=amount, from_account=from_address)

        # Grab the coin's symbol and find it's contract account
        sym, contract = self.symbol, self.get_contract(self.symbol)

        # Craft the transaction arguments for the transfer operation, then broadcast it and get the result
        tx_args = {"from": from_address, "to": address, "quantity": f"{amount:.4f} {sym}", "memo": memo}
        tfr = self.build_tx("transfer", contract, from_address, tx_args)

        # Some of the important data, e.g. how much was actually sent, is buried in the processed>action_traces
        tx_output = tfr['processed']['action_traces'][0]['act']['data']
        tx_amt_final = Decimal(tx_output['quantity'].split()[0])

        return {
            'txid': tfr['transaction_id'],
            'coin': self.orig_symbol,
            'amount': tx_amt_final,
            'fee': Decimal(0),
            'from': from_address,
            'send_type': 'send'
        }

    def build_tx(self, tx_type, contract, sender, tx_args: dict, key_types=None, broadcast: bool = True) -> dict:
        """
        Crafts an EOS transaction using the various arguments, signs it using the stored private key for `sender`,
        then broadcasts it (if `broadcast` is True) and returns the result.

        Example:

            >>> args = {"from": "someguy12333", "to": "steemenginex", "quantity": "1.000 EOS", "memo": ""}
            >>> res = self.build_tx('transfer', 'eosio.token', 'someguy12333', args)
            >>> print(res['transaction_id'])
            dc9ece0dfb8da0b92068e23bdc22c971e0bc713d31ffc1b7552a861197b0d23e

        :param str tx_type:    The type of transaction, e.g. "transfer" or "issue"
        :param str contract:   The contract username to execute against, e.g. 'eosio.token'
        :param str sender:     The account name that will be signing the transaction, will auto lookup it's private key
        :param dict tx_args:   A dictionary of transaction arguments to add to the payload data
        :param list key_types: (optional) Which types of key can be used for this TX? e.g. ['owner', 'active']
        :param bool broadcast: (default: True) If true, broadcasts the TX after signing. Otherwise returns just
                               the signed TX and does not broadcast it to the network.
        :return dict tfr:      The results of the transaction. Includes information about the broadcast if it was sent.
        """
        key_types = ['active'] if key_types is None else key_types
        # Find and decrypt the active private key for the sending account
        key_type, priv_key = self.get_privkey(sender, key_types=key_types)
        payload = {
            "account": contract,
            "name": tx_type,
            "authorization": [{
                "actor": sender,
                "permission": key_type
            }]
        }
        tx_bin = self.eos.abi_json_to_bin(payload['account'], payload['name'], tx_args)
        payload['data'] = tx_bin['binargs']
        trx = dict(actions=[payload])
        trx['expiration'] = str((datetime.utcnow() + timedelta(seconds=60)).replace(tzinfo=pytz.UTC))
        # Sign and broadcast the transaction we've just built
        tfr = self.eos.push_transaction(trx, priv_key, broadcast=broadcast)
        return tfr

    @staticmethod
    def get_privkey(from_account: str, key_types: list = None) -> Tuple[str, str]:
        """
        Find the EOS :py:class:`models.CryptoKeyPair` in the database for a given account `from_account` ,
        decrypt the private key, then returns a tuple containing (key_type:str, priv_key:str,)

        If no matching key pair could be found, will raise an AuthorityMissing exception.

        Example:

            >>> key_type, priv_key = EOSManager.get_privkey('steemenginex', key_types=['active'])
            >>> print(key_type)
            active
            >>> print(priv_key)  # The below private key was randomly generated for this pydoc block, is isn't a real key.
            5KK4oSvg9n5NxiAK9CXRd7zhbARpx8oxh15miPTXW8htGbYQPKD


        :param str from_account: The EOS account to find a private key for
        :param list key_types:   (optional) A list() of key types to search for. Default: ['active', 'owner']

        :raises AuthorityMissing:  No key pair could be found for the given `from_account`
        :raises EncryptKeyMissing: CTC admin did not set ENCRYPT_KEY in their `.env`, or it is invalid
        :raises EncryptionError:   Something went wrong while decrypting the private key (maybe ENCRYPT_KEY is invalid)

        :return tuple k:           A tuple containing the key type (active/owner etc.) and the private key.
        """

        key_types = ['active', 'owner'] if key_types is None else key_types

        kp = CryptoKeyPair.objects.filter(network='eos', account=from_account, key_type__in=key_types)
        if len(kp) < 1:
            raise AuthorityMissing(f'No private key found for EOS account {from_account} matching types: {key_types}')

        # Grab the first key pair we've found, and decrypt the private key into plain text
        priv_key = decrypt_str(kp[0].private_key)

        return kp[0].key_type, priv_key

    def validate_amount(self, amount: Union[Decimal, float, str], from_account: str = None) -> Decimal:
        """
        Validates a user specified EOS token amount by:

         - if amount is a float, we round it down to a 4 DP string
         - we then pass the amount to Decimal so we can perform more precise calculations
         - checks that the amount is at least 0.0001 (minimum amount of EOS that can be sent)
         - if `from_account` is specified, will raise NotEnoughBalance if we don't have enough balance to cover the TX.

        Example:

            >>> amount = self.validate_amount(1.23)
            >>> amount
            Decimal('1.23')

        :param Decimal amount:    The amount of EOS (or token) to be sent, ideally as Decimal (but works with float/str)
        :param str from_account:  (optional) If specified, check that `from_account` has enough balance for this TX.

        :raises ArithmeticError:  When the amount is lower than the lowest amount allowed by the token's precision
        :raises NotEnoughBalance: The account `from_account` does not have enough balance to send this amount.
        :raises TokenNotFound:    `from_account` does not have a listed balance of `self.symbol`

        :return Decimal amount:   The `amount` after sanitization, converted to a Decimal
        """
        symbol = self.symbol

        # If we get passed a float for some reason, make sure we trim it to the token's precision before
        # converting it to a Decimal.
        if type(amount) == float:
            amount = '{0:.4f}'.format(amount)

        amount = Decimal(amount)
        if amount < Decimal('0.0001'):
            raise ArithmeticError(f'Amount {amount} is lower than minimum of 0.0001 EOS, cannot send.')

        if from_account is not None:
            our_bal = self.balance(from_account)
            if amount > our_bal:
                raise NotEnoughBalance(f'Account {from_account} has {our_bal} {symbol} but needs {amount} to send...')

        return amount

    def issue(self, amount: Decimal, address: str, memo: str = None):
        acc = self.coin.our_account

        # Some basic sanity checks, e.g. do the from/to account exist? validate/cast the sending amount
        self.address_valid_ex(acc, address)
        memo = "" if empty(memo) else memo
        # Note: since we're issuing, no from_account kwarg to avoid NotEnoughBalance exceptions
        amount = self.validate_amount(amount=amount)

        # Grab the coin's symbol and find it's contract account
        sym, contract = self.symbol, self.get_contract(self.symbol)

        # Craft the transaction arguments for the issue operation, then broadcast it and get the result
        tx_args = {"to": address, "quantity": f"{amount:.4f} {sym}", "memo": memo}
        tfr = self.build_tx("issue", contract, acc, tx_args)

        # Some of the important data, e.g. how much was actually sent, is buried in the processed>action_traces
        tx_output = tfr['processed']['action_traces'][0]['act']['data']
        tx_amt_final = Decimal(tx_output['quantity'].split()[0])

        return {
            'txid': tfr['transaction_id'],
            'coin': sym,
            'amount': tx_amt_final,
            'fee': Decimal(0),
            'from': acc,
            'send_type': 'issue'
        }

    def send_or_issue(self, amount, address, memo=None) -> dict:
        try:
            log.debug(f'Attempting to send {amount} {self.symbol} to {address} ...')
            return self.send(amount=amount, address=address, memo=memo)
        except NotEnoughBalance:
            acc = self.coin.our_account
            log.debug(f'Not enough balance. Issuing {amount} {self.symbol} to our account {acc} ...')

            # Issue the coins to our own account, and then send them. This prevents problems caused when issuing
            # directly to third parties.
            self.issue(amount=amount, address=acc, memo=f"Issuing to self before transfer to {address}")

            log.debug(f'Sending newly issued coins: {amount} {self.symbol} to {address} ...')
            tx = self.send(amount=amount, address=address, memo=memo, from_address=acc)
            # So the calling function knows we had to issue these coins, we change the send_type back to 'issue'
            tx['send_type'] = 'issue'
            return tx



