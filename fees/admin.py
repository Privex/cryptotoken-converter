import csv
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
from django.http import HttpResponse
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

CMC_API_KEY = '2b653ab6-2fe2-4ff5-8536-88666fce9e1d'


privex_wallets = {
    'BTC': 'bc1q2wjjd0fqqhf5uzy43kqyf5vsm37st8q8zuj8r4lyav3zyvvh3ytql736tu',
    'LTC': 'LWY6hPyHP98NdZMXFKn7EvmptQnUnsNvWv',
    'BCH': 'bitcoincash:prg0x58fkeln865q8fpse7r9zh5pyuqhdq5s5gv5k8',
    'EOS': 'privexinceos',
    'HBD': 'privex',
    'DOGE': 'DAeWUsC1Kr8R1EES8XnzLJvtfAN9iLjhZu',
    'WAX': 'privexinceos',
    'BLURT': 'privex',
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
    'BLURT': 'hive-engine',
    'STEEM': 'hive-engine'
}


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
        add_message(request, messages.ERROR, 'No unpaid payouts selected.')
        return redirect('/admin/fees/feepayout/')

    return TemplateResponse(request, "admin/confirm_send_payout.html", {
        'payouts': payouts,
        'action': rp.get('action', ''),
        'select_across': rp.get('select_across', ''),
        'index': rp.get('index', ''),
        'selected_action': rp.get('_selected_action', ''),
    })


confirm_send_payout.short_description = 'Send Payout'


