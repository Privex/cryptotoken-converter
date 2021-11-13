from payments.coin_handlers.EOS import EOSManager
from payments.coin_handlers.CyberWay.CWMixin import CWMixin


class CWManager(EOSManager, CWMixin):
    """
    This is a stub class which simply glues :class:`.CWMixin` onto :class:`.EOSManager`

    Once the mixin is applied, it adjusts the chain settings and overrides any required methods,
    then the standard EOSManager code should just work.
    """

