"""
This module init file is responsible for loading the Coin Handler modules, and offering methods for accessing
loaders and managers.

A **Coin Handler** is a Python module (folder containing classes and init file) designed to handle sending/receiving
cryptocurrency/tokens for a certain network, or certain family of networks sharing similar code.

They may handle just one single coin, several coins, or they may even allow users to dynamically add coins by
querying for a specific ``coin_type`` from the model :class:`payments.models.Coin`

A coin handler must contain:

 - An ``__init__.py`` with a dictionary named ``exports``, containing the keys 'loader' and/or 'manager' pointing
   to the un-instantiated loader/manager class.

   - If your init file needs to do some sort-of initialisation, such as dynamically generating ``provides`` for
     your classes, or adding a new coin type to settings.COIN_TYPES, it's best to place it in a function named
     "reload" with a global boolean ``loaded`` so that you only initialise the module the first time it's loaded.

     See the example __init__.py near the bottom of this module docstring.

     This is optional, but it will allow reload_handlers() to properly re-trigger your initialisation code
     only when changes occur, such as Coin's being created/updated in the database.

 - Two classes, a **Loader** and a **Manager**. Each class can either in it's own file, or in a single file containing
   other classes / functions.

   - A **Loader** is a class which extends :class:`base.BaseLoader`, and is responsible for retrieving transactions
     that occur on that coin to detect incoming transactions.
   - A **Manager** is a class which extends :class:`base.BaseManager`, and is responsible for handling sending/issuing
     of coins/tokens, as well as other small functions such as validating addresses, and checking balances.

Your **Loader** class may choose to extend the helper class :class:`base.BatchLoader`, allowing your loader
to use batches/chunking for memory efficiency, without having to write much code.

Your Coin Handler classes should ONLY use the exceptions in :py:mod:`base.exceptions`, along with any exceptions
listed in the `:raises:` pydoc statements of the overridden method.

For handling automatic retry when something goes wrong, you can use the decorator
:py:func:`base.decorators.retry_on_err`

Example `__init__.py`:

>>> from django.conf import settings
>>> from payments.coin_handlers.SteemEngine.SteemEngineLoader import SteemEngineLoader
>>> from payments.coin_handlers.SteemEngine.SteemEngineManager import SteemEngineManager
>>>
>>> loaded = False
>>>
>>> def reload():
>>>     global loaded
>>>     if 'steemengine' not in dict(settings.COIN_TYPES):
>>>         settings.COIN_TYPES += (('steemengine', 'SteemEngine Token',),)
>>>     loaded = True
>>>
>>> if not loaded:
>>>    reload()
>>>
>>> exports = {
>>>     "loader": SteemEngineLoader,
>>>     "manager": SteemEngineManager
>>> }


For an example of how to layout your coin handler module, check out the pre-included Coin Handlers:

 - :py:mod:`.SteemEngine`
 - :py:mod:`.Bitcoin`

"""
import logging
from decimal import Decimal
from importlib import import_module
from django.conf import settings
from django.db.migrations.executor import MigrationExecutor
from django.db import connections, DEFAULT_DB_ALIAS
from payments.coin_handlers.base import BaseLoader, BaseManager


handlers = {}
"""
A dictionary of coin symbols, containing instantiated managers (BaseManager) and loaders (BaseLoader)
example layout:

    handlers = {
        'ENG': {
            'loaders':  [ SteemEngineLoader, ],
            'managers': [ SteemEngineLoader, ],
        },
        'SGTK': {
            'loaders':  [ SteemEngineLoader, ],
            'managers': [ SteemEngineLoader, ],
        },
    }
"""


handlers_loaded = False
"""Used to track whether the Coin Handlers have been initialized, so reload_handlers can be auto-called."""

ch_base = settings.COIN_HANDLERS_BASE
"""Base module path to where the coin handler modules are located. E.g. payments.coin_handlers"""

log = logging.getLogger(__name__)


def is_database_synchronized(database: str) -> bool:
    """
    Check if all migrations have been ran. Useful for preventing auto-running code accessing models before the
    tables even exist, thus preventing you from migrating...

    >>> from django.db import DEFAULT_DB_ALIAS
    >>> if not is_database_synchronized(DEFAULT_DB_ALIAS):
    >>>     log.warning('Cannot run reload_handlers because there are unapplied migrations!')
    >>>     return

    :param str database: Which Django database config is being used? Generally just pass django.db.DEFAULT_DB_ALIAS
    :return bool: True if all migrations have been ran, False if not.
    """
    connection = connections[database]
    connection.prepare_database()
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    return False if executor.migration_plan(targets) else True


