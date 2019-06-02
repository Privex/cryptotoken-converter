from decimal import Decimal

from payments.coin_handlers import BaseManager


class EOSManager(BaseManager):
    def address_valid(self, address) -> bool:
        pass

    def get_deposit(self) -> tuple:
        pass

    def balance(self, address: str = None, memo: str = None, memo_case: bool = False) -> Decimal:
        pass

    def send(self, amount, address, from_address=None, memo=None) -> dict:
        pass
