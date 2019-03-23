.. _REST API Documentation:

REST API Documentation
======================

CryptoToken Converter exposes a REST API under the URL ``/api`` to allow any application
to easily interact with the system.

It uses `Django REST Framework`_ which automatically generates a lot of the code running
behind the API endpoints.

.. _Django REST Framework: https://www.django-rest-framework.org

Endpoints
---------

For **GET** requests, any request parameters must either be sent as either:

    **Standard GET parameters** -  e.g. ``/api/deposits/?from_address=someguy123``

    **Directly in the URL** - e.g. ``/api/coins/LTC``

For **POST** requests, you may send your request data/params as a normal URL encoded form,
or you may choose to send it as JSON.

    **application/json - JSON Encoded Body**

    .. code-block:: json

        {
            "my_param": "somevalue",
            "other.param": "other value"
        }


    **application/x-www-form-urlencoded - Standard POST body**

    ::

        my_param=somevalue&other.param=other%20value


/api/convert/
---------------

Starts the conversion process between two coins.

Returns the deposit details for you to send the coins to.

**Methods:** POST (URL Encoded Form, or JSON)

**POST Parameters:**

+-------------------------+-------------------+-----------------------------------------------------+
| Parameter               | Type              | Description                                         |
+=========================+===================+=====================================================+
| from_coin               | String            | Symbol of the coin to convert from                  |
+-------------------------+-------------------+-----------------------------------------------------+
| to_coin                 | String            | Symbol of the destination coin                      |
+-------------------------+-------------------+-----------------------------------------------------+
| destination             | String            | The address or account on ``to_coin`` for receiving |
|                         |                   | your converted coins                                |
+-------------------------+-------------------+-----------------------------------------------------+

All parameters are required.

**Errors:**

    If the JSON response ``error`` key is present and set to ``true``, the error message will be placed in ``message``,
    and a non-200 status code will be returned, related to the error reason.

    Potential errors and their status codes:

    - "An unknown error has occurred... please contact support", 500
    - "You must specify 'from_coin', 'to_coin', and 'destination'", 400
    - "There is no such coin pair {} -> {}", 404
    - "The destination {} address/account '{}' is not valid", 400

    Example error response::

        POST /api/convert/

        HTTP 400 Bad Request
        Allow: POST, OPTIONS
        Content-Type: application/json
        Vary: Accept

        {
            "error": true,
            "message": "You must specify 'from_coin', 'to_coin', and 'destination'"
        }

**Return Data:**

    All successful requests will include ``ex_rate`` (the amount of ``to_coin`` per ``from_coin``), ``pair`` (details
    about the coin pair that you have chosen), and ``destination`` (where the ``from_coin`` will be sent to).

    Depending on whether the ``from_coin`` is an **address based** coin, or an **account/memo based** coin, the
    actual deposit details will be returned differently. Address based coins will return ``address``, while account
    based coins will return ``account`` and ``memo``.

    Below are two examples to help explain this. ``SGTK`` is "Sometoken", a SteemEngine token, meaning it's account+memo
    based. ``LTC`` is Litecoin, a classic address based cryptocurrency.

    **Example 1 (address based -> account based)**::

      POST /api/convert/
      from_coin=LTC&to_coin=SGTK&destination=someguy123

      HTTP 200 OK
      Content-Type: application/json

      {
          "ex_rate": 100000.0,
          "destination": "someguy123",
          "pair": "LTC -> SGTK (100000.0000 SGTK per LTC)",
          "address": "MJL1E5oSqFLpdL9BswKmYonxU1Cq1WKWGL"
      }


    **Example 2 (account based -> address based)**::

      POST /api/convert/
      from_coin=SGTK&to_coin=LTC&destination=MVYBriQcasb6zvtGjPfLKbbWcRoKWh4sAf

      HTTP 200 OK
      Content-Type: application/json
      {
          "ex_rate": 0.01,
          "destination": "MVYBriQcasb6zvtGjPfLKbbWcRoKWh4sAf",
          "pair": "SGTK -> LTC (0.0100 LTC per SGTK)",
          "memo": "LTC MVYBriQcasb6zvtGjPfLKbbWcRoKWh4sAf",
          "account": "someguy123"
      }

/api/deposits/
---------------

``/api/deposits/``
    Returns all deposit attempts received by the system.
    Can be filtered using the **GET Parameters** listed below.

``/api/deposits/<id>``
    Returns a single deposit attempt by it's ID

**Methods:** GET

**GET Parameters:**

