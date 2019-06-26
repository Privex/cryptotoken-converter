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

from bitshares import BitShares
from bitshares.account import Account
from bitshares.asset import Asset

from graphenecommon.exceptions import AccountDoesNotExistsException
from graphenecommon.exceptions import AssetDoesNotExistsException

#from payments.coin_handlers.base.exceptions import TokenNotFound, MissingTokenMetadata
#from payments.models import Coin
#from steemengine.helpers import empty

#log = logging.getLogger(__name__)


class BitsharesMixin:
    """
    BitsharesMixin - A class that provides shared functionality used by both BitsharesLoader and BitsharesManager.

    Main features::

     - Access the BitShares shared instance via :py:attr:`.bitshares`
     - Safely get Bitshares account & asset objects

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

    @property
    def bitshares(self) -> BitShares:
        """Returns an instance of BitShares and caches it in the attribute _bitshares after creation"""
        if not self._bitshares:
            self._bitshares = BitShares(settings.BITSHARES_RPC_NODE, bundle=True)
        return self._bitshares

    def get_account_obj(self, account_name) -> (Account):
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

    def get_asset_obj(self, symbol) -> (Asset):
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

        #try:
        #    contract = self.settings[symbol].get('contract')
        #    if not empty(contract):
        #        return contract
        #except AttributeError:
        #    raise TokenNotFound(f'The coin "{symbol}" was not found in {__name__}.settings')

        #log.debug(f'No contract found in DB settings for "{symbol}", checking if we have a default...')
        #try:
        #    contract = self.default_contracts[symbol]

        #    if empty(contract):
        #        raise MissingTokenMetadata

        #    log.debug(f'Found contract for "{symbol}" in default_contracts, returning "{contract}"')
        #    return contract
        #except (AttributeError, MissingTokenMetadata):
        #    log.error(f'Failed to find a contract for "{symbol}" in Coin objects nor default_contracts...')
        #    raise MissingTokenMetadata(f"Couldn't find '{symbol}' contract in DB coin settings or default_contracts.")
