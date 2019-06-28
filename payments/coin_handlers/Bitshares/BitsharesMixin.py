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
#import logging
#from typing import Dict, Any, List

from django.conf import settings

from payments.models import CryptoKeyPair
from steemengine.helpers import decrypt_str

from bitshares import BitShares
from bitshares.account import Account
from bitshares.asset import Asset
from bitshares.blockchain import Blockchain

from graphenecommon.exceptions import AccountDoesNotExistsException
from graphenecommon.exceptions import AssetDoesNotExistsException

from payments.coin_handlers.base.exceptions import AuthorityMissing
#from payments.models import Coin
#from steemengine.helpers import empty

#log = logging.getLogger(__name__)


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
            self._bitshares = BitShares(settings.BITSHARES_RPC_NODE, bundle=True)
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
