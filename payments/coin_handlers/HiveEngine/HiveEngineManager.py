from payments.coin_handlers.HiveEngine.HiveEngineMixin import HiveEngineMixin
from payments.coin_handlers.SteemEngine import SteemEngineManager


class HiveEngineManager(SteemEngineManager, HiveEngineMixin):
    """
    This is a stub class which simply glues :class:`.HiveEngineMixin` onto :class:`.SteemEngineManager`

    Once the mixin is applied, it adjusts the chain settings and overrides any required methods,
    then the standard SteemEngineManager code should just work.
    """

    def __init__(self, symbol: str):
        self._eng_rpc = None
        self._eng_rpcs = {}
        super(HiveEngineManager, self).__init__(symbol)
