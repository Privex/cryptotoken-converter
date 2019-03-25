import logging
from rest_framework import viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.views import APIView

from payments.coin_handlers import get_manager
from payments.models import Deposit, Coin, CoinPair, AddressAccountMap, Conversion
from payments.serializers import DepositSerializer, CoinSerializer, CoinPairSerializer, ConversionSerializer

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

# Create your views here.
from django.views.generic import TemplateView

log = logging.getLogger(__name__)


class IndexView(TemplateView):
    template_name = 'base.html'


@api_view(['GET'])
def api_root(request, format=None):
    return Response({
        'coins': reverse('coin-list', request=request, format=format),
        'pairs': reverse('coinpair-list', request=request, format=format),
        'deposits': reverse('deposit-list', request=request, format=format),
        'conversions': reverse('conversion-list', request=request, format=format),
        'start_conversion': reverse('start_convert', request=request, format=format)
    })


class CoinAPI(viewsets.ReadOnlyModelViewSet):
    queryset = Coin.objects.filter(enabled=True)
    serializer_class = CoinSerializer


class DepositAPI(viewsets.ReadOnlyModelViewSet):
    queryset = Deposit.objects.all()
    serializer_class = DepositSerializer
    filterset_fields = ('address', 'from_account', 'to_account', 'txid', 'memo')


class CoinPairAPI(viewsets.ReadOnlyModelViewSet):
    queryset = CoinPair.objects.filter(from_coin__enabled=True, to_coin__enabled=True)
    serializer_class = CoinPairSerializer
    filterset_fields = ('from_coin', 'to_coin')


class ConversionAPI(viewsets.ReadOnlyModelViewSet):
    queryset = Conversion.objects.all()
    serializer_class = ConversionSerializer
    filterset_fields = ('from_coin', 'to_coin')


def r_err(msg, status=500):
    return Response(dict(error=True, message=msg), status=status)


class DRFNoCSRF(SessionAuthentication):

    def enforce_csrf(self, request):
        return  # disable csrf check


class ConvertAPI(DRFNoCSRF, APIView):
    authentication_classes = (DRFNoCSRF,)

    def post(self, request: Request):
        try:
            return self._post(request)
        except:
            log.exception("An unhandled exception occurred while handling ConvertAPI.post")
            return r_err('An unknown error has occurred... please contact support', 500)

    def _post(self, request: Request):
        d = request.data
        # If they didn't specify one of these, it will simply raise an exception for us to handle below.
        try:
            from_coin = str(d['from_coin']).upper()
            to_coin = str(d['to_coin']).upper()
            destination = str(d['destination'])
        except (AttributeError, KeyError):
            return r_err("You must specify 'from_coin', 'to_coin', and 'destination'", 400)
        # Check if the coin pair specified actually exists. If it doesn't, it'll throw a DoesNotExist.
        try:
            c = CoinPair.objects.get(from_coin__symbol=from_coin, to_coin__symbol=to_coin)
        except CoinPair.DoesNotExist:
            return r_err("There is no such coin pair {} -> {}".format(d['from_coin'], d['to_coin']), 404)
        # Grab the x(BaseManager) instances for the from/to coin, so we can do some validation + generate deposit info
        m = get_manager(from_coin)
        m_to = get_manager(to_coin)

        # To save users from sending their coins into the abyss, make sure their destination address/account is
        # actually valid / exists.
        if not m_to.address_valid(destination):
            return r_err("The destination {} address/account '{}' is not valid".format(to_coin, destination), 400)
        # Ask the Coin Handler for their from_coin how to handle deposits for that coin
        dep_type, dep_addr = m.get_deposit()
        # Data to return in the 'result' key of our response.
        res = dict(
            ex_rate=c.exchange_rate, destination=destination,
            pair=str(c)
        )
        if dep_type == 'account':
            # If the coin handler uses an account system, that means we just give them our account to deposit into,
            # and generate a memo with destination coin/address details.
            res['memo'] = "{} {}".format(to_coin, destination)
            res['account'] = dep_addr
        else:
            # If it's not account based, assume it's address based.
            dep_data = dict(deposit_coin=c.from_coin, deposit_address=dep_addr,
                            destination_coin=c.to_coin, destination_address=destination)
            res['address'] = dep_addr
            # Store the address so we can map it to their destination coin when they deposit to it.
            AddressAccountMap(**dep_data).save()

        return Response(res)
