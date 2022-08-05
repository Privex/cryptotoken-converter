import logging
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib import admin, messages

# Register your models here.
from django.contrib.admin import AdminSite
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import User, Group
from django.contrib.messages.api import add_message
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models.query import QuerySet
from django.http import HttpResponseNotAllowed
from django.shortcuts import render, redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone
from django.views.decorators.cache import cache_page
from django.views.generic import TemplateView
from privex.helpers import empty, is_true

from fees.admin import FeePayoutView, FeePayoutAdmin
from fees.models import FeePayout
from payments.models import Coin, Deposit, AddressAccountMap, CoinPair, Conversion, CryptoKeyPair

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


def confirm_refund_deposit(modeladmin, request, queryset: QuerySet):
    """
    Confirmation page for the "Refund Deposits to Sender" page.
    :param modeladmin:
    :param request:
    :param queryset:
    :return:
    """
    rp = request.POST
    deps = []
    for d in queryset:   # type: Deposit
        if empty(d.from_account):
            add_message(
                request, messages.ERROR, f'Cannot refund deposit ({d}) - from_account is blank!'
            )
            continue
        deps.append(d)

    if len(deps) < 1:
        add_message(
            request, messages.ERROR,
            'No valid refundable deposits selected. Only deposits with from_account can be refunded.'
        )
        return redirect('/admin/payments/deposit/')

    return TemplateResponse(request, "admin/refund.html", {
        'deposits': deps,
        'action': rp.get('action', ''),
        'select_across': rp.get('select_across', ''),
        'index': rp.get('index', ''),
        'selected_action': rp.get('_selected_action', ''),
    })


confirm_refund_deposit.short_description = "Refund Deposits to Sender"


def refund_deposits(request):
    rp = request.POST
    objlist = rp.getlist('objects[]')
    if empty(rp.get('refund')) or empty(objlist, itr=True):
        log.info('Refund value: %s - Objects: %s', rp.get('refund'), objlist)
        add_message(
            request, messages.ERROR, f'Error - missing POST data for refund_deposits!'
        )
        return redirect('/admin/payments/deposit/')

    deposits = Deposit.objects.filter(id__in=objlist)
    for d in deposits:  # type: Deposit
        try:
            if empty(d.from_account):
                add_message(
                    request, messages.ERROR, f'Cannot refund deposit ({d}) - from_account is blank!'
                )
                continue
            with transaction.atomic():
                log.info('Attempting to refund deposit (%s)', d)

                convs = Conversion.objects.filter(deposit=d)

                if len(convs) > 0:
                    for conv in convs:
                        log.info('Removing linked conversion %s', conv)
                        add_message(request, messages.WARNING, f'Removed linked conversion {str(conv)}')
                        conv.delete()

                sym = d.coin_symbol
                memo = f'Refund of {sym} deposit {d.txid}'

                log.debug('Initializing manager for %s', sym)
                mgr = get_manager(sym)

                log.debug('Calling send_or_issue for amount "%s" to address "%s" with memo "%s"',
                          d.amount, d.from_account, memo)

                res = mgr.send_or_issue(amount=d.amount, address=d.from_account, memo=memo)

                d.status = 'refund'
                d.refunded_at = timezone.now()
                d.refund_coin = res.get('coin', sym)
                d.refund_memo = memo
                d.refund_amount = res.get('amount', d.amount)
                d.refund_address = d.from_account
                d.refund_txid = res.get('txid', 'N/A')
                d.save()



                add_message(
                    request, messages.SUCCESS, f'Successfully refunded {d.amount} {sym} to {d.from_account}'
                )
        except Exception as e:
            d.status = 'err'
            d.error_reason = f'Error while refunding: {type(e)} {str(e)}'
            log.exception('Error while refunding deposit %s', d)
            d.save()
            add_message(
                request, messages.ERROR, f'Error while refunding deposit ({d}) - Reason: {type(e)} {str(e)}'
            )
    return redirect('/admin/payments/deposit/')