def export_fee_payments_csv(modeladmin, request, queryset: QuerySet):
    """Export selected fee payouts as CSV with base-asset USD price/value at payout time."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="fee_payments.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'id', 'coin', 'base_asset', 'amount', 'notes', 'paid', 'created_at',
        'base_price_usd', 'dollar_value',
    ])
    for payout in queryset.select_related('coin').order_by('created_at', 'id'):
        base_asset = get_native_coin(payout.coin.symbol)
        price = get_historical_price(base_asset, payout.created_at)
        if price:
            value = (Decimal(payout.amount) * price).quantize(Decimal('0.01'))
        else:
            price = Decimal(0)
            value = None
        writer.writerow([
            payout.id,
            payout.coin.symbol,
            base_asset,
            payout.amount,
            payout.notes,
            payout.paid,
            payout.created_at.isoformat(sep=' ', timespec='seconds'),
            price,
            value,
        ])
    return response


export_fee_payments_csv.short_description = 'Export selected fee payments as CSV'


def send_payout(request):
    rp = request.POST
    objlist = rp.getlist('objects[]')
    if len(objlist) < 1:
        add_message(
            request, messages.ERROR,
            'No payouts selected.'
        )
        redirect('/admin/fees/feepayout/')
    password = rp.get('password')
    if password != env('FEE_PAYOUT_PASS'):
        raise Exception('Invalid password supplied to send payout')
    for d in FeePayout.objects.filter(id__in=objlist):  # type: FeePayout
        status, msg = do_payout(d)
        add_message(request, messages.INFO if status else messages.ERROR, msg)
    return redirect('/admin/fees/feepayout/')


def do_payout(d: FeePayout):
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
        elif d.notes == 'aggroed':
            if d.coin.symbol.startswith('SWAP.'):
                address = 'aggroed'
            else:
                return False, 'Unable to distribute non SWAP coin to aggroed'
        else:
            return False, f'Unable to read notes during payout: {d} {d.notes}'
        if type(address) is tuple:
            get_manager(d.coin.symbol_id).send(d.amount, address=address[0], memo=address[1])
            d.paid = True
            d.save()
            return True, f"Sent {d.amount} {d.coin.symbol} to {address[0]}, memo: {address[1]}"
        elif address:
            get_manager(d.coin.symbol_id).send(d.amount, address=address)
            d.paid = True
            d.save()
            return True, f"Sent {d.amount} {d.coin.symbol} to {address}"
        else:
            return False, f"Unable to transfer {d.coin.symbol}, no address for {d.notes}"
    except Exception as e:
        log.exception(f'Error while paying out {d}')
        return False, f"Unable to pay out: {d} ({str(e)} {e.__class__.__name__})"


def get_payout(since='1970-01-01', sort=True, by_native=True):
    qs_pay = FeePayout.objects.values('coin_id').exclude(notes__in=['aggroed', 'hive engine (surplus)']).filter(created_at__gt=since)
    qs_fee = Conversion.objects.values('from_coin_id').filter(created_at__gt=since)
    qs_fee_se = Conversion.objects.using('steemengine').values('from_coin_id').filter(created_at__gt=since)
    payouts = {p['coin_id']: p['fee'] for p in qs_pay.annotate(fee=Sum('amount'))}
    fees = {f['from_coin_id']: f['fee'] for f in qs_fee.annotate(fee=Sum('ex_fee'))}
    fees_se = {f['from_coin_id']: f['fee'] for f in qs_fee_se.annotate(fee=Sum('ex_fee'))}
    all_coins = [dict(coin_id=coin, amount=fees[coin]) for coin in fees.keys()] + \
                [dict(coin_id=coin, amount=fees_se[coin], se=True) for coin in fees_se.keys()] + \
                [dict(coin_id=coin, amount=-payouts[coin]) for coin in payouts.keys()]
    summary = {}
    for payout in all_coins:
        coin_id = payout['coin_id']
        ncoin_id = get_native_coin(coin_id)
        if by_native:
            coin_id = ncoin_id
        co = Coin.objects
        if payout.get('se', False):
            co = co.using('steemengine')
        try:
            coin = co.get(symbol=coin_id)
        except Coin.DoesNotExist:
            try:
                coin = co.get(symbol=ncoin_id)
            except Coin.DoesNotExist:
                continue
        if not coin.enabled:
            continue
        # collect info
        if coin_id in summary:
            if payout['amount'] > 0:
                summary[coin_id]['fees'] += payout['amount']
            if coin_id in summary[coin_id]['amounts']:
                summary[coin_id]['amounts'][coin_id] += payout['amount']
            else:
                summary[coin_id]['amounts'][coin_id] = payout['amount']
        else:
            rate = get_price(coin_id if by_native else ncoin_id)
            summary[coin_id] = dict(
                amounts={coin_id: payout['amount']},
                rate=rate,
                fees=max(payout['amount'], 0)
            )
        summary[coin_id]['coin'] = coin
    # summarize
    for coin_id in summary:
        #summary[coin_id]['info'] = info[coin_id]
        summary[coin_id]['decimals'] = 4 if 'BTC' in coin_id else 2
        summary[coin_id]['amount'] = sum(summary[coin_id]['amounts'].values())
        summary[coin_id]['value'] = f"{summary[coin_id]['rate'] * Decimal(summary[coin_id]['amount']):.2f}"
        try:
            summary[coin_id]['balances'] = get_coin_balances(summary[coin_id]['coin'])
        except UnboundLocalError:
            summary[coin_id]['error'] = True
            summary[coin_id]['balances'] = []
    if sort:
        return sorted(summary.items(), key=lambda i: Decimal(i[1]['value']), reverse=True)
    else:
        return summary


def get_coin_balances(coin):
    he = Coin.objects.filter(symbol='SWAP.' + get_native_coin(coin.symbol))
    #se = Coin.objects.using('steemengine').filter(symbol=get_native_coin(coin.symbol) + 'P', coin_type='steemengine')
    try:
        balances = [get_coin_balance(coin)]
        balances += [get_coin_balance(hec, 'hive') for hec in he] + [get_coin_supply(hec, 'hive') for hec in he]
        #balances += [get_coin_balance(sec, 'steem') for sec in se] + [get_coin_supply(sec, 'steem') for sec in se]
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
    elif network == 'steem':
        #return coin.symbol + ' bal', Decimal(SteemEngineToken(network=network).get_token_balance(coin.our_account, coin.symbol))
        return coin.symbol + ' steem n/a', Decimal(0)
    else:
        try:
            bal = Decimal(get_manager(coin.symbol).balance(coin.our_account))
            if coin.symbol == 'HBD':
                bal += Decimal(25518.074)
            return coin.symbol + ' bal', bal
        except KeyError:
            return coin.symbol + ' steem n/a', Decimal(0)
        except Exception as e:
            return coin.symbol + f' exc {e.__class__.__name__}', Decimal(0)


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


def get_historical_price(coin: str, when):
    """USD price for ``coin`` on the UTC date of ``when``. Returns 0 if the API call fails."""
    if coin == 'SAND':
        return Decimal(0.000851225622)
    if coin == 'WAX':
        coin = 'WAXP'
    day = when.strftime('%Y-%m-%d') if hasattr(when, 'strftime') else str(when)[:10]
    return _get_historical_price(coin, day) or Decimal(0)


def _cmc_session():
    session = Session()
    session.headers.update({
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': CMC_API_KEY,
    })
    return session


@r_cache(lambda coin: f'cmc_id:{coin}', cache_time=3600 * 24 * 7)
def get_cmc_id(coin: str):
    """Resolve a ticker to the best-matching CoinMarketCap asset id."""
    if coin == 'WAX':
        coin = 'WAXP'
    try:
        response = _cmc_session().get(
            'https://pro-api.coinmarketcap.com/v1/cryptocurrency/map',
            params={'symbol': coin},
        )
        payload = json.loads(response.text)
        matches = [
            item for item in (payload.get('data') or [])
            if item.get('symbol') == coin
        ]
        if not matches:
            log.warning('No CMC id for %s: %s', coin, payload.get('status'))
            return None
        matches.sort(key=lambda item: (
            0 if item.get('is_active') else 1,
            item.get('rank') if item.get('rank') is not None else 999999,
            item['id'],
        ))
        return matches[0]['id']
    except (ConnectionError, Timeout, TooManyRedirects, KeyError, TypeError, ValueError) as e:
        log.error('Unable to resolve CMC id for %s: %s', coin, e)
        return None


@r_cache(lambda coin, day: f'cmc_hist_v2:{coin}:{day}', cache_time=3600 * 24 * 30)
def _get_historical_price(coin: str, day: str):
    cmc_id = get_cmc_id(coin)
    if not cmc_id:
        return Decimal(0)
    url = 'https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/historical'
    parameters = {
        'id': str(cmc_id),
        'time_end': f'{day}T23:59:00.000Z',
        'count': '1',
        'interval': 'daily',
        'convert': 'USD',
    }
    try:
        response = _cmc_session().get(url, params=parameters)
        payload = json.loads(response.text)
        status = payload.get('status') or {}
        if status.get('error_code'):
            log.warning(
                'CMC historical error for %s (%s) on %s: %s',
                coin, cmc_id, day, status.get('error_message'),
            )
            return Decimal(0)
        data = payload.get('data') or {}
        # v2 returns a single asset object; tolerate id-keyed shapes too
        if isinstance(data, dict) and 'quotes' not in data:
            data = data.get(str(cmc_id)) or data.get(cmc_id) or {}
        quotes = (data or {}).get('quotes') or []
        if not quotes:
            log.warning('No CMC historical quotes for %s (%s) on %s', coin, cmc_id, day)
            return Decimal(0)
        return Decimal(str(quotes[-1]['quote']['USD']['price']))
    except (ConnectionError, Timeout, TooManyRedirects, KeyError, TypeError, ValueError) as e:
        log.error('Unable to get CMC historical price for %s on %s: %s', coin, day, e)
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
        'X-CMC_PRO_API_KEY': CMC_API_KEY,
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
    #payout = get_payout(FeePayout.objects.exclude(notes='aggroed').values('created_at').order_by('-created_at').first()['created_at'], sort=False)
    payout = get_payout('1970-01-01', sort=False, by_native=False)
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
        if not pr['native'] and get_native_coin(coin) in payout_table:
            payout_table[get_native_coin(coin)]['total_fees'] += pr['fee_amount']
    privex_share = Decimal(0.25)
    he_share = Decimal(0.75)
    for coin, pr in payout_table.items():
        if pr['native']:
            pr['value'] = pr['total_fees'] * pr['price']
            pr['privex_cut'] = pr['total_fees'] * privex_share
            #try:
                #swap_coin = Coin.objects.get(symbol_id='SWAP.' + coin)
                #try:
                #    balance = Decimal(get_manager(swap_coin.symbol_id).balance(swap_coin.our_account))
                #except KeyError:
                #    balance = Decimal(0)
            #    pr['he_cut'] = pr['total_fees'] * he_share
            #    if pr['he_cut'] == 0:
            #        del pr['he_cut']
            #except Coin.DoesNotExist:
            #    pass
        else:
            if get_native_coin(coin) not in payout_table:
                continue
            pr['value'] = ''
            try:
                swap_coin = Coin.objects.get(symbol_id=coin)
                try:
                    pr['he_balance'] = Decimal(get_manager(swap_coin.symbol_id).balance(swap_coin.our_account))
                except KeyError:
                    pr['he_balance'] = Decimal(0)
                pr['he_cut'] = payout_table[get_native_coin(coin)]['total_fees'] * he_share
            except Coin.DoesNotExist:
                pass
            pr['total_fees'] = ''
    coins = ['LTC', 'BTC', 'HBD', 'DOGE', 'STEEM', 'BLURT', 'BCH']
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
        context['payout2'] = get_payout(FeePayout.objects.exclude(notes__in=['aggroed', 'hive engine (surplus)']).order_by('-created_at')[0].created_at)
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
    list_display = ('coin', 'amount', 'notes', 'paid', 'created_at')
    list_filter = ('coin', 'created_at', 'paid')
    search_fields = ('notes', 'coin__symbol')
    ordering = ('-created_at', '-updated_at')
    actions = [confirm_send_payout, export_fee_payments_csv]
