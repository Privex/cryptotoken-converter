"""
Various conversion logic is extracted to this module filled with methods, so it can be used elsewhere
and easily tested in unit tests.
"""
from decimal import Decimal
from typing import Tuple, Optional

from django.conf import settings
from django.core.mail import mail_admins
from django.template.loader import render_to_string
from django.utils import timezone

from payments.coin_handlers import get_manager
from payments.coin_handlers.base import AccountNotFound, NotEnoughBalance
from payments.exceptions import ConvertError, ConvertInvalid, NotRefunding
from payments.models import Deposit, CoinPair, Conversion, Coin, AddressAccountMap
from steemengine.helpers import empty
import logging

log = logging.getLogger(__name__)


def validate_deposit(deposit: Deposit) -> Tuple[str, CoinPair, str]:
    """
    Validates and identifies the destination CoinPair and account/address of a given Deposit.

    Returns a tuple containing the destination address/account, the CoinPair for conversion, and
    the destination memo (if it has one, otherwise it will be blank or None).

    :param Deposit deposit: The Deposit object to validate and return destination details for

    :raises ConvertError: Raised when a serious error occurs that generally isn't the sender's fault.
    :raises ConvertInvalid: Raised when a Deposit fails validation, i.e. the sender ignored our instructions.
    :raises Coin.DoesNotExist: Destination coin doesn't exist
    :raises CoinPair.DoesNotExist: Detected conversion pair does not exist

    :return tuple: (dest_address: str, coin_pair: CoinPair, dest_memo: str)
    """
    d = deposit
    # There's a OneToOne relation between a deposit and a conversion
    # If we try to insert a conversion when a deposit already has one, it'll throw an error...
    if Conversion.objects.filter(deposit=d).count() > 0:
        log.warning('Error: A conversion already exists for deposit "%s". Aborting conversion.', d)
        raise ConvertError(
            'A Conversion object already exists for this deposit. An admin should investigate the logs, '
            'make sure no coins were sent in the previous conversion attempt, then remove the related '
            'conversion from the DB.'
        )
    # If you're not supposed to be able to convert from this coin, then we can't process it.
    if d.coin.pairs_from.count() < 1:
        raise ConvertInvalid('No coin pairs with from_coin = {}'.format(d.coin.symbol))

    memo = d.memo.strip() if d.memo is not None else None

    # If a deposit has a memo, but not a crypto address, then we parse the memo
    if not empty(memo) and empty(d.address):
        log.debug('Deposit ID %s has a memo, attempting to detect destination pair', d.id)
        m = memo.split()
        if len(m) < 2:
            log.warning('Marking "inv" - memo split by spaces has less than 2 items... "%s"', d)
            raise ConvertInvalid('Memo is not valid - splitting by whitespace resulted in <2 items.')

        symbol, address = (m[0].upper(), m[1])  # First item is dest symbol, second is address/account
        dest_memo = ' '.join(m[2:]) if len(m) >= 3 else ''  # 3+ items means there's a destination memo at the end
        pair = CoinPair.objects.get(from_coin=d.coin, to_coin=Coin.objects.get(symbol=symbol))
        return address, pair, dest_memo
    if not empty(d.address):
        _a_map = AddressAccountMap.objects.filter(deposit_coin=d.coin, deposit_address=d.address)
        _a_map = _a_map.filter(deposit_memo=memo) if not empty(memo) else _a_map
        a_map = _a_map.first()    # type: AddressAccountMap
        
        if a_map is None:
            raise ConvertInvalid("Deposit address {} has no known coin destination mapped to it.".format(d.address))

        pair = CoinPair.objects.get(from_coin=d.coin, to_coin=a_map.destination_coin)
        address = a_map.destination_address
        dest_memo = a_map.destination_memo
        return address, pair, dest_memo

    # If there's no address, and no memo, we have no idea what to do with this deposit
    raise ConvertInvalid('No deposit address nor memo - unable to route this deposit anywhere...')


