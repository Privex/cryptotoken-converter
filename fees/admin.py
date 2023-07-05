import json
import logging
from decimal import Decimal

import requests
from django.contrib import admin, messages
from django.contrib.messages import add_message
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.db.models.aggregates import Sum
from django.db.models.query import QuerySet
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.views.generic.base import TemplateView
from getenv import env
from privex.helpers import DictObject, r_cache
from requests import Session, Timeout, TooManyRedirects

from fees.models import FeePayout
from payments.coin_handlers import get_loader, get_manager
from privex.steemengine import SteemEngineToken
from privex.steemengine.exceptions import NoResults
from payments.models import Conversion, Coin

log = logging.getLogger(__name__)


def confirm_send_payout(modeladmin, request, queryset: QuerySet):
    """
    Confirmation page for the "Suspend Services" page.
    """
    rp = request.POST
    payouts = []
    for d in queryset:  # type: FeePayout
        if d.paid:
            add_message(request, messages.ERROR, f'Cannot pay out ({d}) - already paid')
            continue
        payouts.append(d)

    if len(payouts) < 1:
        add_message(request, messages.ERROR, 'No valid cancellable services selected.')
        return redirect('/pvx_admin/billing/service/')

    return TemplateResponse(request, "admin/confirm_send_payout.html", {
        'payouts': payouts,
        'action': rp.get('action', ''),
        'select_across': rp.get('select_across', ''),
        'index': rp.get('index', ''),
        'selected_action': rp.get('_selected_action', ''),
    })


def send_payout(request):
    rp = request.POST
    objlist = rp.getlist('objects[]')
    if len(objlist) < 1:
        add_message(
            request, messages.ERROR,
            'No payouts selected.'
        )
        redirect(request.build_absolute_uri())
    password = rp.get('password')
    if password != env('FEE_PAYOUT_PASS'):
        raise Exception('Invalid password supplied to send payout')
    privex_wallets = {
        'BTC': 'bc1q2wjjd0fqqhf5uzy43kqyf5vsm37st8q8zuj8r4lyav3zyvvh3ytql736tu',
        'LTC': 'LWY6hPyHP98NdZMXFKn7EvmptQnUnsNvWv',
        'BCH': 'bitcoincash:prg0x58fkeln865q8fpse7r9zh5pyuqhdq5s5gv5k8',
        'EOS': 'privexinceos',
        'HBD': 'privex',
        'DOGE': 'DAeWUsC1Kr8R1EES8XnzLJvtfAN9iLjhZu',
        'WAX': 'privexinceos',
        'BLURT': ('blurt-swap', 'SWAP.BLURT privex'),
        'STEEM': 'privex'
    }
    he_wallets = {
        'BTC': 'bc1q324jejrpmyd23ejflhrluemsatuxa3ghuk5w3m',
        'LTC': 'MQxmGYkWK44Lwf38KSmxj7JNSt3B4P9wae',
        'BCH': 'bitcoincash:qznd0v0exhatqqpymtl8frqp4sfly6dmlvv8jva9hm',
        'EOS': '',
        'HBD': 'hive-engine',
        'DOGE': 'D695r3CS7LM8CJSRFMRcyGFxxww1wEy9gY',
        'WAX': '',
        'BLURT': ('blurt-swap', 'SWAP.BLURT hive-engine'),
        'STEEM': 'hive-engine'
    }
    for d in FeePayout.objects.filter(id__in=objlist):  # type: FeePayout
        try:
            if d.notes == 'privex':
                if d.coin.symbol.startswith('SWAP.'):
                    address = 'privex'
                else:
                    address = privex_wallets[d.coin.symbol]
            elif d.notes == 'hive engine':
                if d.coin.symbol.startswith('SWAP.'):
                    address = 'hive-engine'
                else:
                    address = he_wallets[d.coin.symbol]
            else:
                add_message(request, messages.ERROR, f'Unable to read notes during payout: {d} {d.notes}')
                continue
            if type(address) is tuple:
                get_manager(d.coin.symbol_id).send(d.amount, address=address[0], memo=address[1])
                add_message(request, messages.INFO, f"Sent {d.amount} {d.coin.symbol} to {address[0]}, memo: {address[1]}")
            elif address:
                get_manager(d.coin.symbol_id).send(d.amount, address=address)
                add_message(request, messages.INFO, f"Sent {d.amount} {d.coin.symbol} to {address}")
            else:
                add_message(request, messages.ERROR, f"Unable to transfer {d.coin.symbol}, no address for {d.notes}")
        except Exception as e:
            log.exception(f'Error while paying out {d}')
            add_message(request, messages.ERROR, f"Unable to pay out: {d} ({str(e)})")
    return redirect(request.build_absolute_uri())


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
        if not coin.enabled:
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


def get_coin_balances(coin):
    he = Coin.objects.filter(symbol='SWAP.' + get_native_coin(coin.symbol))
    se = Coin.objects.using('steemengine').filter(symbol=get_native_coin(coin.symbol) + 'P', coin_type='steemengine')
    balances = [get_coin_balance(coin)]
    try:
        balances += [get_coin_balance(hec, 'hive') for hec in he] + [get_coin_supply(hec, 'hive') for hec in he]
        balances += [get_coin_balance(sec, 'steem') for sec in se] + [get_coin_supply(sec, 'steem') for sec in se]
    except Exception:
        log.exception(f'unable to get balance/supply for {coin.symbol} {coin.our_account}')
    return balances


@r_cache(lambda coin, network: f'feecalc:supply:{network}:{coin.symbol}', cache_time=3600*6)
def get_coin_supply(coin, network):
    token_info = SteemEngineToken(network=network).get_token(coin.symbol)
    return coin.symbol + ' sup', -Decimal(token_info['circulating_supply'])


@r_cache(lambda coin, network=None: f'feecalc:balance:{network}:{coin}', cache_time=3600*6)
def get_coin_balance(coin, network=None):
    if coin.our_account is None:
        return 'RPC bal', Decimal(get_manager(coin.symbol).rpc.getbalance())
    elif network:
        return coin.symbol + ' bal', Decimal(SteemEngineToken(network=network).get_token_balance(coin.our_account, coin.symbol))
    else:
        return coin.symbol + ' bal', Decimal(get_manager(coin.symbol).balance(coin.our_account))


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
        if k == get_native_coin(k):
            unused[k]['balances'] = v['balances']
            unused[k]['unused'] += sum([bal[1] for bal in v['balances'] if bal])
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


class FeePayoutAdmin(admin.ModelAdmin):
    list_display = ('coin', 'amount', 'notes', 'created_at')
    list_filter = ('coin', 'created_at')
    ordering = ('created_at', 'updated_at')
    actions = [confirm_send_payout]
