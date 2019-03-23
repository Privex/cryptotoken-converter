from rest_framework import serializers

from payments.models import Deposit, Coin, CoinPair, Conversion


class CoinSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Coin
        fields = ('symbol', 'display_name', 'our_account', 'can_issue')


class DepositSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Deposit
        fields = (
            'id',
            'txid',
            'coin',
            'vout',
            'status',
            'tx_timestamp',
            'address',
            'from_account',
            'to_account',
            'amount',
            'memo',
            'processed_at',
            'convert_to'
        )


class CoinPairSerializer(serializers.ModelSerializer):

    class Meta:
        model = CoinPair
        fields = ('id', 'from_coin', 'to_coin', 'exchange_rate', '__str__')


class ConversionSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Conversion
        exclude = ()