These parameters can be used with the plain ``/api/deposits/`` URL, to filter deposits based on various columns.

Note: Results from ``/api/deposits/`` will always be returned as a list, even if there's only one.

+-------------------------+-------------------+-----------------------------------------------------+
| Parameter               | Type              | Description                                         |
+=========================+===================+=====================================================+
| address                 | String            | Return deposits that were sent to this address      |
|                         |                   | (only for address-based coins)                      |
+-------------------------+-------------------+-----------------------------------------------------+
| txid                    | String            | Return deposits with a matching transaction ID      |
+-------------------------+-------------------+-----------------------------------------------------+
| from_account            | String            | Return deposits that were sent from this account    |
|                         |                   | (only for account-based coins)                      |
+-------------------------+-------------------+-----------------------------------------------------+
| to_account              | String            | Return deposits that were sent to this account      |
|                         |                   | (only for account-based coins)                      |
+-------------------------+-------------------+-----------------------------------------------------+
| memo                    | String            | Return deposits that were sent using this memo      |
|                         |                   | (normally only for account-based coins)             |
+-------------------------+-------------------+-----------------------------------------------------+

**Return Data:**

    **Example 1 (Plain GET request)**::

        GET /api/deposits/

        HTTP 200 OK
        Content-Type: application/json

        [
            {
                "id": 4,
                "txid": "635dd656b3bd8c61699e6066c9b3c6e74696e195",
                "coin": "http://127.0.0.1:8000/api/coins/SGTK/",
                "vout": 0,
                "status": "conv",
                "tx_timestamp": "2019-03-20T03:46:30Z",
                "address": null,
                "from_account": "privex",
                "to_account": "someguy123",
                "amount": "1.00000000000000000000",
                "memo": "LTC LKjpPtgMbcFgbJJYwzfe1ZtR8x4bbs2V3o",
                "processed_at": "2019-03-20T04:31:30.643406Z",
                "convert_to": "http://127.0.0.1:8000/api/coins/LTC/"
            },
            {
                "id": 5,
                "txid": "b881d1ae8cf280184960c9c2d74bc1bd230f18f5adcd7fe695239dbf46b06c45",
                "coin": "http://127.0.0.1:8000/api/coins/LTC/",
                "vout": 0,
                "status": "conv",
                "tx_timestamp": "2019-03-20T01:34:20Z",
                "address": "MFht1FmYhsRaSChGdqomxQpjtGtsjFHDQX",
                "from_account": null,
                "to_account": null,
                "amount": "0.10000000000000000000",
                "memo": null,
                "processed_at": "2019-03-20T04:46:53.602857Z",
                "convert_to": "http://127.0.0.1:8000/api/coins/SGTK/"
            }
        ]

    **Example 2 (Filtering results)**::

        GET /api/deposits/?txid=635dd656b3bd8c61699e6066c9b3c6e74696e195

        HTTP 200 OK
        Content-Type: application/json

        [
            {
                "id": 4,
                "txid": "635dd656b3bd8c61699e6066c9b3c6e74696e195",
                "coin": "http://127.0.0.1:8000/api/coins/SGTK/",
                "vout": 0,
                "status": "conv",
                "tx_timestamp": "2019-03-20T03:46:30Z",
                "address": null,
                "from_account": "privex",
                "to_account": "someguy123",
                "amount": "1.00000000000000000000",
                "memo": "LTC LKjpPtgMbcFgbJJYwzfe1ZtR8x4bbs2V3o",
                "processed_at": "2019-03-20T04:31:30.643406Z",
                "convert_to": "http://127.0.0.1:8000/api/coins/LTC/"
            }
        ]

    **Example 3 (ID Lookup)**::

        GET /api/deposits/4/

        HTTP 200 OK
        Content-Type: application/json

        {
            "id": 4,
            "txid": "635dd656b3bd8c61699e6066c9b3c6e74696e195",
            "coin": "http://127.0.0.1:8000/api/coins/SGTK/",
            "vout": 0,
            "status": "conv",
            "tx_timestamp": "2019-03-20T03:46:30Z",
            "address": null,
            "from_account": "privex",
            "to_account": "someguy123",
            "amount": "1.00000000000000000000",
            "memo": "LTC LKjpPtgMbcFgbJJYwzfe1ZtR8x4bbs2V3o",
            "processed_at": "2019-03-20T04:31:30.643406Z",
            "convert_to": "http://127.0.0.1:8000/api/coins/LTC/"
        }

/api/conversions/
------------------