class CustomAdmin(AdminSite):
    """
    To allow for custom admin views, we override AdminSite, so we can add custom URLs, among other things.
    """

    def get_urls(self):
        _urls = super(CustomAdmin, self).get_urls()
        urls = [
            path('coin_health/', CoinHealthView.as_view(), name='coin_health'),
            path('add_coin_pair/', AddCoinPairView.as_view(), name='easy_add_pair'),
            path('refund_deposits/', refund_deposits, name='refund_deposits'),
            path('_clear_cache/', clear_cache, name='clear_cache'),
            path('fee_payout/', FeePayoutView.as_view(), name='fee_payout')
        ]
        return _urls + urls


ctadmin = CustomAdmin()


class CoinAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'symbol', 'coin_type', 'enabled', 'our_account', 'can_issue')
    list_filter = ('coin_type',)
    ordering = ('symbol',)

    fieldsets = (
        ('Unique Coin Symbol for refrencing from the API', {
            'fields': ('symbol',),
            'description': "<p><strong>Help:</strong> The 'Unique Coin Symbol' is not passed to the handler, and thus "
                           "doesn't need to match the real token symbol on the network, it just needs to be unique, as "
                           "it acts as the ID of the coin when making API calls.</p>"
                           "</p><br/><hr/>"
        }),
        ("Native Token Symbol (must match the real symbol on it's network)", {
            'fields': ('symbol_id',),
            'description': "<p>The 'Native Coin Symbol' is passed to the coin handler and does not have to be unique, "
                           "but it MUST match the real symbol used by the token, otherwise the  "
                           "coin handler will be unable to send/receive the token.<br/><strong>If you leave this field "
                           "blank when creating the coin, it will default to the Unique Coin Symbol.</strong>"
                           "</p><br/><hr/>"
        }),
        ('Display name, Coin Type (handler), Enable/Disable coin', {
            'fields': ('display_name', 'coin_type', 'enabled'),
            'description': "<p><strong>Help:</strong> The 'Display Name' is returned in API calls, and shown in the"
                           " admin panel.</p> "
                           "<p>The 'Coin Type' must be set correctly, it determines which network this coin is on, so "
                           "that the correct <strong>Coin Handler</strong> will be used for the coin.</p>"
                           "<p>The 'Enabled' option decides whether or not this coin is in use. If you uncheck this, "
                           "no conversions will take place for this coin, and it will not be returned on the API."
                           "</p><hr/>"
        }),
        ('Our account/address, and whether we can issue this coin', {
            'fields': ('our_account', 'can_issue'),
            'description': "<p><strong>Help:</strong> The 'Our Account (or address)' is passed to the coin handler "
                           "and may not always need to be specified. For account based networks such as Steem, this "
                           "setting generally MUST be filled in. <br/> "
                           "The 'Can Issue' option determines whether the system should attempt to issue a token if "
                           "our balance is too low to fulfill a conversion. If you are not the issuer of a token, "
                           "keep this un-ticked.</p><hr/>"
        }),
        ('(Advanced) Coin Handler Settings', {
            'classes': ('collapse',),
            'fields': ('setting_host', 'setting_port', 'setting_user', 'setting_pass', 'setting_json'),
            'description': "<p><strong>Help:</strong> The 'Handler Settings' are all optional. Most coins will work "
                           "just fine without changing any of these options. <br/>"
                           "The host/port/user/pass settings are designed for selecting a certain RPC node, "
                           "however these may not always be respected by every handler.<br/> "
                           "The 'Custom JSON' field allows for additional settings specific to the coin handler, "
                           "and you must enter valid JSON in this field, for example:</p> "
                           "<code>{\"contract\": \"eosio.token\"}</code><br/><br/><hr/>"
        }),
        ('Low Funds Email Alert Settings', {
            'classes': ('collapse',),
            'fields': ('notify_low_funds', 'funds_low', 'last_notified'),
            'description': "<p><strong>Help:</strong> You generally only need to touch the checkbox 'Send an email"
                           " notification', as the 'Deposits currently stuck' and 'Last Email Notification' are "
                           "automatically managed by the system.</p><hr/>"
        }),
    )

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
    list_display = ('__str__', 'from_coin', 'to_coin', 'exchange_rate')
    ordering = ('from_coin', 'to_coin')


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
    ordering = ('-tx_timestamp',)
    actions = [confirm_refund_deposit]


