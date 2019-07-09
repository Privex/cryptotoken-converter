from typing import Any, Dict

from payments.coin_handlers.EOS import EOSLoader


class AppicsLoader(EOSLoader):
    setting_defaults = {**EOSLoader.setting_defaults, 'auto_refund': True} # type: Dict[str, Any]
