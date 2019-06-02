import logging
from datetime import timedelta, datetime
from decimal import Decimal, getcontext, ROUND_DOWN

import pytz
from requests import HTTPError

from payments.coin_handlers import BaseManager
from payments.coin_handlers.EOS.EOSMixin import EOSMixin
from payments.coin_handlers.base import TokenNotFound, CoinHandlerException, AccountNotFound, AuthorityMissing, \
    NotEnoughBalance
from payments.models import CryptoKeyPair
from steemengine.helpers import empty, decrypt_str

getcontext().rounding = ROUND_DOWN

log = logging.getLogger(__name__)


class EOSManager(BaseManager, EOSMixin):
    def address_valid(self, address) -> bool:
        try:
            acc = self.eos.get_account(address)
            if 'account_name' not in acc:
                log.warning(f'"account_name" not in data returned by eos.get_account("{address}")...')
                return False
            return True
        except HTTPError as e:
            log.info(f'HTTPError while verifying EOS account "{address}" - this is probably normal: {str(e)}')
            return False

    def get_deposit(self) -> tuple:
        return 'account', self.coin.our_account

    def balance(self, address: str = None, memo: str = None, memo_case: bool = False) -> Decimal:
        if not address:
            address = self.coin.our_account

        if not empty(memo):
            raise NotImplemented('Filtering by memos not implemented yet for EOSManager!')
        sym = self.symbol.upper()

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
        if not from_address:
            from_address = self.coin.our_account

        if not self.address_valid(from_address):
            raise AccountNotFound(f'The from account "{from_address}" does not exist...')

        if not self.address_valid(address):
            raise AccountNotFound(f'The to account "{address}" does not exist...')

        memo = "" if empty(memo) else memo
        sym = self.symbol.upper()
        contract = self.get_contract(sym)

        kp = CryptoKeyPair.objects.filter(network='eos', account=from_address, key_type__in=['active', 'owner'])

        if len(kp) < 1:
            raise AuthorityMissing(f'No active/owner private key found for EOS account {from_address}')

        # Grab the first key pair we've found, and decrypt the private key into plain text
        priv_key = decrypt_str(kp[0].private_key)

        # If we get passed a float for some reason, make sure we trim it to the token's precision before
        # converting it to a Decimal.
        if type(amount) == float:
            amount = '{0:.4f}'.format(amount)

        amount = Decimal(amount)
        if amount < Decimal('0.0001'):
            raise ArithmeticError(f'Amount {amount} is lower than minimum of 0.0001 EOS, cannot send.')

        our_bal = self.balance(from_address)

        if amount > our_bal:
            raise NotEnoughBalance(f'Account {from_address} has {our_bal} {sym} but needs {amount} to send...')

        fmt_amt = f"{amount:.4f} {sym}"

        tx_args = {
            "from": from_address,
            "to": address,
            "quantity": fmt_amt,
            "memo": memo
        }

        payload = {
            "account": contract,
            "name": "transfer",
            "authorization": [{
                "actor": from_address,
                "permission": kp[0].key_type
            }]
        }
        tx_bin = self.eos.abi_json_to_bin(payload['account'], payload['name'], tx_args)
        payload['data'] = tx_bin['binargs']
        trx = dict(actions=[payload])
        trx['expiration'] = str((datetime.utcnow() + timedelta(seconds=60)).replace(tzinfo=pytz.UTC))

        tfr = self.eos.push_transaction(trx, priv_key, broadcast=True)

        tx_output = tfr['processed']['action_traces'][0]['act']['data']
        tx_amt_final = Decimal(tx_output['quantity'].split()[0])

        return {
            'txid': tfr['transaction_id'],
            'coin': sym,
            'amount': tx_amt_final,
            'fee': Decimal(0),
            'from': from_address,
            'send_type': 'send'
        }

