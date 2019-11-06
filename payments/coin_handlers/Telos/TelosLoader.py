from typing import List

from payments.coin_handlers.EOS import EOSLoader
from payments.coin_handlers.Telos.TelosMixin import TelosMixin
import logging

log = logging.getLogger(__name__)


class TelosLoader(EOSLoader, TelosMixin):
    """
    This is a stub class which simply glues :class:`.TelosMixin` onto :class:`.EOSLoader`
    
    Once the mixin is applied, it adjusts the chain settings and overrides any required methods,
    then the standard EOSLoader code should just work.
    """

    def __init__(self, symbols):
        self.tx_count = 1000
        self.loaded = False
        self.current_rpc = None
        super(TelosLoader, self).__init__(symbols=symbols)