def refund_sender(deposit: Deposit, reason: str = None, return_to: str = None) -> Tuple[Deposit, dict]:
    """
    Returns a Deposit back to it's original sender, sets the Deposit status to 'refund', and stores the refund
    details onto the Deposit.

    :param Deposit    deposit: The :class:`models.Deposit` object to refund
    :param str         reason: If specified, will use this instead of ``deposit.error_reason`` for the memo.
    :param str      return_to: If specified, will return to this addr/acc instead of deposit.address/from_account
    :return tuple refund_data:  Returns a tuple containing the updated Deposit object, and the tx data from send().
    """
    d = deposit
    reason = d.error_reason if empty(reason) else reason
    if empty(reason):
        reason = f'Returned to sender due to unknown error processing deposit amount {d.amount} ' \
            f'with TXID {d.txid}...'

    log.info(f'Refunding Deposit {d} due to reason: {reason}')
    if d.status == 'refund':
        raise NotRefunding(f'The deposit {d} is already refunded!')
    if d.status == 'conv':
        raise NotRefunding(f'The deposit {d} is already successfully converted!')

    c = d.coin
    sym = c.symbol.upper()
    mgr = get_manager(sym)
    # Return destination priority: ``return_to`` arg, sender address, sender account
    dest = d.address if empty(return_to) else return_to
    dest = d.from_account if empty(dest) else dest

    if empty(dest):
        raise AttributeError('refund_sender could not find any non-empty return address/account...')

    metadata = dict(deposit=deposit, action="refund")
    log.info(f'(REFUND) Sending {d.amount} {sym} to addr/acc {dest} with memo "{reason}"')

    txdata = mgr.send_or_issue(amount=d.amount, address=dest, memo=reason, trigger_data=metadata)
    log.debug(f'(REFUND) Storing refund details for deposit {d}')

    d.status = 'refund'
    d.refund_address = dest
    d.refund_amount = txdata['amount']
    d.refund_coin = sym
    d.refund_memo = reason
    d.refund_txid = txdata['txid']
    d.refunded_at = timezone.now()

    d.save()
    log.info(f'(REFUND) SUCCESS. Saved details for {d}')

    return d, txdata


def convert(deposit: Deposit, pair: CoinPair, address: str, dest_memo: str = None) -> Optional[Conversion]:
    """
    After a Deposit has passed the validation checks of :py:meth:`.detect_deposit` , this method loads the
    appropriate coin handler, calculates fees, generates a memo, and sends the exchanged coins to
    their destination.

    :param Deposit deposit: The deposit object to be converted
    :param CoinPair pair:   A CoinPair object for getting the exchange rate + destination coin
    :param str address:     The destination crypto address, or account
    :param str dest_memo:   Optionally specify a memo for the coins to be sent with

    :raises ConvertError:   Raised when a serious error occurs that generally isn't the sender's fault.
    :raises ConvertInvalid: Raised when a Deposit fails validation, i.e. the sender ignored our instructions.

    :return Conversion c:   The inserted conversion object after a successful transfer
    :return None None:      Something is wrong with the coin handler, try again later, do not set deposit to error.
    """
    # f/tcoin are the actual Coin objects
    fcoin = pair.from_coin
    tcoin = pair.to_coin
    # dest/src are string symbols
    dest_coin = tcoin.symbol.upper()
    src_coin = fcoin.symbol.upper()

    mgr = get_manager(dest_coin)

    if empty(dest_memo):
        dest_memo = 'Token Conversion'
        if not empty(deposit.address):
            dest_memo += ' via {} deposit address {}'.format(src_coin, deposit.address)
        if not empty(deposit.from_account):
            dest_memo += ' from {} account {}'.format(src_coin, deposit.from_account)

    send_amount, ex_fee = amount_converted(deposit.amount, pair.exchange_rate, settings.EX_FEE)

    log.info('Attempting to send %f %s to address/account %s', send_amount, dest_coin, address)
    try:
        if not mgr.health_test():
            log.warning("Coin %s health test has reported that it's down. Will try again later...", tcoin)
            deposit.last_convert_attempt = timezone.now()
            deposit.save()
            return None
        metadata = dict(
            deposit=deposit,
            pair=pair,
            action="convert"
        )
        if tcoin.can_issue:
            s = mgr.send_or_issue(amount=send_amount, address=address, memo=dest_memo, trigger_data=metadata)
        else:
            s = mgr.send(amount=send_amount, address=address, memo=dest_memo, trigger_data=metadata)
        log.info('Successfully sent %f %s to address/account %s', send_amount, dest_coin, address)

        deposit.status = 'conv'
        deposit.convert_to = tcoin
        deposit.processed_at = timezone.now()
        deposit.save()

        c = Conversion(
            deposit=deposit,
            from_coin=fcoin,
            to_coin=tcoin,
            from_address=s.get('from', None),
            to_address=address,
            to_memo=dest_memo,
            to_amount=s.get('amount', deposit.amount),
            to_txid=s.get('txid', None),
            tx_fee=s.get('fee', Decimal(0)),
            ex_fee=ex_fee
        )
        c.save()
        log.info('Successfully stored Conversion. Conversion ID is %s', c.id)
        return c
    except AccountNotFound:
        raise ConvertInvalid('Destination address "{}" appears to be invalid. Exc: AccountNotFound'.format(address))
    except NotEnoughBalance:
        log.error('Not enough balance to send %f %s. Will try again later...', send_amount, dest_coin)
        try:
            deposit.last_convert_attempt = timezone.now()
            deposit.save()
            notify_low_bal(
                pair=pair, send_amount=send_amount, balance=mgr.balance(), deposit_addr=mgr.get_deposit()[1]
            )
        except:
            log.exception('Failed to send ADMINS email notifications for low balance of coin %s', dest_coin)
        return None


