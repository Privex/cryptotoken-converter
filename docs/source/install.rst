Installation and configuration
==============================

.. Attention:: This guide is aimed at Ubuntu Bionic 18.04 - if you're not running Ubuntu 18.04, some parts of
               the guide may not apply to you, or simply won't work.

.. Tip::       If you don't have any machines running Ubuntu 18.04, you can grab a `dedicated or virtual server`_
               pre-installed with it from Privex_ - we're the ones who wrote this software! :)

.. _Privex: https://www.privex.io
.. _dedicated or virtual server: https://www.privex.io

Requirements and Dependencies
-------------------------------

**Core Dependencies**

- Python 3.7+ (may or may not work on older versions)
- PostgreSQL or MySQL for the database
- Nginx for the production web server
- Linux or macOS (OSX) is recommended (may work on Windows, however we refuse to actively support it)

**Additional Requirements**

- If you plan to use the :ref:`Bitcoind Handler` you'll need one or more coin daemons such as ``bitcoind`` ,
  ``litecoind`` or ``dogecoind`` running in server mode, with an rpcuser and rpcpassword configured.
- If you plan to use the :ref:`SteemEngine Handler` you'll need a `Steem account`_ - for best operation it's
  recommended that you use `Steem Engine`_ tokens that you've created (can issue them), and you must have
  the **active private key** of the token owner account.

**Knowledge**

- You should have basic knowledge of navigating a Linux/Unix system, including running basic commands
- It may help if you have at least a basic understanding of the Python programming language
- If you plan to contribute to the project, or make modifications, you should read the documentation for
  the `Django Framework`_, and the third-party add-on `Django REST Framework`_

.. _Steem account: https://anon.steem.network/
.. _Steem Engine: https://steem-engine.com
.. _Django Framework: https://docs.djangoproject.com/en/2.1/
.. _Django REST Framework: https://www.django-rest-framework.org/

Install Core Dependencies
-------------------------

For this guide, we'll be using PostgreSQL, but you're free to use MySQL if you're more comfortable with it.

Using your system package manager, install Python 3.7, Postgres server, nginx, and git

.. code-block:: bash

    sudo apt update
    # Install Python 3.7, Nginx, and Git
    sudo apt install -y python3.7 python3.7-dev python3.7-venv nginx git

    # (If you want to use PostgreSQL)
    # The `postgresql` package will install the latest Postgres client and server, we also want libpq-dev,
    # which is the postgres client dev headers, sometimes needed for Python postgres libraries
    sudo apt install -y postgresql libpq-dev

    # (If you want to use MariaDB / MySQL)
    # Install MariaDB (cross-compatible with MySQL) and the development headers to avoid issues with the Python
    # MySQL library
    sudo apt install -y mariadb-server libmariadbclient-dev libmariadb-dev

.. Tip::    The below step for setting your default ``python3`` is optional, but it may help prevent issues when
            python files refer to ``python3`` and not ``python3.7``

To avoid the issue of ``python3`` referring to an older version of Python 3, you should run the following
commands to set up Python 3.7 as the default. On Ubuntu 18.04, Python 3.6 is the default used for ``python3``.

.. code-block:: bash

    # Make sure both Python 3.6 (Ubuntu 18.04 default), and 3.7 are registered with update-alternatives
    sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.6 1
    sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.7 2
    # Set `python3.7` as the default version to use when `python3` is ran
    sudo update-alternatives --set python3 /usr/bin/python3.7


To check if the above worked, you should see ``3.7.x`` when running ``python3 -V`` like below:

.. code-block:: bash

    user@host ~ $ python3 -V
    Python 3.7.1

Create Database and DB user
----------------------------

For Postgres, this is very easy.

Simply run the below commands to create a user, a database, and make the user the owner of the DB.

.. code-block:: bash

    # Log in as the postgres user
    root@host # su - postgres

    # Create a user, you'll be prompted for the password
    # S = not a superuser, D = cannot create databases, R = cannot create roles
    # l = can login, P = prompt for user's new password
    $ createuser -SDRl -P steemengine
        Enter password for new role:
        Enter it again:

    # Create the database steemengine_pay with the new user as the owner

    $ createdb -O steemengine steemengine_pay

    # If you've already created the DB, use psql to manually grant permissions to the user

    $ psql
        psql (10.6 (Ubuntu 10.6-0ubuntu0.18.04.1))
        Type "help" for help.

        postgres=# GRANT ALL ON DATABASE steemengine TO steemengine_pay;


The above commands create a postgres user called ``steemengine`` and a database called ``steemengine_pay`` .

Feel free to adjust the username and database name to your liking.

Download and install the project
---------------------------------

.. Tip:: If you're running this in production, for security you should create a limited account, and install the
         project using that account.

Clone the repo, and enter the directory.

.. code-block:: bash

    git clone https://github.com/privex/cryptotoken-converter
    cd cryptotoken-converter

Create and activate a **python virtual environment** to avoid conflicts with any packages installed system-wide,
or any upgrades to the python version.

.. code-block:: bash

    # Create the virtual environment in the folder `venv`
    python3.7 -m venv venv
    # Activate the virtual environment.
    source venv/bin/activate

You must make sure to activate the virtualenv before you run any python files, or install any python packages.

While the virtualenv is activated, you'll see the text ``(venv)`` on the side of your shell, like so::

    (venv) user@host ~/cryptotoken-converter $

Now that the virtualenv is created and activated, we can install the python packages required to run this project.

.. code-block:: bash

    # pip3 is the package manager for Python 3, this command will install the packages listed in `requirements.txt`
    pip3 install -r requirements.txt

