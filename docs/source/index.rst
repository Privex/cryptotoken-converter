.. CryptoToken Converter documentation master file, created by
   sphinx-quickstart on Thu Mar 21 03:24:42 2019.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Privex's CryptoToken Converter Documentation
=================================================

This documentation is for CryptoToken Converter, an open source project developed
by `Privex Inc.`_ for simple, anonymous conversion between two cryptocurrencies / tokens.

You can find the full source code for the project on our Github_

It allows for both uni-directional and bi-directional conversions between user specified
coin pairs, whether that's BTC->LTC, or LTC->LTCP (Litecoin to Pegged Litecoin token).

Using CryptoToken Converter, you can easily operate services such as crypto <-> token gateways,
as well as token <-> token and crypto <-> crypto.

Out of the box, CryptoToken Converter comes with two :ref:`Coin Handlers`:

* :ref:`Bitcoind Handler`
   Handles deposits/sending for coins which have a fork of
   `bitcoind` without dramatic JSONRPC API changes (e.g. Litecoin, Dogecoin).
* :ref:`SteemEngine Handler`
   Handles deposits/issuing/sending for tokens that exist on the `Steem Engine`_
   platform - a side-chain of the Steem_ blockchain.

Every "coin pair" has an exchange rate set in the database, which can be
either statically set for pegged tokens, or dynamically updated for conversions
between two different cryptos/tokens.

.. _Privex Inc.: https://www.privex.io
.. _Github: https://github.org/Privex/cryptotoken-converter
.. _Steem: https://steem.com
.. _Steem Engine: https://steem-engine.com