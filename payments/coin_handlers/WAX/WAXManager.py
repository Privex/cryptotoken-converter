from payments.coin_handlers.EOS import EOSManager
from payments.coin_handlers.WAX.WAXMixin import WAXMixin


class WAXManager(EOSManager, WAXMixin):
    """
    This is a stub class which simply glues :class:`.WAXMixin` onto :class:`.EOSManager`

    Once the mixin is applied, it adjusts the chain settings and overrides any required methods,
    then the standard EOSManager code should just work.
    """