``/api/conversions/``
    Returns all successful conversions sent by the system.
    Can be filtered using the **GET Parameters** listed below.

``/api/conversions/<id>``
    Returns a single conversion by it's ID

**Methods:** GET

**GET Parameters:**

These parameters can be used with the plain ``/api/conversions/`` URL, to filter conversions based on various columns.

Note: Results from ``/api/conversions/`` will always be returned as a list, even if there's only one.

+-------------------------+-------------------+-----------------------------------------------------+
| Parameter               | Type              | Description                                         |
+=========================+===================+=====================================================+
| to_address              | String            | Return conversions that were sent to this address   |
|                         |                   | or account (it's used for both)                     |
+-------------------------+-------------------+-----------------------------------------------------+
| to_txid                 | String            | Return conversions with this outgoing TXID          |
+-------------------------+-------------------+-----------------------------------------------------+
| to_coin                 | String            | Return conversions into this coin symbol            |
+-------------------------+-------------------+-----------------------------------------------------+
| from_coin               | String            | Return conversions from this coin symbol            |
+-------------------------+-------------------+-----------------------------------------------------+
| from_address            | String            | Return conversions that were sent from this address |
|                         |                   | or account (it's used for both)                     |
+-------------------------+-------------------+-----------------------------------------------------+

**Return Data:**

    Note: The ``to_amount`` is the final amount that the user should have received AFTER ``ex_fee`` and ``tx_fee``
    were removed.

    **Example 1 (Plain GET request)**::

        GET /api/conversions/

        HTTP 200 OK
        Content-Type: application/json
        [
            {
                "url": "http://127.0.0.1:8000/api/conversions/6/",
                "from_address": "LKjpPtgMbcFgbJJYwzfe1ZtR8x4bbs2V3o",
                "to_address": "LKjpPtgMbcFgbJJYwzfe1ZtR8x4bbs2V3o",
                "to_memo": "Token Conversion from SGTK account privex",
                "to_amount": "0.00883200000000000000",
                "to_txid": "e4a5cb3ccc5524e20a39b1a076cef16a85efc68bf929e7a3ec4a834c30711e55",
                "tx_fee": "0.00016800000000000000",
                "ex_fee": "0.00100000000000000000",
                "created_at": "2019-03-21T10:14:20.021360Z",
                "updated_at": "2019-03-21T10:14:20.021373Z",
                "deposit": "http://127.0.0.1:8000/api/deposits/10/",
                "from_coin": "http://127.0.0.1:8000/api/coins/SGTK/",
                "to_coin": "http://127.0.0.1:8000/api/coins/LTC/"
            },
            {
                "url": "http://127.0.0.1:8000/api/conversions/7/",
                "from_address": "someguy123",
                "to_address": "privex",
                "to_memo": "Token Conversion via LTC deposit address MTcPHSipXBzwhTWT8wXMtNf6vwAxovjpx9",
                "to_amount": "900.00000000000000000000",
                "to_txid": "55c30e43088c8aa6d7a74da1e29d3843cd7157e7",
                "tx_fee": "0.00000000000000000000",
                "ex_fee": "100.00000000000000000000",
                "created_at": "2019-03-21T10:15:47.071323Z",
                "updated_at": "2019-03-21T10:15:47.071340Z",
                "deposit": "http://127.0.0.1:8000/api/deposits/9/",
                "from_coin": "http://127.0.0.1:8000/api/coins/LTC/",
                "to_coin": "http://127.0.0.1:8000/api/coins/SGTK/"
            }
        ]

    **Example 2 (Filtering results)**::

        GET /api/conversions/?from_coin=SGTK&to_coin=LTC

        HTTP 200 OK
        Content-Type: application/json
        [
            {
                "url": "http://127.0.0.1:8000/api/conversions/6/",
                "from_address": "LKjpPtgMbcFgbJJYwzfe1ZtR8x4bbs2V3o",
                "to_address": "LKjpPtgMbcFgbJJYwzfe1ZtR8x4bbs2V3o",
                "to_memo": "Token Conversion from SGTK account privex",
                "to_amount": "0.00883200000000000000",
                "to_txid": "e4a5cb3ccc5524e20a39b1a076cef16a85efc68bf929e7a3ec4a834c30711e55",
                "tx_fee": "0.00016800000000000000",
                "ex_fee": "0.00100000000000000000",
                "created_at": "2019-03-21T10:14:20.021360Z",
                "updated_at": "2019-03-21T10:14:20.021373Z",
                "deposit": "http://127.0.0.1:8000/api/deposits/10/",
                "from_coin": "http://127.0.0.1:8000/api/coins/SGTK/",
                "to_coin": "http://127.0.0.1:8000/api/coins/LTC/"
            },
            {
                "url": "http://127.0.0.1:8000/api/conversions/5/",
                "from_address": "LKjpPtgMbcFgbJJYwzfe1ZtR8x4bbs2V3o",
                "to_address": "LKjpPtgMbcFgbJJYwzfe1ZtR8x4bbs2V3o",
                "to_memo": "Token Conversion from SGTK account privex",
                "to_amount": "0.00433200000000000000",
                "to_txid": null,
                "tx_fee": "0.00016800000000000000",
                "ex_fee": "0.00050000000000000000",
                "created_at": "2019-03-20T04:56:53.859675Z",
                "updated_at": "2019-03-20T04:56:53.859691Z",
                "deposit": "http://127.0.0.1:8000/api/deposits/7/",
                "from_coin": "http://127.0.0.1:8000/api/coins/SGTK/",
                "to_coin": "http://127.0.0.1:8000/api/coins/LTC/"
            }
        ]

    **Example 3 (ID Lookup)**::

        GET /api/conversions/5/

        HTTP 200 OK
        Content-Type: application/json

        {
            "url": "http://127.0.0.1:8000/api/conversions/5/",
            "from_address": "LKjpPtgMbcFgbJJYwzfe1ZtR8x4bbs2V3o",
            "to_address": "LKjpPtgMbcFgbJJYwzfe1ZtR8x4bbs2V3o",
            "to_memo": "Token Conversion from SGTK account privex",
            "to_amount": "0.00433200000000000000",
            "to_txid": null,
            "tx_fee": "0.00016800000000000000",
            "ex_fee": "0.00050000000000000000",
            "created_at": "2019-03-20T04:56:53.859675Z",
            "updated_at": "2019-03-20T04:56:53.859691Z",
            "deposit": "http://127.0.0.1:8000/api/deposits/7/",
            "from_coin": "http://127.0.0.1:8000/api/coins/SGTK/",
            "to_coin": "http://127.0.0.1:8000/api/coins/LTC/"
        }

/api/pairs/
------------

``/api/pairs/``
    Returns all coin pairs supported by the system
    Can be filtered using the **GET Parameters** listed below.

``/api/pairs/<id>``
    Returns a single coin pair by it's ID

**Methods:** GET

**GET Parameters:**

These parameters can be used with the plain ``/api/pairs/`` URL, to filter coin pairs based on from/to symbol.

Note: Results from ``/api/pairs/`` will always be returned as a list, even if there's only one.

+-------------------------+-------------------+-----------------------------------------------------+
| Parameter               | Type              | Description                                         |
+=========================+===================+=====================================================+
| to_coin                 | String            | Return pairs with this destination coin symbol      |
+-------------------------+-------------------+-----------------------------------------------------+
| from_coin               | String            | Return pairs with this deposit coin symbol          |
+-------------------------+-------------------+-----------------------------------------------------+

**Example 1 (Plain GET request)**::

    GET /api/pairs/

    HTTP 200 OK
    Content-Type: application/json

    [
        {
            "id": 1,
            "from_coin": "LTC",
            "to_coin": "SGTK",
            "exchange_rate": "100000.00000000000000000000",
            "__str__": "LTC -> SGTK (100000.0000 SGTK per LTC)"
        },
        {
            "id": 2,
            "from_coin": "SGTK",
            "to_coin": "LTC",
            "exchange_rate": "0.01000000000000000000",
            "__str__": "SGTK -> LTC (0.0100 LTC per SGTK)"
        }
    ]

**Example 2 (Filtering results)**::

    GET /api/pairs/?from_coin=LTC

    HTTP 200 OK
    Content-Type: application/json

    [
        {
            "id": 1,
            "from_coin": "LTC",
            "to_coin": "SGTK",
            "exchange_rate": "100000.00000000000000000000",
            "__str__": "LTC -> SGTK (100000.0000 SGTK per LTC)"
        }
    ]



**Example 3 (ID Lookup)**::

    GET /api/pairs/1/

    HTTP 200 OK
    Content-Type: application/json

    {
        "id": 1,
        "from_coin": "LTC",
        "to_coin": "SGTK",
        "exchange_rate": "100000.00000000000000000000",
        "__str__": "LTC -> SGTK (100000.0000 SGTK per LTC)"
    }

