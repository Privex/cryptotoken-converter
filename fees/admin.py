import logging
from decimal import Decimal

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models.aggregates import Sum
from django.db.models.query import QuerySet
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.views.generic.base import TemplateView
from privex.helpers import DictObject, r_cache

from fees.models import FeePayout
from payments.coin_handlers import get_loader, get_manager
from privex.steemengine import SteemEngineToken
from privex.steemengine.exceptions import NoResults
from payments.models import Conversion, Coin

log = logging.getLogger(__name__)


def get_payout(since='1970-01-01'):
    qs_pay = FeePayout.objects.values('coin').filter(created_at__gt=since)
    qs_fee = Conversion.objects.values('from_coin_id').filter(created_at__gt=since)
    payouts = {fp['coin']: fp['fee'] for fp in qs_pay.annotate(fee=Sum('amount'))}
    fees = {c['from_coin_id']: c['fee'] for c in qs_fee.annotate(fee=Sum('ex_fee'))}
    payouts_steem = {fp['coin']: fp['fee'] for fp in qs_pay.using('steemengine').annotate(fee=Sum('amount'))}
    fees_steem = {c['from_coin_id']: c['fee'] for c in qs_fee.using('steemengine').annotate(fee=Sum('ex_fee'))}
    all_coins = [dict(coin_id=coin, amount=fees[coin]) for coin in fees.keys()] + \
                [dict(coin_id=coin, amount=-payouts[coin]) for coin in payouts.keys()] + \
                [dict(coin_id=coin, amount=fees_steem[coin]) for coin in fees_steem.keys()] + \
                [dict(coin_id=coin, amount=-payouts_steem[coin]) for coin in payouts_steem.keys()]
    summary = {}
    for payout in all_coins:
        try:
            coin = Coin.objects.get(symbol=payout['coin_id'])
            native_coin = coin.symbol_id
            network = 'hive'
        except Coin.DoesNotExist:
            coin = Coin.objects.using('steemengine').get(symbol=payout['coin_id'])
            native_coin = coin.symbol_id
            network = 'steem'
        if payout['coin_id'].startswith('SWAP.'):
            native_coin = payout['coin_id'].split('.')[1]
        elif payout['coin_id'].endswith('P'):
            native_coin = payout['coin_id'][:-1]
        if native_coin.endswith('P'):
            native_coin = native_coin[:-1]
        if native_coin == 'BRIDGE.BTC':
            native_coin = 'BRIDGEBTC'
        if native_coin in summary:
            summary[native_coin]['amount'] = summary[native_coin]['amount'] + payout['amount']
            summary[native_coin]['info'][coin.symbol_id] = get_coin_info(coin)
        else:
            summary[native_coin] = dict(
                amount=payout['amount'],
                rate=get_price(native_coin, network),
                info={coin.symbol_id: get_coin_info(coin)}
            )
    for native_coin in summary:
        summary[native_coin]['value'] = f"{summary[native_coin]['rate'] * summary[native_coin]['amount']:.2f}"
        summary[native_coin]['amount'] = f"{summary[native_coin]['amount']:.2f}"
    return sorted(summary.items(), key=lambda i: Decimal(i[1]['value']), reverse=True)


def get_coin_info(coin):
    info = dict(
        current_bal = 0,
        circ_supply =0,
        outstanding =0,
        unused =0,
        )
    try:
        info['current_bal'] = f'{get_manager(coin.symbol_id).balance(coin.our_account):.2f}'
    except Exception:
        pass
    return info


@r_cache(lambda coin, network: f'price:{network}:{coin}')
def get_price(coin, network):
    if network == 'steem':
        fake_coin = coin + 'P'
    elif network == 'hive':
        fake_coin = 'SWAP.' + coin
    if coin == 'APX':
        return Decimal(0.00695810)
    try:
        rate = SteemEngineToken(network=network).get_ticker(fake_coin).lastPrice
    except NoResults:
        try:
            rate = SteemEngineToken(network=network).get_ticker(coin).lastPrice
        except (NoResults, Exception):
            rate = 0
    except Exception:
        rate = 0
    return rate


class FeePayoutAdmin(admin.ModelAdmin):
    list_display = ('coin', 'amount', 'created_at')
    list_filter = ('coin', 'created_at')
    ordering = ('created_at', 'updated_at')


class FeePayoutView(TemplateView):
    template_name = 'admin/fee_payout.html'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_context_data(self, **kwargs):
        context = super(FeePayoutView, self).get_context_data(**kwargs)
        context['payout'] = get_payout()
        context['payout2'] = get_payout(FeePayout.objects.order_by('-created_at')[0].created_at)
        return context

    def get(self, request, *args, **kwargs):
        r = self.request
        u = r.user
        if not u.is_authenticated or not u.is_superuser:
            raise PermissionDenied
        return super(FeePayoutView, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        r = self.request
        u = r.user
        if not u.is_authenticated or not u.is_superuser:
            raise PermissionDenied
        FeePayout.objects.bulk_create([FeePayout(**p) for p in get_payout()])
        return redirect('admin:fee_payout')