def notify_low_bal(pair: CoinPair, send_amount: Decimal, balance: Decimal, deposit_addr: str):
    """
    Send a "low hot wallet balance" notification email to the admins, with details of what caused the low
    balance issue. Automatically updates the low balance fields on the ``pair.to_coin`` after sending.

    Will only send the email if ``pair.to_coin.should_notify_low`` is True.

    :param pair: The coin pair object that triggered the low balance notification
    :param send_amount: The amount that we tried to send
    :param balance: The current balance of pair.to_coin
    :param deposit_addr: An address/account for admins to deposit for re-filling the hot wallet
    """
    tcoin = pair.to_coin
    log.debug('Checking if we should notify admins of low balance')
    if tcoin.should_notify_low:
        log.info('Sending emails to admins to let them know of %s low balance', tcoin.symbol)

        deposits_waiting = Deposit.objects.filter(convert_to=tcoin, status='mapped').count()

        tpl_data = dict(
            pair=pair, balance=balance, deposits=deposits_waiting,
            amount=send_amount, site_url=settings.SITE_URL, deposit_addr=deposit_addr
        )
        html_body = render_to_string('emails/admin_lowbalance.html', tpl_data)
        txt_body = render_to_string('emails/admin_lowbalance.txt', tpl_data)
        subject = '{} hot wallet is low'.format(tcoin)
        mail_admins(subject, txt_body, html_message=html_body)
        log.info('Email sent successfully')
        log.debug('Setting funds_low to True, and updating last_notified')
        tcoin.funds_low = True
        tcoin.last_notified = timezone.now()
        tcoin.save()


def amount_converted(from_amount: Decimal, ex_rate: Decimal, fee_pct: Decimal = 0) -> Tuple[Decimal, Decimal]:
    """
    Handles the math for calculating the amount we should send, using an exchange rate and a percentage fee.

    Example, convert 10 coins using exchange rate 0.5, with 1% exchange fee:

    >>> amount_converted(Decimal('10'), Decimal('0.5'), Decimal('1'))
    ( Decimal('4.99'), Decimal('0.01'), )

    Meaning, you should send 4.99, and we've taken 0.01 in fees from that amount.

    :param from_amount: The base amount to convert by the exchange rate
    :param ex_rate:     The exchange rate to use for conversion
    :param fee_pct:     Exchange fee as a flat percentage number, e.g. 1 means 1% fee
    :return tuple:      send_amount:Decimal, ex_fee:Decimal
    """
    conv_amount = from_amount * ex_rate     # The original conversion amount
    ex_fee_pct = fee_pct * Decimal('0.01')  # The exchange fee percentage
    ex_fee = conv_amount * ex_fee_pct       # The actual Decimal amount of fee to be taken off the dest. amount
    send_amount = conv_amount - ex_fee      # The amount of `dest_coin` we should actually try to send them
    return send_amount, ex_fee
