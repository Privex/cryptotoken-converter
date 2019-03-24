"""
steemengine URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/

Copyright::

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
# from adminplus.sites import AdminSitePlus
from django.contrib import admin
from django.urls import path, include, re_path
from rest_framework import routers

from payments.views import IndexView, DepositAPI, CoinAPI, ConvertAPI, CoinPairAPI, ConversionAPI, api_root
from payments.admin import ctadmin


router = routers.SimpleRouter()

router.register(r'deposits', DepositAPI)
router.register(r'coins', CoinAPI)
router.register(r'pairs', CoinPairAPI)
router.register(r'conversions', ConversionAPI)

admin.site = ctadmin
admin.sites.site = admin.site
admin.autodiscover()

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/convert/', ConvertAPI.as_view(), name='start_convert'),
    re_path(r'^api/$', api_root),
    path('api/', include(router.urls)),
    path('', IndexView.as_view(), name='index')
]


# urlpatterns += router.urls
