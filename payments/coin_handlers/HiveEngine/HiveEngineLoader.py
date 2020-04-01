from payments.coin_handlers.HiveEngine.HiveEngineMixin import HiveEngineMixin
from payments.coin_handlers.SteemEngine import SteemEngineLoader


class HiveEngineLoader(SteemEngineLoader, HiveEngineMixin):
    """
    This is a stub class which simply glues :class:`.HiveEngineMixin` onto :class:`.SteemEngineLoader`

    Once the mixin is applied, it adjusts the chain settings and overrides any required methods,
    then the standard SteemEngineLoader code should just work.
    """

    def __init__(self, symbols):
        self._eng_rpc = None
        self._eng_rpcs = {}
        self.tx_count = 1000
        self.loaded = False
        super(HiveEngineLoader, self).__init__(symbols=symbols)

