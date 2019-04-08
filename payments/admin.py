import logging

from django.contrib import admin, messages

# Register your models here.
from django.contrib.admin import AdminSite
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import User, Group
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed
from django.shortcuts import render, redirect
from django.urls import path
from django.views.decorators.cache import cache_page
from django.views.generic import TemplateView

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
from payments.coin_handlers import reload_handlers, has_manager, get_manager

log = logging.getLogger(__name__)


class CustomAdmin(AdminSite):
    """
    To allow for custom admin views, we override AdminSite, so we can add custom URLs, among other things.
    """
    def get_urls(self):
        _urls = super(CustomAdmin, self).get_urls()
        urls = [
            path('coin_health/', CoinHealthView.as_view(), name='coin_health'),
            path('_clear_cache/', clear_cache, name='clear_cache'),
        ]
        return _urls + urls


ctadmin = CustomAdmin()


class CoinAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'symbol', 'coin_type', 'enabled', 'our_account', 'can_issue')
    list_filter = ('coin_type',)

    def get_fieldsets(self, request, obj=None):
        # To ensure that the Coin Type dropdown is properly populated, we call reload_handlers() just before
        # the create / update Coin page finishes loading it's data.
        reload_handlers()
        return super(CoinAdmin, self).get_fieldsets(request, obj)


class AddressAccountMapAdmin(admin.ModelAdmin):
    list_display = ('deposit_coin', 'deposit_address', 'destination_coin', 'destination_address')
    list_filter = ('deposit_coin', 'destination_coin',)
    search_fields = ('deposit_address', 'destination_address',)
    pass


class CoinPairAdmin(admin.ModelAdmin):
    pass


class ConversionAdmin(admin.ModelAdmin):
    list_display = ('from_coin', 'from_address', 'from_amount', 'to_coin', 'to_address', 'to_amount',
                    'tx_fee', 'ex_fee', 'created_at')
    list_filter = ('from_coin', 'to_coin')
    search_fields = ('id', 'from_address', 'to_address', 'to_memo', 'to_txid')
    ordering = ('-created_at',)


class DepositAdmin(admin.ModelAdmin):
    list_display = ('txid', 'status', 'coin', 'amount', 'address', 'from_account', 'to_account', 'tx_timestamp')
    list_filter = ('status', 'coin',)
    search_fields = ('id', 'txid', 'address', 'from_account', 'to_account', 'memo', 'refund_address')
    ordering = ('-created_at',)
    pass


# Because we've overridden the admin site, the default user/group admin doesn't register properly.
# So we manually register them to their admin views.
ctadmin.register(User, UserAdmin)
ctadmin.register(Group, GroupAdmin)

ctadmin.register(Coin, CoinAdmin)
ctadmin.register(CoinPair, CoinPairAdmin)
ctadmin.register(Conversion, ConversionAdmin)
ctadmin.register(Deposit, DepositAdmin)
ctadmin.register(AddressAccountMap, AddressAccountMapAdmin)


class CoinHealthView(TemplateView):
    """
    Admin view for viewing health/status information of all coins in the system.

    Loads the coin handler manager for each coin, and uses the health() function to grab status info for the coin.

    Uses caching API to avoid constant RPC queries, and displays results as a standard admin view.
    """
    template_name = 'admin/coin_health.html'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.coin_fails = []

    def get_fails(self):
        """View function to be called from template, for getting list of coin handler errors"""
        return self.coin_fails

    def handler_dic(self):
        """View function to be called from template. Loads and queries coin handlers for health, with caching."""
        hdic = {}           # A dictionary of {handler_name: {headings:list, results:list[tuple/list]}
        reload_handlers()
        for coin in Coin.objects.all():
            try:
                if not has_manager(coin.symbol):
                    self.coin_fails.append('Cannot check {} (no manager registered in coin handlers)'.format(coin))
                    continue
                # Try to load coin health data from cache.
                # If it's not found, query the manager and cache it for up to 30 seconds to avoid constant RPC hits.
                c_health = coin.symbol + '_health'
                mname, mhead, mres = cache.get_or_set(c_health, get_manager(coin.symbol).health(), 30)
                # Create the dict keys for the manager name if needed, then add the health results
                d = hdic[mname] = dict(headings=list(mhead), results=[]) if mname not in hdic else hdic[mname]
                d['results'].append(list(mres))
            except:
                log.exception('Something went wrong loading health data for coin %s', coin)
                self.coin_fails.append(
                    'Failed checking {} (something went wrong loading health data, check server logs)'.format(coin)
                )
        return hdic

    def get(self, request, *args, **kwargs):
        r = self.request
        u = r.user
        if not u.is_authenticated or not u.is_superuser:
            raise PermissionDenied
        return super(CoinHealthView, self).get(request, *args, **kwargs)


def clear_cache(request):
    """Allow admins to clear the Django cache system"""
    if request.method.upper() != 'POST':
        raise HttpResponseNotAllowed(['POST'])

    u = request.user
    if not u.is_authenticated or not u.is_superuser:
        raise PermissionDenied
    cache.clear()
    # Redirect back to the previous page. If not set, send them to /
    referer = request.META.get('HTTP_REFERER', '/')
    messages.add_message(request, messages.SUCCESS, 'Successfully cleared Django cache')
    return redirect(referer)