Beem Wallet (if using Steem)
----------------------------

If you're using a coin handler that uses the **Steem network**, such as :ref:`SteemEngine Handler`, then you
must create a Beem wallet, and add the **active private key** for each Steem account you intend to send/issue from.

.. code-block:: bash

    # Create a new Beem wallet, make sure to remember your wallet password, you'll need it later.
    beempy createwallet
    # Import the Private Active Key for each Steem account you plan to send/issue from.
    beempy addkey


Basic Configuration
---------------------

The first step of configuration is creating a ``.env`` file, this will contain various configuration details
needed to run the project.

.. code-block:: bash

    # Creates a file called `.env` if it doesn't already exist
    touch .env
    # Ensures that `.env` can only be read/written to by your user.
    chmod 700 .env

Open up ``.env`` in your favourite text editor (such as ``vim`` or ``nano`` ).

Paste the following example config::

    DB_USER=steemengine_pay
    DB_PASS=MySuperSecretPassword
    DB_NAME=steemengine
    DEBUG=false
    SECRET_KEY=VeryLongRandomStringUsedToProtectYourUserSessions
    UNLOCK=

Some of the above options can simply be left out if they're just the default, but it's best to specify them anyway,
to avoid the application breaking due to changes to the default values.

Now we'll explain what the above options do, as well as some extras.

**Basic Config**

``SECRET_KEY`` - **Required**

    A long (recommended 40+ chars) random string of uppercase letters, lowercase letters,
    and numbers. It's used for various Django functionality, including encryption of your user sessions/cookies.

``DEBUG`` - Optional

    If set to ``True`` Django will output detailed error pages, automatically re-load the app
    when python files are modified, among other helpful development features. If not specified, it defaults
    to ``False``.

    **This should always be set to FALSE in production, otherwise the error pages WILL leak a lot of**
    **information, including sensitive details such as passwords or API keys.**


``EX_FEE`` - Optional

    This option sets the exchange fee, as a percentage. For example `1` would mean a 1% fee is
    taken from each exchange from crypto->token and token->crypto.

    You may also use decimal numbers, such as `0.5` for 0.5%, or to disable exchange fees, simply set it to `0`
    or remove the line entirely, **as the default is no fee**.

``COIN_HANDLERS`` - Optional.

    If you're using any third party :ref:`Coin Handlers` or you want to disable some
    of the default ones, this is a list of comma separated Coin Handler folder names.

    **Default:** ``SteemEngine,Bitcoin``


**Steem Configuration**

If you plan to use :ref:`SteemEngine Handler` then you may want to configure these as needed.

``STEEM_RPC_NODES`` - Optional

    If you want to override the Steem RPC node(s) used for functions such as signing
    the custom_json transactions from the token issuing account, you can specify them as a comma separated list.

    They will be used in the order they are specified.

    **Default:** Automatically use best node determined by Beem

    **Example:** ``STEEM_RPC_NODES=https://steemd.privex.io,https://api.steemit.com``

``UNLOCK`` - **Required if using Steem**

    The wallet password for Beem. This must be specified to allow Steem transactions to be automatically signed.
    See the section `Beem Wallet (if using Steem)`_ to create a wallet.


**Database Configuration**

- ``DB_BACKEND`` - What type of DB are you using? ``mysql`` or ``postgresql`` Default: ``postgresql``
- ``DB_HOST`` - What hostname/ip is the DB on? Default: ``localhost``
- ``DB_NAME`` - What is the name of the database to use? Default: ``steemengine_pay``
- ``DB_USER`` - What username to connect with? Default: ``steemengine``
- ``DB_PASS`` - What password to connect with? Default: no password


Final Setup
-----------

The app is almost ready to go! Just a few last things.

To create the database structure (tables, relations etc.), you'll need to run the Django migrations

.. code-block:: bash

    ./manage.py migrate

You'll also want to create an admin account (superuser)

.. code-block:: bash

    ./manage.py createsuperuser

Now, start the Django server

.. code-block:: bash

    ./manage.py runserver

You should now be able to go to http://127.0.0.1:8000/admin/ in your browser and access the Django admin.

Login using the superuser account you've created.

Using the admin panel, create at least two Coin's (:class:`payments.models.Coin`), and at least
one Coin Pair (:class:`payments.models.CoinPair`).

Make sure to set each Coin's "Coin Type" correctly, so that Coin Handlers will detect them (use the types
"SteemEngine Token", and "Bitcoind Compatible"). You may have to refresh the "Add Coin" page if some of the types
don't show up.

After adding the coins, you should now be able to open one of the API pages in your browser, such as this one:
http://127.0.0.1:8000/api/coins/

If you can see your added coins on that page, everything should be working! :)

Now try making some conversions using the API: :ref:`REST API Documentation`

Transaction Scanning and Conversion
------------------------------------

To handle incoming deposits, and converting deposits into their destination coin, there are two management
commands to run.

``./manage.py load_txs``

    The command **load_txs** imports incoming transactions into the Deposits table for any Coin that
    has a properly configured Coin Handler (:ref:`Coin Handlers`).

``./manage.py convert_coins``

    The command **convert_coins** scans each deposit in the Deposit table to check if it's valid, and which
    Coin it should be converted to.

    Each valid deposit will then be converted into it's destination coin, and the deposit will be marked as
    ``conv`` (Successfully Converted).

    If you're running with DEBUG set to true, you'll see a detailed log of what it's doing, so you can diagnose
    any problems with your coin configuration and fix it.


When running in production, you would normally have these running on a **cron** - a scheduled task.

To find out how to run this in production, please read :ref:`Running in Production`


