from typing import Dict, Any, List
from eospy.cleos import Cleos
from payments.coin_handlers.EOS.EOSMixin import EOSMixin
import logging

from payments.models import Coin

log = logging.getLogger(__name__)


class TelosMixin(EOSMixin):
    
    chain = 'telos'
    chain_type = 'telos'
    chain_coin = 'TLOS'
    
    setting_defaults = dict(
        host='telos.caleos.io', username=None, password=None, endpoint='/', port=443, ssl=True, precision=4,
        telos=True
    )
    
    _telos = None  # type: Cleos

    provides = ['TLOS']  # type: List[str]

    default_contracts = {
        'TLOS': 'eosio.token',
    }  # type: Dict[str, str]

    def __init__(self):
        super().__init__()
        self.current_rpc = None

    @property
    def eos(self) -> Cleos:
        """Returns an instance of Cleos and caches it in the attribute :py:attr:`._telos` after creation"""
        if not self._telos:
            log.debug(f'Creating Cleos instance using Telos API node: {self.url}')
            self.current_rpc = self.url
            self._telos = Cleos(url=self.url)
        return self._telos

    def replace_eos(self, **conn) -> Cleos:
        """
        Destroy the EOS :class:`.Cleos` instance at :py:attr:`._eos` and re-create it with the modified
        connection settings ``conn``

        Also returns the EOS instance for convenience.

        Only need to specify settings you want to override.

        Example::

            >>> eos = self.replace_eos(host='example.com', port=80, ssl=False)
            >>> eos.get_account('someguy123')


        :param conn: Connection settings. Keys: endpoint, ssl, host, port, username, password
        :return Cleos eos: A :class:`.Cleos` instance with the modified connection settings.
        """
        del self._telos
        url = self._make_url(**conn)
        log.debug('Replacing Cleos instance with new Telos API node: %s', url)
        self.current_rpc = url
        self._telos = Cleos(url=url)
    
        return self._telos
