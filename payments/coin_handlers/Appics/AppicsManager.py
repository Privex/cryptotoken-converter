import logging
from decimal import Decimal
from typing import Dict, Any

from privex.helpers import empty

from payments.coin_handlers.EOS.EOSManager import EOSManager
from payments.models import Deposit

log = logging.getLogger(__name__)


class AppicsManager(EOSManager):
    setting_defaults = {**EOSManager.setting_defaults, 'auto_refund': True}  # type: Dict[str, Any]

    def send(self, amount, address, from_address=None, memo=None, trigger_data: dict = None):
        """
        Send a given ``amount`` of APX from ``from_address`` to ``address`` with the memo ``memo``.

        Only ``amount`` and ``address`` are mandatory.

        :param Decimal amount:      Amount of coins/tokens to send, as a Decimal()
        :param str address:         Destination EOS account to send the coins/tokens to
        :param str memo:            Memo to send coins/tokens with (default: "")
        :param str from_address:    EOS Account to send from (default: uses Coin.our_account)
        :param dict trigger_data:   Metadata containing the key "deposit", with details of the Deposit triggering this.
        :raises AuthorityMissing:   Cannot send because we don't have authority to (missing key etc.)
        :raises AccountNotFound:    The requested account doesn't exist
        :raises NotEnoughBalance:   Sending account/address does not have enough balance to send
        :raises AttributeError:     The key 'deposit' wasn't found in the ``trigger_data``
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
        trig_act = trigger_data.get('action')

        # If `send` is being triggered due to a refund, we have to do a standard EOS issue.
        if trig_act == 'refund':
            return super(AppicsManager, self).issue(
                amount=amount, address=address, memo=memo, trigger_data=trigger_data
            )
        else:
            deposit = trigger_data['deposit']  # type: Deposit
            steem_tx = str(deposit.txid)

        # Fallback to the coin's `our_account` if `from_address` is not specified
        from_address = self.coin.our_account if not from_address else from_address

        # Some basic sanity checks, e.g. do the from/to account exist? validate/cast the sending amount
        self.address_valid_ex(from_address, address)
        memo = "" if empty(memo) else memo
        amount = self.validate_amount(amount=amount)

        # Grab the coin's symbol and find it's contract account
        sym, contract = self.symbol, self.get_contract(self.symbol)
        log.debug(f'Contact for {sym} is {contract}')

        # Craft the transaction arguments for the transfer operation, then broadcast it and get the result
        tx_args = {"to": address, "quantity": f"{amount:.4f} {sym}", "memo": memo, "steem_tx": steem_tx}
        log.debug(f'Built mint transaction: {tx_args} and signing with {from_address}')

        tfr = self.build_tx("mint", contract, from_address, tx_args, key_types=['active'])

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

    def issue(self, amount: Decimal, address: str, memo: str = None, trigger_data: dict = None):
        return self.send(
            amount=amount, address=address, memo=memo, trigger_data=trigger_data
        )
