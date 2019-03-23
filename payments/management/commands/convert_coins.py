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

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction
from django.utils import timezone

from payments.coin_handlers import get_manager
from payments.coin_handlers.base.exceptions import NotEnoughBalance, AccountNotFound
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


class Command(BaseCommand):

    help = 'Processes deposits, and handles coin conversions'

    def handle_deposit(self, deposit: Deposit):
        """
        Validates a Deposit through various sanity checks, detects which coin the Deposit is destined for, as well as
        where to send it to, and then passes off to :py:meth:`.convert` to handle the actual sending.

        :param Deposit deposit: A :class:`payments.models.Deposit` object to analyze and convert
        :raises ConvertError: Raised when a serious error occurs that generally isn't the sender's fault.
        :raises ConvertInvalid: Raised when a Deposit fails validation, i.e. the sender ignored our instructions.
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

        # If there's no address, and no memo, we have no idea what to do with this deposit
        memo = d.memo.strip() if d.memo is not None else None
        if empty(memo) and empty(d.address):
            raise ConvertInvalid('No deposit address nor memo - unable to route this deposit anywhere...')

        # If the memo isn't empty ('', None, etc.), then we scan the memo for "SYMBOL   ADDRESS"
        if not empty(memo):
            log.debug('Deposit ID %s has a memo, attempting to detect destination pair', d.id)
            msplit = memo.split()
            if len(msplit) < 2:
                log.warning('Marking "inv" - memo split by spaces has less than 2 items... "%s"', d)
                raise ConvertInvalid('Memo is not valid - splitting by whitespace resulted in <2 items.')
            symbol, address = (msplit[0].upper(), msplit[1],)
            dest_coin = Coin.objects.get(symbol=symbol)
        # Otherwise, we try to lookup the deposit address to figure out what we do with this deposit.
        else:
            assert not empty(d.address)
            a_map = AddressAccountMap.objects.filter(deposit_coin=d.coin, deposit_address=d.address)
            a_map = a_map.filter(deposit_memo=memo) if not empty(memo) else a_map

            if len(a_map) < 1:
                raise ConvertInvalid("Deposit address {} has no known coin destination mapped to it.".format(d.address))

            dest_coin = a_map[0].destination_coin
            symbol = dest_coin.symbol
            address = a_map[0].destination_address
        # Finally, let convert() take over, which will send the coins, update the Deposit, and create the Conversion
        # object in the DB, as well as some additional validation such as balance checks.
        try:
            pair = CoinPair.objects.get(from_coin=d.coin, to_coin=dest_coin)
            return self.convert(deposit=d, pair=pair, address=address)
        except CoinPair.DoesNotExist:
            log.warning('Marking "inv" - no such coin pair %s -> %s ... deposit: "%s"', d.coin_id, symbol, d)
            raise ConvertInvalid('No such coin pair {} -> {}'.format(d.coin_id, symbol))
        except:
            log.exception('Unexpected error while sending the transaction... Deposit: "%s"', d)
            raise ConvertError('Unknown error while sending TX. An admin must manually check the error logs.')

    def convert(self, deposit: Deposit, pair: CoinPair, address: str):
        """
        After a Deposit has passed the validation checks of :py:meth:`.handle_deposit` , this method loads the
        appropriate coin handler, calculates fees, generates a memo, and sends the exchanged coins to
        their destination.

        :param deposit:         The deposit object to be converted
        :param CoinPair pair:   A CoinPair object for getting the exchange rate + destination coin
        :param str address:     The destination crypto address, or account

        :raises ConvertError:   Raised when a serious error occurs that generally isn't the sender's fault.
        :raises ConvertInvalid: Raised when a Deposit fails validation, i.e. the sender ignored our instructions.

        :return Conversion c:   The inserted conversion object after a successful transfer
        :return None None:      Something is wrong with the coin handler, try again later, do not set deposit to error.
        """
        dest_coin = pair.to_coin.symbol.upper()
        src_coin = deposit.coin.symbol.upper()

        mgr = get_manager(dest_coin)

        dest_memo = 'Token Conversion'
        if not empty(deposit.address):
            dest_memo += ' via {} deposit address {}'.format(src_coin, deposit.address)
        if not empty(deposit.from_account):
            dest_memo += ' from {} account {}'.format(src_coin, deposit.from_account)

        # The original conversion amount
        conv_amount = Decimal(deposit.amount) * Decimal(pair.exchange_rate)
        # The exchange fee percentage
        ex_fee_pct = Decimal(str(settings.EX_FEE)) * Decimal('0.01')
        # The actual Decimal amount of fee to be taken off the dest. amount
        ex_fee = conv_amount * ex_fee_pct
        # The amount of `dest_coin` we should actually try to send them
        send_amount = conv_amount - ex_fee

        log.info('Attempting to send %f %s to address/account %s', send_amount, dest_coin, address)
        try:
            if pair.to_coin.can_issue:
                s = mgr.send_or_issue(amount=send_amount, address=address, memo=dest_memo)
            else:
                s = mgr.send(amount=send_amount, address=address, memo=dest_memo)
            log.info('Successfully sent %f %s to address/account %s', send_amount, dest_coin, address)

            deposit.status = 'conv'
            deposit.convert_to = pair.to_coin
            deposit.processed_at = timezone.now()
            deposit.save()

            c = Conversion(
                deposit=deposit,
                from_coin=pair.from_coin,
                to_coin=pair.to_coin,
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
            log.exception('Not enough balance to send these tokens. Will try again later...')
            return None

    def handle(self, *args, **options):
        # Load all "new" deposits, max of 200 in memory at a time to avoid memory leaks.
        new_deposits = Deposit.objects.filter(status='new').iterator(200)
        log.info('Coin converter and deposit validator started')
        for d in new_deposits:
            try:
                log.debug('Scanning deposit %s', d)
                with transaction.atomic():
                    try:
                        self.handle_deposit(d)
                    except ConvertError as e:
                        # Something went very wrong while processing this deposit. Log the error, store the reason
                        # onto the deposit, and then save it.
                        log.error('ConvertError for deposit "%s" !!! Message: %s', d, str(e))
                        d.status = 'err'
                        d.error_reason = str(e)
                        d.save()
                    except ConvertInvalid as e:
                        # This exception usually means the sender didn't read the instructions properly, or simply
                        # that the transaction wasn't intended to be exchanged.
                        log.error('ConvertInvalid (user mistake) for deposit "%s" Message: %s', d, str(e))
                        d.status = 'inv'
                        d.error_reason = str(e)
                        d.save()
            except:
                log.exception('UNHANDLED EXCEPTION. Deposit could not be processed... %s', d)
                d.status = 'err'
                d.error_reason = 'Unhandled exception while processing TX. An admin must manually check the error logs.'
                d.save()
        log.info('Finished validating new deposits for conversion')



