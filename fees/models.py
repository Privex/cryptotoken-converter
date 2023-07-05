import logging

from django.db import models

from payments.models import Coin, MAX_STORED_DIGITS, MAX_STORED_DP

log = logging.getLogger(__name__)


class FeePayout(models.Model):
    coin = models.ForeignKey(Coin, on_delete=models.DO_NOTHING)
    amount = models.DecimalField(max_digits=MAX_STORED_DIGITS, decimal_places=MAX_STORED_DP)
    notes = models.CharField(max_length=1000, default='')
    paid = models.BooleanField(default=False)

    created_at = models.DateTimeField('Creation Time', auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField('Last Update', auto_now=True)

