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

    num_retries = 0
    while True:
        rpc_node = settings.HE_RPC_NODES[curr_node_index]
        curr_node_index += 1
        if curr_node_index >= len(settings.HE_RPC_NODES):
            curr_node_index = 0

        # strip off the http or https prefix
        use_ssl = False
        port_num = ''
        if rpc_node[:8] == 'https://':
            use_ssl = True
            port_num = 443
            rpc_node = rpc_node[8:]
        elif rpc_node[:7] == 'http://':
            rpc_node = rpc_node[7:]
            node_parts = rpc_node.split(':')
            rpc_node = node_parts[0]
            if len(node_parts) > 1:
                port_num = int(node_parts[1])

        rpc_url = '/contracts'
        if use_ssl and (rpc_node == 'api2.hive-engine.com' or rpc_node == 'api.hive-engine.com'):
            rpc_url = '/rpc/contracts'
        history_node = 'history.hive-engine.com'
        history_url = 'accountHistory'
        network_account = 'ssc-mainnet-hive'
        network = 'hive'

        try:
            token = SteemEngineToken(
                network_account=network_account,
                network=network,
                history_conf=dict(hostname=history_node, url=history_url),
                hostname=rpc_node,
                url=rpc_url,
                port=port_num,
                ssl=use_ssl,
                nodes=settings.HIVE_RPC_NODES
            )
            return token
        except Exception as e:
            num_retries += 1
            log.error('unable to connect to %s (attempt %s)', rpc_node, str(num_retries))
            if num_retries >= 5:
                log.error('giving up')
                raise
            else:
                log.error('will try again')


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