class KeyPairAdmin(admin.ModelAdmin):
    list_display = ('network', 'public_key', 'account', 'key_type')
    ordering = ('network', 'account')


# Because we've overridden the admin site, the default user/group admin doesn't register properly.
# So we manually register them to their admin views.
ctadmin.register(User, UserAdmin)
ctadmin.register(Group, GroupAdmin)

ctadmin.register(Coin, CoinAdmin)
ctadmin.register(CoinPair, CoinPairAdmin)
ctadmin.register(Conversion, ConversionAdmin)
ctadmin.register(Deposit, DepositAdmin)
ctadmin.register(AddressAccountMap, AddressAccountMapAdmin)
ctadmin.register(CryptoKeyPair, KeyPairAdmin)

ctadmin.register(FeePayout, FeePayoutAdmin)


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
        hdic = {}  # A dictionary of {handler_name: {headings:list, results:list[tuple/list]}
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


class AddCoinPairView(TemplateView):
    """
    Admin view for easily adding two coins + two pairs in each direction
    """
    template_name = 'admin/add_pair.html'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def coin_types(self):
        """View function to be called from template, for getting list of coin handler errors"""
        return settings.COIN_TYPES

    def get(self, request, *args, **kwargs):
        r = self.request
        u = r.user
        if not u.is_authenticated or not u.is_superuser:
            raise PermissionDenied
        reload_handlers()
        return super(AddCoinPairView, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        p = request.POST
        one = dict(
            symbol=p.get('symbol_one'),
            symbol_id=p.get('symbol_id_one'),
            can_issue=is_true(p.get('issue_one')),
            coin_type=p.get('coin_type_one'),
            our_account=p.get('our_account_one'),
            display_name=p.get('display_one'),
        )
        two = dict(
            symbol=p.get('symbol_two'),
            symbol_id=p.get('symbol_id_two'),
            can_issue=is_true(p.get('issue_two')),
            coin_type=p.get('coin_type_two'),
            our_account=p.get('our_account_two'),
            display_name=p.get('display_two'),
        )

        if empty(one['symbol']):
            messages.add_message(request, messages.ERROR, 'Unique symbol not specified for Coin One.')
            return redirect('admin:easy_add_pair')
        if empty(one['coin_type']) or one['coin_type'] not in dict(settings.COIN_TYPES):
            messages.add_message(request, messages.ERROR, 'Invalid coin type for Coin Two.')
            return redirect('admin:easy_add_pair')
        if empty(two['symbol']):
            messages.add_message(request, messages.ERROR, 'Unique symbol not specified for Coin Two.')
            return redirect('admin:easy_add_pair')
        if empty(two['coin_type']) or two['coin_type'] not in dict(settings.COIN_TYPES):
            messages.add_message(request, messages.ERROR, 'Invalid coin type for Coin Two.')
            return redirect('admin:easy_add_pair')

        c_one = Coin(**one)
        c_one.save()
        messages.add_message(request, messages.SUCCESS, f'Created Coin object {c_one}.')

        c_two = Coin(**two)
        c_two.save()
        messages.add_message(request, messages.SUCCESS, f'Created Coin object {c_two}.')

        p_one = CoinPair(from_coin=c_one, to_coin=c_two, exchange_rate=Decimal('1'))
        p_two = CoinPair(from_coin=c_two, to_coin=c_one, exchange_rate=Decimal('1'))
        p_one.save()
        p_two.save()
        messages.add_message(request, messages.SUCCESS, f'Created CoinPair object {p_one}.')
        messages.add_message(request, messages.SUCCESS, f'Created CoinPair object {p_two}.')

        return redirect('admin:easy_add_pair')

