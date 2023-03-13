import json
import logging
from decimal import Decimal

import requests
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.db.models.aggregates import Sum
from django.db.models.query import QuerySet
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.views.generic.base import TemplateView
from privex.helpers import DictObject, r_cache
from requests import Session, Timeout, TooManyRedirects

from fees.models import FeePayout
from payments.coin_handlers import get_loader, get_manager
from privex.steemengine import SteemEngineToken
from privex.steemengine.exceptions import NoResults
from payments.models import Conversion, Coin

log = logging.getLogger(__name__)


def get_payout(since='1970-01-01', sort=True):
    qs_pay = FeePayout.objects.values('coin_id').filter(created_at__gt=since)
    qs_fee = Conversion.objects.values('from_coin_id').filter(created_at__gt=since)
    payouts = {p['coin_id']: p['fee'] for p in qs_pay.annotate(fee=Sum('amount'))}
    fees = {f['from_coin_id']: f['fee'] for f in qs_fee.annotate(fee=Sum('ex_fee'))}
    all_coins = [dict(coin_id=coin, amount=fees[coin]) for coin in fees.keys()] + \
                [dict(coin_id=coin, amount=-payouts[coin]) for coin in payouts.keys()]
    summary = {}
    for payout in all_coins:
        coin = Coin.objects.get(symbol=payout['coin_id'])
        if 'GOLOS' in coin.symbol_id:
            continue
        coin_id = payout['coin_id']
        # collect info
        if coin_id in summary:
            if payout['amount'] > 0:
                summary[coin_id]['fees'] += payout['amount']
            if coin.symbol in summary[coin_id]['amounts']:
                summary[coin_id]['amounts'][coin.symbol] += payout['amount']
            else:
                summary[coin_id]['amounts'][coin.symbol] = payout['amount']
        else:
            rate = get_price(coin_id)
            if rate == 0:
                if 'SWAP.' in coin_id:
                    rate = get_price(coin_id[5:])
                if 'BTCP' == coin_id:
                    rate = get_price('BTC')
            summary[coin_id] = dict(
                amounts={coin.symbol: payout['amount']},
                rate=rate,
                fees=max(payout['amount'], 0)
            )
    # summarize
    for coin_id in summary:
        #summary[coin_id]['info'] = info[coin_id]
        summary[coin_id]['decimals'] = 4 if 'BTC' in coin_id else 2
        summary[coin_id]['amount'] = sum(summary[coin_id]['amounts'].values())
        summary[coin_id]['value'] = f"{summary[coin_id]['rate'] * Decimal(summary[coin_id]['amount']):.2f}"
        summary[coin_id]['balances'] = get_coin_balances(Coin.objects.get(symbol=coin_id))
    if sort:
        return sorted(summary.items(), key=lambda i: Decimal(i[1]['value']), reverse=True)
    else:
        return summary


@r_cache(lambda coin: f'info:{coin}', cache_time=3600*6)
def get_coin_balances(coin):
    balances = []
    try:
        if coin.our_account is None:
            balances = [('RPC bal', Decimal(get_manager(coin.symbol_id).rpc.getbalance()))]
        else:
            balances = [(coin.symbol_id + ' bal', Decimal(get_manager(coin.symbol_id).balance(coin.our_account)))]
    except Exception:
        log.exception(f'unable to get balance for {coin.symbol_id} {coin.our_account}')
    #if coin.symbol == 'BTCP' or 'EOS' in 'coin.symbol':
    #    return
    if coin.symbol.startswith('SWAP.'):
        try:
            token_info = SteemEngineToken(network='hive').get_token(coin.symbol)
            balances.append((coin.symbol + ' sup', -Decimal(token_info['circulating_supply'])))
        except Exception:
            log.exception(f'unable to get supply for {coin.symbol_id}')
    elif not coin.symbol.endswith('P'):  # native
        se = SteemEngineToken(network='steem')
        for sec in Coin.objects.using('steemengine').filter(
            coin_type='steemengine').filter(Q(symbol=get_native_coin(coin.symbol) + 'P') |
                                            Q(symbol='SWAP.' + get_native_coin(coin.symbol))):
            try:
                balances.append((sec.symbol + ' sup' + sec.symbol, -Decimal(se.get_token(sec.symbol)['circulating_supply'])))
                balances.append((sec.symbol + ' bal', Decimal(se.get_token_balance(sec.our_account, sec.symbol))))
            except Exception:
                log.exception(f'Unable to get Steem-Engine balances for {coin.symbol} ({sec.symbol})')
    else:  # btcp
        pass
    return balances


def get_price(coin: str):
    if coin == 'SAND':
        return Decimal(0.000851225622)
    if coin == 'WAX':
        coin = 'WAXP'
    data = get_coinmarketcap_data()
    for listing in data:
        if listing['symbol'] == coin:
            return Decimal(listing['quote']['USD']['price'])
    else:
        return Decimal(0)