def get_loaders(symbol: str = None) -> list:
    """
    Get all loader's, or all loader's for a certain coin

    :param symbol: The coin symbol to get all loaders for (uppercase)
    :return list: If symbol not specified, a list of tuples (symbol, list<BaseLoader>,)
    :return list: If symbol IS specified, a list of instantiated :class:`base.BaseLoader`'s
    """
    if not handlers_loaded: reload_handlers()
    return [(s, data['loaders'],) for s, data in handlers] if symbol is None else handlers[symbol]['loaders']


def get_managers(symbol: str = None) -> list:
    """
    Get all manager's, or all manager's for a certain coin

    :param symbol: The coin symbol to get all managers for (uppercase)
    :return list: If symbol not specified, a list of tuples (symbol, list<BaseManager>,)
    :return list: If symbol IS specified, a list of instantiated :class:`base.BaseManager`'s
    """
    if not handlers_loaded: reload_handlers()
    return [(s, data['managers'],) for s, data in handlers] if symbol is None else handlers[symbol]['managers']


def get_manager(symbol: str) -> BaseManager:
    """
    For some use-cases, you may want to just grab the first manager that supports this coin.

        >>> m = get_manager('ENG')
        >>> m.send(amount=Decimal(1), from_address='someguy123', address='privex')

    :param symbol:         The coin symbol to get the manager for (uppercase)
    :return BaseManager:   An instance implementing :class:`base.BaseManager`
    """
    if not handlers_loaded: reload_handlers()
    return handlers[symbol]['managers'][0]


def get_loader(symbol: str) -> BaseLoader:
    """
    For some use-cases, you may want to just grab the first loader that supports this coin.

        >>> m = get_loader('ENG')
        >>> m.send(amount=Decimal(1), from_address='someguy123', address='privex')

    :param symbol:        The coin symbol to get the loader for (uppercase)
    :return BaseLoader:   An instance implementing :class:`base.BaseLoader`
    """
    if not handlers_loaded: reload_handlers()
    return handlers[symbol]['loaders'][0]


def add_handler(handler, handler_type):
    global handlers
    # `handler` is an un-instantiated class extending BaseLoader / BaseManager
    for symbol in handler.provides:
        if symbol not in handlers:
            handlers[symbol] = dict(loaders=[], managers=[])
        h = handler(symbol=symbol) if handler_type == 'managers' else handler(symbols=[symbol])
        handlers[symbol][handler_type].append(h)


def reload_handlers():
    """
    Resets `handler` to an empty dict, then loads all `settings.COIN_HANDLER` classes into the dictionary `handlers`
    using `settings.COIN_HANDLERS_BASE` as the base module path to load from
    """
    global handlers, handlers_loaded
    handlers = {}
    log.debug('--- Starting reload_handlers() ---')

    # To avoid a chicken and the egg problem where you can't run migrations because our handlers are using the DB
    # we make sure the DB is migrated before we allow any handlers to be loaded.
    if not is_database_synchronized(DEFAULT_DB_ALIAS):
        log.warning('Cannot run reload_handlers because there are unapplied migrations!')
        return

    for ch in settings.COIN_HANDLERS:
        try:
            log.debug('Loading coin handler %s', ch)
            i = import_module('.'.join([ch_base, ch]))
            # To avoid a handler's initialising code being ran every time the module is imported, a handler's init file
            # can define a reload() function, which is only ran the first time the module is loaded.
            # If reload_handlers() has been called, then we need to make sure we force reload those with a reload func.
            if handlers_loaded and hasattr(i, 'reload'):
                i.reload()
            ex = i.exports
            if 'loader' in ex:
                log.debug('Adding loader class for %s', ch)
                add_handler(ex['loader'], 'loaders')
            if 'manager' in ex:
                log.debug('Adding manager class for %s', ch)
                add_handler(ex['manager'], 'managers')
        except:
            log.exception("Something went wrong loading the handler %s", ch)
            log.error("Skipping this handler...")

    handlers_loaded = True
    log.debug('All handlers:')
    for sym, hdic in handlers.items():
        for l in hdic.get('loaders', []):
            log.debug('Symbol %s - Loader: %s', sym, type(l).__name__)
        for l in hdic.get('managers', []):
            log.debug('Symbol %s - Manager: %s', sym, type(l).__name__)
    log.debug('--- End of reload_handlers() ---')
