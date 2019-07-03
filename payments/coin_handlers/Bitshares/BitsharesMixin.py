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
from decimal import Decimal
from django.conf import settings
from typing import List

from payments.models import CryptoKeyPair
from steemengine.helpers import decrypt_str

from bitshares import BitShares
from bitshares.account import Account
from bitshares.asset import Asset
from bitshares.blockchain import Blockchain
from bitshares.amount import Amount

from graphenecommon.exceptions import AccountDoesNotExistsException
from graphenecommon.exceptions import AssetDoesNotExistsException
from graphenecommon.exceptions import InvalidWifError
from graphenecommon.exceptions import KeyAlreadyInStoreException

from payments.coin_handlers.base.exceptions import AuthorityMissing

log = logging.getLogger(__name__)


class BitsharesMixin:
    """
    BitsharesMixin - A class that provides shared functionality used by both BitsharesLoader and BitsharesManager.

    Main features::

     - Access the BitShares shared instance via :py:attr:`.bitshares`
     - Access the Blockchain shared instance via :py:attr:`.blockchain`
     - Safely get Bitshares network data (account data, asset data, and block timestamps)

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

    _bitshares = None   # type: BitShares
    """Shared instance of :py:class:`bitshares.BitShares` used across both the loader/manager."""

    _blockchain = None  # type: Blockchain
    """Shared instance of :py:class:`bitshares.blockchain.Blockchain` used across both the loader/manager."""

    @property
    def bitshares(self) -> BitShares:
        """Returns an instance of BitShares and caches it in the attribute _bitshares after creation"""
        if not self._bitshares:
            self._bitshares = BitShares(settings.BITSHARES_RPC_NODE, bundle=True, keys=[])
        return self._bitshares
    
    @property
    def blockchain(self) -> Blockchain:
        """Returns an instance of Blockchain and caches it in the attribute _blockchain after creation"""
        if not self._blockchain:
            self._blockchain = Blockchain(blockchain_instance=self.bitshares)
        return self._blockchain

    def get_account_obj(self, account_name) -> Account:
        """
        If an account exists on Bitshares, will return a :py:class:`bitshares.account.Account` object. Otherwise None.

        :param account_name: Bitshares account to get data for
        :return Account or None
        """
        try:
            account_obj = Account(account_name, blockchain_instance=self.bitshares)
            return account_obj
        except AccountDoesNotExistsException:
            return None

    def get_asset_obj(self, symbol) -> Asset:
        """
        If a token symbol exists on Bitshares, will return a :py:class:`bitshares.asset.Asset` object. Otherwise None.

        :param symbol: Bitshares token to get data for (can be symbol name or id)
        :return Asset or None
        """
        try:
            asset_obj = Asset(symbol, blockchain_instance=self.bitshares)
            return asset_obj
        except AssetDoesNotExistsException:
            return None

    def get_block_timestamp(self, block_number) -> int:
        """
        Given a block number, returns the timestamp of that block. If block number is invalid or an error happens, returns 0.

        :param block_number: block number to get data for
        :return int
        """
        try:
            return self.blockchain.block_timestamp(block_number)
        except:
            return 0

    def get_decimal_from_amount(self, amount_obj: Amount) -> Decimal:
        """Helper function to convert a Bitshares Amount object into a Decimal"""
        raw_amount = Decimal(int(amount_obj))
        balance = raw_amount / (10 ** amount_obj.asset['precision'])
        return balance

    def get_private_key(self, account_name, key_type) -> str:
        """
        Find the Bitshares :py:class:`models.CryptoKeyPair` in the database for a given account `account_name` and
        key type 'key_type' (e.g. 'active' or 'memo'), decrypt the private key, then return the plaintext key.

        If no matching key could be found, will raise an AuthorityMissing exception.

        :param str account_name: The Bitshares account to find a private key for
        :param str key_type:     Key type to search for. Can be 'active', 'memo', or 'owner'

        :raises AuthorityMissing:  No key could be found for the given `account_name`
        :raises EncryptKeyMissing: CTC admin did not set ENCRYPT_KEY in their `.env`, or it is invalid
        :raises EncryptionError:   Something went wrong while decrypting the private key (maybe ENCRYPT_KEY is invalid)

        :return str key:           the plaintext key
        """
        key_types = [key_type]

        kp = CryptoKeyPair.objects.filter(network='bitshares', account=account_name, key_type__in=key_types)
        if len(kp) < 1:
            raise AuthorityMissing(f'No private key found for Bitshares account {account_name} matching type: {key_type}')

        # Grab the first key pair we've found, and decrypt the private key into plain text
        priv_key = decrypt_str(kp[0].private_key)

        return priv_key

    def set_wallet_keys(self, account_name, key_types: List[str]):
        """
        Retrieves a :py:class:`models.CryptoKeyPair` for a given account `account_name` and each key type specified
        in the key_types list (e.g. 'active' or 'memo'). Each private key is then decrypted and added to the
        underlying Bitshares wallet for use in transactions.

        If no matching key could be found, will raise an AuthorityMissing exception.

        :param str account_name: The Bitshares account to set keys for
        :param List key_types:   Key types to search for. Can include 'active', 'memo', or 'owner'

        :raises AuthorityMissing:  A key could be found for the given `account_name`
        :raises EncryptKeyMissing: CTC admin did not set ENCRYPT_KEY in their `.env`, or it is invalid
        :raises EncryptionError:   Something went wrong while decrypting the private key (maybe ENCRYPT_KEY is invalid)
        """
        for key_type in key_types:
            private_key = self.get_private_key(account_name, key_type)
            try:
                self.bitshares.wallet.addPrivateKey(private_key)
            except KeyAlreadyInStoreException:
                log.debug(f'Private key for Bitshares account {account_name} matching type {key_type} already exists in the key store, so not adding it again')
            except InvalidWifError:
                raise AuthorityMissing(f'Invalid key format for Bitshares account {account_name} matching type: {key_type}')