@r_cache('cmc_data', cache_time=3600*24)
def get_coinmarketcap_data():
    url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest'
    parameters = {
        'start': '1',
        'limit': '5000',
        'convert': 'USD'
    }
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': '2b653ab6-2fe2-4ff5-8536-88666fce9e1d',
    }

    session = Session()
    session.headers.update(headers)

    try:
        data = []
        for i in range(0, 3):
            parameters['start'] = i*5000 + 1
            response = session.get(url, params=parameters)
            data = data + json.loads(response.text)['data']
        return data
    except (ConnectionError, Timeout, TooManyRedirects) as e:
        log.error('Unable to get CMC Listings')


class FeePayoutAdmin(admin.ModelAdmin):
    list_display = ('coin', 'amount', 'created_at')
    list_filter = ('coin', 'created_at')
    ordering = ('created_at', 'updated_at')


def get_native_coin(k):
    if 'SWAP.' in k:
        native_coin = k[5:]
    elif k.endswith('P'):
        native_coin = k[:-1]
    elif k.startswith('EOS') and len(k) > 3:
        native_coin = k[3:]
    else:
        native_coin = k
    return native_coin


def get_unused(payout):
    unused = {coin_id: dict(unused=0, decimals=v['decimals'], balances=[]) for coin_id, v in payout if
              not (coin_id.startswith('SWAP.') or coin_id.endswith('P'))}
    for k, v in payout:
        unused[get_native_coin(k)]['balances'].extend(v['balances'])
        unused[get_native_coin(k)]['unused'] += sum([bal[1] for bal in v['balances']])
    return unused


def get_payout_table():
    payout = get_payout(FeePayout.objects.values('created_at').order_by('-created_at').first()['created_at'], sort=False)
    payout_table = {}
    for coin, pr in payout.items():
        payout_table[coin] = dict(
            native=get_native_coin(coin) == coin,
            price=pr.get('rate', ''),
            decimals=pr['decimals'],
            fee_amount=pr['amount'],
            total_fees=pr['amount'],
        )
    for coin, pr in payout_table.items():
        if not pr['native']:
            payout_table[get_native_coin(coin)]['total_fees'] += pr['fee_amount']
    privex_share = Decimal(0.25)
    he_share = Decimal(0.75)
    for coin, pr in payout_table.items():
        if pr['native']:
            pr['value'] = pr['total_fees'] * pr['price']
            pr['privex_cut'] = pr['total_fees'] * privex_share
            try:
                swap_coin = Coin.objects.get(symbol_id='SWAP.' + coin)
                pr['he_cut'] = max(pr['total_fees'] * he_share - Decimal(
                    get_manager(swap_coin.symbol_id).balance(swap_coin.our_account)), 0)
                if pr['he_cut'] == 0:
                    del pr['he_cut']
            except Coin.DoesNotExist:
                pass
        else:
            pr['value'] = ''
            try:
                swap_coin = Coin.objects.get(symbol_id=coin)
                pr['he_balance'] = Decimal(get_manager(swap_coin.symbol_id).balance(swap_coin.our_account))
                pr['he_cut'] = min(payout_table[get_native_coin(coin)]['total_fees'] * he_share, pr['he_balance'])
            except Coin.DoesNotExist:
                pass
            pr['total_fees'] = ''
    coins = ['LTC', 'BTC', 'HBD', 'WAX', 'DOGE', 'STEEM', 'BLURT', 'BCH', 'EOS']
    return filter(lambda t: t[0] in coins or get_native_coin(t[0]) in coins,
                  sorted(payout_table.items(),
                         key=lambda i: (Decimal(0.00000001) if 'SWAP' in i[0] else Decimal(1)) * i[1]['price'],
                         reverse=True))


class FeePayoutView(TemplateView):
    template_name = 'admin/fee_payout.html'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_context_data(self, **kwargs):
        context = super(FeePayoutView, self).get_context_data(**kwargs)
        context['payout'] = get_payout()
        context['payout2'] = get_payout(FeePayout.objects.order_by('-created_at')[0].created_at)
        context['unused'] = get_unused(context['payout'])
        context['payout_table'] = get_payout_table()
        #context['prices'] = {coin: price for coin in context['payout']}
        return context

    def get(self, request, *args, **kwargs):
        r = self.request
        u = r.user
        if not u.is_authenticated or not u.is_superuser:
            raise PermissionDenied
        return super(FeePayoutView, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        p = self.request
        u = p.user
        if not u.is_authenticated or not u.is_superuser:
            raise PermissionDenied
        for coin, p in self.get_context_data()['payout_table']:
            if p.get('he_cut', 0):
                FeePayout(coin_id=coin, amount=p['he_cut'], notes='hive engine').save()
            if p.get('privex_cut', 0):
                FeePayout(coin_id=coin, amount=p['privex_cut'], notes='privex').save()
        return redirect('admin:fee_payout')
