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
from typing import Dict, Any, List, Optional

from django.conf import settings
from privex.steemengine import SteemEngineToken

from payments.coin_handlers.base import SettingsMixin


log = logging.getLogger(__name__)


class SteemEngineMixin(SettingsMixin):
    _eng_rpc: Optional[SteemEngineToken]
    
    def __init__(self, *args, **kwargs):
        self._eng_rpc = None
        super(SteemEngineMixin, self).__init__(*args, **kwargs)
    
    @property
    def eng_rpc(self) -> SteemEngineToken:
        if not self._eng_rpc:
            self._eng_rpc = SteemEngineToken(
                network_account=settings.SENG_NETWORK_ACCOUNT,
                history_conf=dict(hostname=settings.SENG_HISTORY_NODE, url=settings.SENG_HISTORY_URL),
                hostname=settings.SENG_RPC_NODE,
                url=settings.SENG_RPC_URL
            )
        return self._eng_rpc
