from typing import Dict, Any, List, Optional
from privex.steemengine import SteemEngineToken

import logging

from django.conf import settings
from payments.coin_handlers.SteemEngine.SteemEngineMixin import SteemEngineMixin

log = logging.getLogger(__name__)

curr_node_index = 0
def mk_heng_rpc() -> SteemEngineToken:
    """
    Get a :class:`.SteemEngineToken` instance using configured node settings

        >>> rpc = mk_heng_rpc()

    :return SteemEngineToken rpc:  An instance of :class:`.SteemEngineToken`
    """
    global curr_node_index

    rpc_node = settings.HE_RPC_NODES[curr_node_index]
    curr_node_index += 1
    if curr_node_index >= len(settings.HE_RPC_NODES):
        curr_node_index = 0
    
    rpc_url = '/contracts'
    history_node = 'accounts.hive-engine.com'
    history_url = 'accountHistory'
    network_account = 'ssc-mainnet-hive'
    network = 'hive'
    
    return SteemEngineToken(
        network_account=network_account,
        network=network,
        history_conf=dict(hostname=history_node, url=history_url),
        hostname=rpc_node,
        url=rpc_url
    )


class HiveEngineMixin(SteemEngineMixin):
    _eng_rpc: Optional[SteemEngineToken]
    _eng_rpcs: Dict[str, SteemEngineToken]
    
    def __init__(self, *args, **kwargs):
        self._eng_rpc = None
        self._eng_rpcs = {}
        super(SteemEngineMixin, self).__init__(*args, **kwargs)
    
    @property
    def eng_rpc(self) -> SteemEngineToken:
        return mk_heng_rpc()
    
    def get_rpc(self, symbol: str) -> SteemEngineToken:
        return mk_heng_rpc()
