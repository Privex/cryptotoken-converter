"""

This file contains Models, classes which define database tables, and how they relate to each other.

Models are used for both querying the database, as well as inserting new rows and updating existing ones.

Models may also contain **properties** and **functions** to help make them easier to use.

Note: The ``coin_type`` choices tuple, ``COIN_TYPES`` is located in settings.py, and may be dynamically
altered by Coin Handlers. It does not enforce an enum on columns using it for ``choices`` , it's simply used for a
dropdown list in the admin panel.

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
import json
import logging
from django.db import models
from django.conf import settings

# Create your models here.

log = logging.getLogger(__name__)

# If for some reason, you're dealing with token/crypto symbols longer than this, or tokens/coins that need more than
# 20 DP and 40 total digits including the decimals, then you can change both here to quickly update
# it across all models.
#
# If you change it, you'll need to run `./manage.py makemigrations` and `./manage.py migrate`
#
SYMBOL_LEN = 20
# Coin/token amounts are stored in the database with a maximum decimal place precision of the below integer number.
MAX_STORED_DP = 20
# Maximum digits possible for coin/token amounts, e.g. 123.456 counts as 6 total digits (3 before dot, 3 after)
MAX_STORED_DIGITS = 40


class Coin(models.Model):
    """
    The operator of the service should define all coins and tokens they would like to support using the Django Admin.
    The symbol is used as the primary key, so it must be unique. It will automatically be made uppercase.
    """
    symbol = models.CharField('Coin Symbol (e.g. BTC)', max_length=SYMBOL_LEN, primary_key=True)
    display_name = models.CharField('Display Name (e.g. Bitcoin)', max_length=100)
    coin_type = models.CharField(max_length=20)
    # If a coin is disabled (enabled=False), transactions will not be loaded for this coin,
    # nor will any conversions involving this coin work.
    enabled = models.BooleanField(default=True)
    # The "our_account" field is required for certain coins/tokens, so that we know which account name, or address
    # to use when sending, receiving, or issuing tokens/coins
    our_account = models.CharField('If required, our Account/Address to send/receive with', max_length=255,
                                   blank=True, null=True)
    can_issue = models.BooleanField('Can we issue (create) this coin/token?', default=False)

    # To allow for easy adjustment of coin handler settings, we add columns for common connection details
    setting_host = models.CharField('Handler Setting - Hostname', blank=True, null=True, max_length=255)
    setting_port = models.CharField('Handler Setting - Port', blank=True, null=True, max_length=255)
    setting_user = models.CharField('Handler Setting - Username', blank=True, null=True, max_length=255)
    setting_pass = models.CharField('Handler Setting - Password', blank=True, null=True, max_length=255)
    # If a handler requires additional settings, they can be specified in this custom field, usually as JSON.
    setting_json = models.TextField('Handler Setting - Custom JSON', default='{}', max_length=1000)

    @property
    def settings(self) -> dict:
        """
        Small helper property for quickly accessing the setting_xxxx fields, while also decoding the custom json
        field into a dictionary/list

        :return: dict(host:str, port:str, user:str, password:str, json:dict/list)
        """
        try:
            j = json.loads(self.setting_json)
        except:
            log.warning("Couldn't decode JSON for coin %s, falling back to {}", str(self))
            j = {}

        return dict(
            host=self.setting_host,
            port=self.setting_port,
            user=self.setting_user,
            password=self.setting_pass,
            json=j
        )

    @property
    def pairs(self):
        return self.pairs_from | self.pairs_to

    def __init__(self, *args, **kwargs):
        super(Coin, self).__init__(*args, **kwargs)
        # To allow dynamic additions to settings.COIN_TYPES, we have to set it from the constructor
        # not from the model field itself.
        self._meta.get_field('coin_type').choices = settings.COIN_TYPES

    def save(self, *args, **kwargs):
        """To avoid inconsistency, the symbol is automatically made uppercase"""
        self.symbol = self.symbol.upper()
        super(Coin, self).save(*args, **kwargs)
        # After a coin is updated in the DB, we should reload any coin_handlers to detect compatible loaders.
        # We need to use in-line loading to prevent recursive loading from the coin handlers causing issues.
        from payments.coin_handlers import reload_handlers
        reload_handlers()

    def __str__(self):
        return '{} ({})'.format(self.display_name, self.symbol)


class CoinPair(models.Model):
    """
    A coin pair defines an allowed conversion direction between two coins
    For example LTC (Litecoin) -> LTCP (Pegged Litecoin)
    """
    from_coin = models.ForeignKey(Coin, on_delete=models.CASCADE, related_name='pairs_from')
    to_coin = models.ForeignKey(Coin, on_delete=models.CASCADE, related_name='pairs_to')
    exchange_rate = models.DecimalField('Exchange Rate (Amount of `to` per `from`)', max_digits=MAX_STORED_DIGITS,
                                        decimal_places=MAX_STORED_DP, default=1)

    @property
    def from_coin_symbol(self):
        return self.from_coin.symbol

    @property
    def to_coin_symbol(self):
        return self.to_coin.symbol

    def __str__(self):
        return '{c_from} -> {c_to} ({ex:.4f} {c_to} per {c_from})'.format(
            c_from=self.from_coin.symbol, c_to=self.to_coin.symbol, ex=self.exchange_rate
        )

    class Meta:
        unique_together = (('from_coin', 'to_coin'),)


class AddressAccountMap(models.Model):
    """
    This database model maps normal Bitcoin-like addresses to a destination token, and their token account/address.

    This is because deposits of coins such as Bitcoin/Litecoin do not contain any form of "memo", so they must be
    manually mapped onto a destination.

    This model may be used for handling deposits for both memo-based (Bitshares-like) and address-based (Bitcoin-like)
    deposits, as there is both a memo and address (or account) field for deposits + destination coin
    """
    # The deposit details of the coin/token that will be converted into the `destination_coin`
    # The `deposit_address` can be a crypto address, or an account name, depending on what the coin requires.
    # If you use an account name, you should specify `deposit_memo` for detecting the transaction
    deposit_coin = models.ForeignKey(Coin, db_index=True, on_delete=models.DO_NOTHING, related_name='deposit_maps')
    deposit_address = models.CharField('Deposit Address / Account', max_length=100)
    deposit_memo = models.CharField('Deposit Memo (if required)', max_length=255,
                                    blank=True, null=True, default=None)
    # The `destination_*` fields define the crypto/token that the deposited crypto/token will be converted into.
    destination_coin = models.ForeignKey(Coin, db_index=True, on_delete=models.DO_NOTHING, related_name='dest_maps')
    destination_address = models.CharField('Destination Address / Account', max_length=100)
    destination_memo = models.CharField('Destination Memo (if required)', max_length=255,
                                        blank=True, null=True, default=None)

    @property
    def conversions(self):
        return Conversion.objects.filter(to_address=self.destination_address)

    def __str__(self):
        return '{} {} -> {} {}'.format(self.deposit_coin, self.deposit_address,
                                       self.destination_coin, self.destination_address)

    # A set of deposit details (coin, address and memo) should only be able to exist ONCE in the table, otherwise
    # we might not know which destination to send it to.
    class Meta:
        unique_together = (('deposit_coin', 'deposit_address', 'deposit_memo'),)


class Deposit(models.Model):
    """
    A log of incoming token/crypto deposits, which will later be converted into crypto.

    The primary key of a `Deposit` is the auto-generated `id` field - an auto incrementing integer.

    There is a composite unique constraint on (txid, coin, vout), ensuring duplicate transactions do not get stored.

    Deposits start out in state ``new`` , as they are processed by the conversion system they progress into either:

        'err'       - An error occurred while converting / importing
                      During the import/conversion there was a serious error that could not be recovered from
                      This should be investigated by a developer.

        'inv'       - Invalid source/destination, user did not follow instructions correctly
                      The coins were sent to a non-registered address, or a memo we don't know how to process.
                      An admin should attempt to refund these coins to the sender.

        'refund'    - The coins sent in this Deppsit were refunded
                      Info about the refund should be in the refund_* fields

        'conv'      - Successfully Converted
                      The deposited coins were successfully converted into their destination coin, and there
                      should be a related :class:`models.Conversion` containing the conversion details.

    """
    STATUSES = (
        ('err', 'Error Processing Transaction'),
        ('inv', 'Transaction is invalid'),
        ('refund', 'Coins were returned to user'),
        ('new', 'New (awaiting processing)'),
        ('conv', 'Successfully converted')
    )

    txid = models.CharField('Transaction ID', max_length=100, db_index=True)
    """The transaction ID where the coins were received."""

    coin = models.ForeignKey(Coin, db_index=True, on_delete=models.DO_NOTHING, related_name='deposits')
    """The symbol of the cryptocurrency or token that was deposited, in uppercase. e.g. LTC, LTCP, BTCP, STEEMP"""

    vout = models.IntegerField('Output Number (if multiple deposits in one tx)', default=0, blank=True)
    """If a transaction contains multiple deposits, for example, a Bitcoin transaction that contains several
       outputs (vout's) for our addresses, then each vout must have an consistent output number, i.e. one that will
       not change each time the blockchain transaction is compared against the database."""

    status = models.CharField(max_length=20, choices=STATUSES, default='new')
    """The current status of this deposit, see ``STATUSES`` """

    error_reason = models.TextField(max_length=255, blank=True, null=True)

    tx_timestamp = models.DateTimeField('Transaction Date/Time', blank=True, null=True)
    """The date/time the transaction actually occurred on the chain"""

    address = models.CharField(max_length=100, blank=True, null=True)
    """If the deposit is from a classic Bitcoin-like cryptocurrency with addresses, then you should enter the
       address where the coins were deposited into, in this field."""

    # If the deposit is from a Bitshares-like cryptocurrency (Steem, GOLOS, EOS), then you should enter the
    # sending account into `from_account`, our receiving account into `to_account`, and memo into `memo`
    # Tokens received on Steem Engine should use these fields.
    from_account = models.CharField(max_length=100, blank=True, null=True)
    """If account-based coin, contains the name of the account that sent the coins"""

    to_account = models.CharField(max_length=100, blank=True, null=True)
    """If account-based coin, contains the name of the account that the coins were deposited into"""

    memo = models.CharField(max_length=255, blank=True, null=True)
    """If the coin supports memos, and they're required to identify a deposit, use this field."""

    amount = models.DecimalField(max_digits=MAX_STORED_DIGITS, decimal_places=MAX_STORED_DP)

    convert_to = models.ForeignKey(Coin, blank=True, null=True, default=None, on_delete=models.DO_NOTHING,
                                   related_name='deposit_converts')
    """The destination coin. Set after a deposit has been analyzed, and we know what coin it will be converted to"""

    # If something goes wrong with this transaction, and it was refunded, then we store
    # all of the refund details, for future reference.
    refund_address = models.CharField('Refunded to this account/address', max_length=500, blank=True, null=True)
    refund_memo = models.CharField(max_length=500, blank=True, null=True)
    refund_coin = models.CharField('The coin (symbol) that was refunded to them', max_length=10, blank=True, null=True)
    refund_amount = models.DecimalField(max_digits=MAX_STORED_DIGITS, decimal_places=MAX_STORED_DP, default=0)
    refund_txid = models.CharField(max_length=500, blank=True, null=True)
    refunded_at = models.DateTimeField(blank=True, null=True)

    # The date/time that this database entry was added/updated
    created_at = models.DateTimeField('Creation Time', auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField('Last Update', auto_now=True)
    # When the token was converted into the paired crypto currency (if at all)
    processed_at = models.DateTimeField('Processed At', blank=True, null=True)

    @property
    def coin_symbol(self):
        return self.coin.symbol

    def __str__(self):
        return 'ID: {}, Coin: {}, TXID: {}'.format(self.id, self.coin, self.txid)

    class Meta:
        """
        A transaction ID should only exist once within a particular coin. It may exist multiple times if each output
        has a unique `vout` number.
        """
        unique_together = (('txid', 'coin', 'vout'),)


class Conversion(models.Model):
    """
    Once a :class:`models.Deposit` has been scanned, assuming it has a valid address or account/memo, the
    destination cryptocurrency/token will be sent to the user.

    Successful conversion attempts are logged here, allowing for reference of where the coins came from, where
    they went, and what fees were taken.
    """
    deposit = models.OneToOneField(Deposit, related_name='conversion', on_delete=models.DO_NOTHING)

    from_coin = models.ForeignKey(Coin, verbose_name="From Coin", on_delete=models.DO_NOTHING,
                                  related_name='conversions_from')
    """The coin that we were sent"""

    from_address = models.CharField('From Address / Account (if known)', max_length=255, blank=True, null=True)

    to_coin = models.ForeignKey(Coin, verbose_name="Converted Into (Symbol)", on_delete=models.DO_NOTHING,
                                related_name='conversions_to')
    """The destination token/crypto this token will be converted to"""

    to_address = models.CharField('Destination Address / Account', max_length=255)
    """Where was it sent to?"""

    to_memo = models.CharField('Destination Memo (if applicable)', max_length=255, blank=True, null=True)
    to_amount = models.DecimalField('Amount Sent', max_digits=MAX_STORED_DIGITS, decimal_places=MAX_STORED_DP)
    """The amount of ``to_coin`` that was sent, stored as a high precision Decimal"""

    # Sometimes it might not be possible to get the TXID, so we allow it to be None for sanity.
    to_txid = models.CharField('Transaction ID (Destination coin)', max_length=255, null=True, blank=True)
    tx_fee = models.DecimalField('Blockchain Fee', max_digits=MAX_STORED_DIGITS,
                                 decimal_places=MAX_STORED_DP, default=0)

    # The amount of `from_coin` that was retained by the exchange as a fee
    ex_fee = models.DecimalField('Exchange Fee', max_digits=MAX_STORED_DIGITS, decimal_places=MAX_STORED_DP, default=0)

    # The date/time that this database entry was added/updated
    created_at = models.DateTimeField('Creation Time', auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField('Last Update', auto_now=True)

    @property
    def from_coin_symbol(self):
        return self.from_coin.symbol

    @property
    def to_coin_symbol(self):
        return self.to_coin.symbol

    @property
    def from_amount(self):
        return self.deposit.amount




