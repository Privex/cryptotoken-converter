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
from decimal import Decimal
from typing import Tuple

from django.conf import settings
from django.core.mail import mail_admins
from django.core.management import BaseCommand
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from payments.coin_handlers import get_manager
from payments.coin_handlers.base.exceptions import NotEnoughBalance, AccountNotFound
from payments.management import CronLoggerMixin
from payments.models import Deposit, Coin, CoinPair, Conversion, AddressAccountMap
from steemengine.helpers import empty

log = logging.getLogger(__name__)


class ConvertError(BaseException):
    """
    Raised when something strange, but predicted has happened. Generally caused either by a bug, or admin mistakes.
    Deposit should set to err, and save exception msg.
    """
    pass


class ConvertInvalid(BaseException):
    """
    Raised when deposit has missing/invalid information needed to route it to a destination coin/address.
    Generally user's fault. Deposit should set to inv, and save exception msg
    """
    pass


class ConvertCore:
    """
    Various conversion logic is extracted to this class filled with static methods, so it can be used elsewhere
    and easily tested in unit tests.
    """

    @staticmethod
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
            a_map = AddressAccountMap.objects.filter(deposit_coin=d.coin, deposit_address=d.address)
            a_map = a_map.filter(deposit_memo=memo) if not empty(memo) else a_map
            a_map = a_map.first()
            if a_map is None:
                raise ConvertInvalid("Deposit address {} has no known coin destination mapped to it.".format(d.address))

            pair = CoinPair.objects.get(from_coin=d.coin, to_coin=a_map.destination_coin)
            address = a_map.destination_address
            dest_memo = a_map.destination_memo
            return address, pair, dest_memo

        # If there's no address, and no memo, we have no idea what to do with this deposit
        raise ConvertInvalid('No deposit address nor memo - unable to route this deposit anywhere...')

    @staticmethod
    def convert(deposit: Deposit, pair: CoinPair, address: str, dest_memo: str = None):
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

        send_amount, ex_fee = ConvertCore.amount_converted(deposit.amount, pair.exchange_rate, settings.EX_FEE)

        log.info('Attempting to send %f %s to address/account %s', send_amount, dest_coin, address)
        try:
            if not mgr.health_test():
                log.warning("Coin %s health test has reported that it's down. Will try again later...", tcoin)
                deposit.last_convert_attempt = timezone.now()
                deposit.save()
                return None
            if tcoin.can_issue:
                s = mgr.send_or_issue(amount=send_amount, address=address, memo=dest_memo)
            else:
                s = mgr.send(amount=send_amount, address=address, memo=dest_memo)
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
                ConvertCore.notify_low_bal(
                    pair=pair, send_amount=send_amount, balance=mgr.balance(), deposit_addr=mgr.get_deposit()[1]
                )
            except:
                log.exception('Failed to send ADMINS email notifications for low balance of coin %s', dest_coin)
            return None

    @staticmethod
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

    @staticmethod
    def amount_converted(from_amount: Decimal, ex_rate: Decimal, fee_pct: Decimal = 0) -> Tuple[Decimal, Decimal]:
        """
        Handles the math for calculating the amount we should send, using an exchange rate and a percentage fee.

        Example, convert 10 coins using exchange rate 0.5, with 1% exchange fee:

        >>> ConvertCore.amount_converted(Decimal('10'), Decimal('0.5'), Decimal('1'))
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


class Command(CronLoggerMixin, BaseCommand):

    help = 'Processes deposits, and handles coin conversions'

    def __init__(self):
        super(Command, self).__init__()

    def add_arguments(self, parser):
        # Named (optional) arguments
        parser.add_argument(
            '--dry',
            action='store_true',
            help="Dry run (don't actually send any coins, just print what would happen)",
        )

    def detect_deposit(self, deposit: Deposit):
        """
        Validates a Deposit through various sanity checks, detects which coin the Deposit is destined for, as well as
        where to send it to.

        Stores the destination details onto deposit's the convert_xxx fields and updates the state to 'mapped'.

        :param Deposit deposit: A :class:`payments.models.Deposit` object to analyze
        :raises ConvertError: Raised when a serious error occurs that generally isn't the sender's fault.
        :raises ConvertInvalid: Raised when a Deposit fails validation, i.e. the sender ignored our instructions.
        """
        d = deposit
        if d.status != 'new':
            raise ConvertError("Deposit is not in 'new' state during detect_deposit... Something is very wrong!")
        try:
            log.debug('Validating deposit and getting dest details for deposit %s', d)
            # Validate the deposit, and grab the destination coin details
            address, pair, dest_memo = ConvertCore.validate_deposit(d)
            # If no exception was thrown, we change the state to 'mapped' and save the destination details.
            log.debug('Deposit mapped to destination. pair: "%s", addr: "%s", memo: "%s"', pair, address, dest_memo)
            d.status = 'mapped'
            d.convert_to = pair.to_coin
            d.convert_dest_address = address
            d.convert_dest_memo = dest_memo
            d.save()

            return d
        except (CoinPair.DoesNotExist, Coin.DoesNotExist):
            log.warning('Marking "inv" - no such coin pair... deposit: "%s"', d)
            raise ConvertInvalid('Deposit is for non-existent coin pair')

    def convert_deposit(self, deposit: Deposit, dry=False):
        """
        Takes a Deposit in the 'mapped' state (has been through detect_deposit), and attempts to convert it
        to the destination coin.

        :param Deposit deposit: A :class:`payments.models.Deposit` object to convert
        :raises ConvertError: Raised when a serious error occurs that generally isn't the sender's fault.
        :raises ConvertInvalid: Raised when a Deposit fails validation, i.e. the sender ignored our instructions.
        """
        d = deposit

        if d.status != 'mapped':
            raise ConvertError("Deposit is not in 'mapped' state during convert_deposit... Something is very wrong!")
        try:
            if empty(d.convert_to) or empty(d.convert_dest_address):
                raise ConvertError('Deposit "convert_to" or "convert_dest_addr" is empty... Cannot convert!')
            pair = CoinPair.objects.get(from_coin=d.coin, to_coin=d.convert_to)
            log.debug('Converting deposit ID %s from %s to %s, coin pair: %s', d.id, d.coin, d.convert_to, pair)
            # Convert() will send the coins, update the Deposit, and create the Conversion object in the DB,
            # as well as some additional validation such as balance checks.
            if dry:
                log.debug(f"DRT RUN: Would run ConvertCore.convert({d}, {pair}, {d.convert_dest_address}, "
                          f"dest_memo='{d.convert_dest_memo}')")
                return True
            else:
                return ConvertCore.convert(d, pair, d.convert_dest_address, dest_memo=d.convert_dest_memo)

        except (CoinPair.DoesNotExist, Coin.DoesNotExist):
            raise ConvertInvalid('Deposit is for non-existent coin pair')

    def handle(self, *args, **options):
        # Load all "new" deposits, max of 200 in memory at a time to avoid memory leaks.
        new_deposits = Deposit.objects.filter(status='new').iterator(200)
        log.info('Coin converter and deposit validator started')

        # ----------------------------------------------------------------
        # Validate deposits and map them to a destination coin / address
        # ----------------------------------------------------------------
        log.info('Validating deposits that are in state "new"')
        for d in new_deposits:
            try:
                log.debug('Validating and mapping deposit %s', d)
                with transaction.atomic():
                    try:
                        self.detect_deposit(d)
                    except ConvertError as e:
                        # Something went very wrong while processing this deposit. Log the error, store the reason
                        # onto the deposit, and then save it.
                        log.error('ConvertError while validating deposit "%s" !!! Message: %s', d, str(e))
                        d.status = 'err'
                        d.error_reason = str(e)
                        d.save()
                    except ConvertInvalid as e:
                        # This exception usually means the sender didn't read the instructions properly, or simply
                        # that the transaction wasn't intended to be exchanged.
                        log.error('ConvertInvalid (user mistake) while validating deposit "%s" Message: %s', d, str(e))
                        d.status = 'inv'
                        d.error_reason = str(e)
                        d.save()
            except:
                log.exception('UNHANDLED EXCEPTION. Deposit could not be validated/detected... %s', d)
                d.status = 'err'
                d.error_reason = 'Unknown error while validating deposit. An admin must manually check the error logs.'
                d.save()
        log.info('Finished validating new deposits for conversion')

        # ----------------------------------------------------------------
        # Convert any validated deposits into their destination coin
        # ----------------------------------------------------------------
        conv_deposits = Deposit.objects.filter(status='mapped').iterator(200)
        log.info('Converting deposits that are in state "mapped"...')
        for d in conv_deposits:
            try:
                log.debug('Converting deposit %s', d)
                with transaction.atomic():
                    try:
                        self.convert_deposit(d, options['dry'])
                    except ConvertError as e:
                        # Something went very wrong while processing this deposit. Log the error, store the reason
                        # onto the deposit, and then save it.
                        log.error('ConvertError while converting deposit "%s" !!! Message: %s', d, str(e))
                        d.status = 'err'
                        d.error_reason = str(e)
                        d.save()
                    except ConvertInvalid as e:
                        # This exception usually means the sender didn't read the instructions properly, or simply
                        # that the transaction wasn't intended to be exchanged.
                        log.error('ConvertInvalid (user mistake) while converting deposit "%s" Message: %s', d, str(e))
                        d.status = 'inv'
                        d.error_reason = str(e)
                        d.save()
            except:
                log.exception('UNHANDLED EXCEPTION. Conversion error for deposit... %s', d)
                d.status = 'err'
                d.error_reason = 'Unknown error while converting. An admin must manually check the error logs.'
                d.save()
        log.info('Finished converting deposits.')

        log.debug('Resetting any Coins "funds_low" if they have no "mapped" deposits')
        for c in Coin.objects.filter(funds_low=True):
            log.debug(' -> Coin %s currently has low funds', c)
            map_deps = c.deposit_converts.filter(status='mapped').count()
            if map_deps == 0:
                log.debug(' +++ Coin %s has no mapped deposits, resetting funds_low to false', c)
                c.funds_low = False
                c.save()
            else:
                log.debug(' !!! Coin %s still has %d mapped deposits. Ignoring.', c, map_deps)
        log.debug('Finished resetting coins with "funds_low" that have been resolved.')





