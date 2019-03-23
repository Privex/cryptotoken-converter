from django import forms
from django.conf import settings
from django.contrib import admin

# Register your models here.
from payments.models import Coin, Deposit, AddressAccountMap, CoinPair, Conversion

"""
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
from payments.coin_handlers import reload_handlers


@admin.register(Coin)
class CoinAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'symbol', 'coin_type', 'enabled', 'our_account', 'can_issue')
    list_filter = ('coin_type',)

    def get_fieldsets(self, request, obj=None):
        # To ensure that the Coin Type dropdown is properly populated, we call reload_handlers() just before
        # the create / update Coin page finishes loading it's data.
        reload_handlers()
        return super(CoinAdmin, self).get_fieldsets(request, obj)


@admin.register(AddressAccountMap)
class AddressAccountMapAdmin(admin.ModelAdmin):
    list_display = ('deposit_coin', 'deposit_address', 'destination_coin', 'destination_address')
    list_filter = ('deposit_coin', 'destination_coin',)
    search_fields = ('deposit_address', 'destination_address',)
    pass


@admin.register(CoinPair)
class CoinPairAdmin(admin.ModelAdmin):
    pass


@admin.register(Conversion)
class ConversionAdmin(admin.ModelAdmin):
    list_display = ('from_coin', 'from_address', 'from_amount', 'to_coin', 'to_address', 'to_amount',
                    'tx_fee', 'ex_fee', 'created_at')
    list_filter = ('from_coin', 'to_coin')
    search_fields = ('id', 'from_address', 'to_address', 'to_memo', 'to_txid')
    ordering = ('created_at',)


@admin.register(Deposit)
class DepositAdmin(admin.ModelAdmin):
    list_display = ('txid', 'status', 'coin', 'amount', 'address', 'from_account', 'to_account', 'tx_timestamp')
    list_filter = ('status', 'coin',)
    search_fields = ('id', 'txid', 'address', 'from_account', 'to_account', 'memo', 'refund_address')
    ordering = ('created_at',)
    pass
