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
    payouts = {Coin.objects.get(symbol=fp['coin']): fp['fee'] for fp in qs_pay.annotate(fee=Sum('amount'))}
    fees = {c['from_coin']: c['fee'] for c in qs_fee.annotate(fee=Sum('ex_fee'))}
    #payouts_steem = {Coin.objects.using('steemengine').get(symbol=fp['coin']): fp['fee'] for fp in qs_pay.using('steemengine').annotate(fee=Sum('amount'))}
    #fees_steem = {c['from_coin']: c['fee'] for c in qs_fee.using('steemengine').annotate(fee=Sum('ex_fee'))}
    all_coins = [dict(coin_id=coin, amount=fees[coin]) for coin in fees.keys()] + \
                [dict(coin_id=coin, amount=-payouts[coin]) for coin in payouts.keys()]
               # [dict(coin_id=coin, amount=fees_steem[coin]) for coin in fees_steem.keys()] + \
               # [dict(coin_id=coin, amount=-payouts_steem[coin]) for coin in payouts_steem.keys()]
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
        if coin.symbol_id.startswith('GOLOS'):
            continue
        if payout['coin_id'].startswith('SWAP.'):
            native_coin = payout['coin_id'].split('.')[1]
        elif payout['coin_id'].endswith('P'):
            native_coin = payout['coin_id'][:-1]
        if native_coin.endswith('P'):
            native_coin = native_coin[:-1]
        if native_coin == 'BRIDGE.BTC':
            native_coin = 'BRIDGEBTC'
        if native_coin in summary:
            summary[native_coin]['amounts'][coin.symbol] = payout['amount']
            summary[native_coin]['info'][coin.symbol] = get_coin_info(coin, network)
        else:
            summary[native_coin] = dict(
                amounts={coin.symbol: payout['amount']},
                rate=get_price(native_coin, network),
                info={coin.symbol: get_coin_info(coin, network)},
            )
        if coin.symbol_id == 'BTCP':
            print(summary[native_coin])

    for native_coin in summary:
        summary[native_coin]['amount'] = f"{sum(summary[native_coin]['amounts'].values()):.2f}"
        summary[native_coin]['value'] = f"{summary[native_coin]['rate'] * Decimal(summary[native_coin]['amount']):.2f}"
        try:
            #qs_c = Coin.objects
            #if network == 'steem':
            #    qs_c = qs_c.using('steemengine')
            #coin = qs_c.get(symbol=native_coin)
            #print(native_coin)
            #print([info for sym, info in summary[native_coin]['info'].items() if sym != coin.symbol_id])
            summary[native_coin]['unused'] = - Decimal(sum([info['outstanding'] for sym, info in summary[native_coin]['info'].items() if sym != native_coin]))
        except Exception:
            log.exception(native_coin)
            log.info(summary[native_coin]['info'])
    return sorted(summary.items(), key=lambda i: Decimal(i[1]['value']), reverse=True)


@r_cache(lambda coin, network: f'info:{coin}')
def get_coin_info(coin, network):
    info = dict(
        current_bal = 0,
        circ_supply =0,
        outstanding =0, # real circ
        unused =0,
        )
    s = SteemEngineToken(network=network)
    try:
        if coin.our_account is None:
            info['current_bal'] = f'{get_manager(coin.symbol_id).rpc.getbalance():.2f}'
        elif network == 'hive':
            info['current_bal'] = f'{get_manager(coin.symbol_id).balance(coin.our_account):.2f}'
        else:
            if coin.symbol_id == 'BTCP':
                coin.our_account = 'btcpeg'
                log.info(f"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA {s.get_token_balance('btcpeg', 'BTCP')}")
            log.info(f'getting token balance of {coin.symbol_id} {network} {coin.our_account}')
            info['current_bal'] = f'{s.get_token_balance(coin.our_account, coin.symbol_id):.2f}'
    except Exception:
        log.exception(f'unable to get balance for {coin.symbol_id} {coin.our_account}')
        info['current_bal'] = 0

    try:
        token_info = s.get_token(coin.symbol_id)
        info['circ_supply'] = token_info['circulating_supply']
        info['outstanding'] = info['circ_supply'] - Decimal(info['current_bal'])
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
