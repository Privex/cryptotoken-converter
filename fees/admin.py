import logging

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models.aggregates import Sum
from django.shortcuts import redirect
from django.views.generic.base import TemplateView

from fees.models import FeePayout
from payments.models import Conversion

log = logging.getLogger(__name__)


def get_payout():
    payouts = {fp['coin']: fp['fee'] for fp in FeePayout.objects.values('coin').annotate(fee=Sum('amount'))}
    fees = {c['from_coin_id']: c['fee'] for c in Conversion.objects.values('from_coin_id').annotate(fee=Sum('ex_fee'))}
    return [dict(coin_id=coin, amount=fees[coin] - payouts.get(coin, 0)) for coin in fees.keys()]


class FeePayoutAdmin(admin.ModelAdmin):
    list_display = ('coin', 'amount')
    list_filter = ('coin',)
    ordering = ('created_at', 'updated_at')


class FeePayoutView(TemplateView):
    template_name = 'admin/fee_payout.html'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_context_data(self, **kwargs):
        context = super(FeePayoutView, self).get_context_data(**kwargs)
        context['payout'] = get_payout()
        return context

    def get(self, request, *args, **kwargs):
        r = self.request
        u = r.user
        if not u.is_authenticated or not u.is_superuser:
            raise PermissionDenied
        return super(FeePayoutView, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        FeePayout.objects.bulk_create([FeePayout(**p) for p in get_payout()])
        return redirect('admin:fee_payout')
