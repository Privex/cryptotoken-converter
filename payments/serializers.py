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
            'coin_symbol',
            'vout',
            'status',
            'tx_timestamp',
            'address',
            'from_account',
            'to_account',
            'amount',
            'memo',
            'created_at',
            'conversion',
            'processed_at',
            'convert_to'
        )


class CoinPairSerializer(serializers.HyperlinkedModelSerializer):
    from_coin_symbol = serializers.ReadOnlyField()
    to_coin_symbol = serializers.ReadOnlyField()

    class Meta:
        model = CoinPair
        fields = (
            'id',
            'from_coin',
            'from_coin_symbol',
            'to_coin',
            'to_coin_symbol',
            'exchange_rate',
            '__str__'
        )


class ConversionSerializer(serializers.HyperlinkedModelSerializer):
    from_coin_symbol = serializers.ReadOnlyField()
    to_coin_symbol = serializers.ReadOnlyField()

    class Meta:
        model = Conversion
        exclude = ()
