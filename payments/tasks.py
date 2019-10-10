import json
from typing import Optional, Tuple

from celery.app.task import Context
from celery.task import BaseTask
from celery.result import AsyncResult
from django.db import transaction
from lockmgr.lockmgr import LockMgr, Locked
from privex.helpers import is_true, empty

from payments.coin_handlers import get_manager, has_loader, get_loaders, BaseLoader
from payments.coin_handlers.base import SettingsMixin
from payments.exceptions import ConvertError, ConvertInvalid, CTCException
from payments.lib import ConvertCore
from payments.models import Deposit, CoinPair, Coin, TaskLog
from steemengine.celery import app

import logging

log = logging.getLogger(__name__)


def _background_task(task: BaseTask, tl_cols: dict, task_args: list = None, task_kwargs: dict = None,
                     **kwargs) -> Tuple[TaskLog, AsyncResult]:
    task_args = [] if not task_args else task_args
    task_kwargs = [] if not task_kwargs else task_kwargs
    
    # a_res = task.delay(*task_args, **task_kwargs)
    a_res = task.apply_async(args=task_args, kwargs=task_kwargs, **kwargs)
    tl = TaskLog(action=task.name, task_id=a_res.task_id, **tl_cols)
    tl.save()
    return tl, a_res


def background_task(task: BaseTask, queued_by: Optional[str], t_conf: dict = None, *args, **kwargs) -> TaskLog:
    """
    Fire the Celery task ``task`` into the background, while also creating a :class:`.TaskLog` object and saving it
    to the database.

    On the returned object, you can call :py:meth:`.TaskLog.task_get` to wait for, and return the result from the task.
    Alternatively, you can use :py:meth:`.TaskLog.res_get` to get the :class:`.AsyncResult` object from Celery.

    Special behaviour:

      - If ``deposit_id`` is in the kwargs, it will be automatically added to the ``task_metadata`` of the TaskLog,
        and the foreign key :py:attr:`.TaskLog.deposit` will be linked to that deposit ID.

    Usage:

        >>> from payments import tasks
        >>> # Returns a TaskLog model object. Additional args/kwargs are passed to your task.
        >>> tl = tasks.background_task(tasks.check_deposit, 'somefunc', deposit_id=123)
        >>> result = tl.task_get(timeout=5)   # Helper method, same as using .get() on an AsyncResult

    :param celery.task.BaseTask task: A Celery task function i.e. one using the decorator ``@app.task``
    :param str queued_by: The function/module or other name to recognise what triggered the task. Can be ``None``
    :param dict t_conf: Extra config options for this function. Non-config keys will be passed to TaskLog.

    :param Any args: Forwarded to your task
    :param Any kwargs: Forwarded to your task

    :return TaskLog tl: A :class:`payments.models.TaskLog` instance.
    """
    t_conf = {} if not t_conf else dict(t_conf)
    
    task_metadata = t_conf.get('task_metadata', {})
    task_name = task.name
    
    _bg_args = {}
    if 'link' in t_conf: _bg_args['link'] = t_conf.pop('link')
    if 'link_error' in t_conf: _bg_args['link_error'] = t_conf.pop('link_error')
    
    tl_cols = dict(metadata=json.dumps(task_metadata), queued_by=queued_by, **t_conf)
    # Add deposit_id to the TaskLog metadata and link the related Deposit object for ease of use.
    if 'deposit_id' in kwargs:
        dep_id = int(kwargs['deposit_id'])
        tl_cols['deposit'] = Deposit.objects.get(id=dep_id)
        if 'deposit_id' not in task_metadata:
            task_metadata['deposit_id'] = dep_id

    tl, a_res = _background_task(task=task, tl_cols=tl_cols, task_args=list(args), task_kwargs=kwargs, **_bg_args)
    return tl


@app.task
def auto_refund(deposit_id: int, last_error: str = None):
    deposit = Deposit.objects.get(id=deposit_id)
    with transaction.atomic():
        mgr = get_manager(deposit.coin.symbol)  # type: SettingsMixin
        should_refund = mgr.settings.get(deposit.coin.symbol, {}).get('auto_refund', False)
        if is_true(should_refund):
            with LockMgr(f'auto_refund:{deposit_id}'):
                log.info(f'Auto refund is enabled for coin {deposit.coin}. Attempting return to sender.')
                dep, refund_data = ConvertCore.refund_sender(deposit=deposit)
                return dict(deposit_id=dep.id, refund_data=dict(refund_data))
    if not last_error:
        return None
    
    raise CTCException(last_error)
    

@app.task
def handle_errors(request: Context, exc, traceback, deposit_id):
    log.info('Deposit ID: %s', deposit_id)
    log.info('Request: %s', request)
    log.info('Exc - Type: %s ||| Message: %s', type(exc), str(exc))
    log.info('Traceback: %s', traceback)
    ex_type = type(exc)
    tname = request.task
    if ex_type is Locked:
        log.warning('Ran into lock while running %s - will try again later...', tname)
        return
    d = Deposit.objects.get(id=deposit_id)
    e = exc
    if ex_type is ConvertInvalid:
        log.error('ConvertInvalid (user mistake) while running %s - Deposit: "%s" Message: %s', tname, d, str(e))
        d.status = 'inv'
        d.error_reason = f"<ConvertInvalid>: {str(e)}"
        d.save()
        return
    if ex_type is ConvertError:
        log.error('ConvertError while running %s - Deposit: "%s" !!! Message: %s', tname, d, str(e))
        if '.check_deposit' in request['task']:
            # Fire off to auto_refund which will automatically refund the deposit if enabled, otherwise will set the
            # error state on the deposit with the error reason.
            background_task(
                auto_refund, 'tasks.handle_errors', t_conf=dict(link_error=handle_errors.s(deposit_id)),
                **dict(deposit_id=deposit_id, last_error=str(e))
            )
            return
        d.status = 'err'
        d.error_reason = f"<ConvertError>: {str(e)}"
        d.save()
        return

    log.error('UNHANDLED EXCEPTION. Task %s raised exception: %s (Message: %s) ... Deposit: %s\nTraceback: %s',
              tname, type(e), str(e), d, traceback)

    d.status = 'err'
    d.error_reason = f"Unknown error while running {tname}. An admin should check the error logs.\n" \
        f"Last Exception was:\n{type(e)}\n{str(e)}\n{traceback}"
    d.save()
    return


@app.task
def convert_deposit(deposit_id: int, dry=False) -> Optional[dict]:
    """
    Takes a Deposit in the 'mapped' state (has been through detect_deposit), and attempts to convert it
    to the destination coin.

    :param bool dry: If true, does not run ConvertCore.convert, only logs what would be ran.
    :param Deposit deposit_id: A :class:`payments.models.Deposit` object to convert
    :raises ConvertError: Raised when a serious error occurs that generally isn't the sender's fault.
    :raises ConvertInvalid: Raised when a Deposit fails validation, i.e. the sender ignored our instructions.
    """
        
    d = Deposit.objects.get(id=deposit_id)
    
    with LockMgr(f'convert_deposit:{d.id}'):
        if d.status != 'mapped':
            raise ConvertError("Deposit not in 'mapped' state during convert_deposit... Something is very wrong!")
        try:
            if empty(d.convert_to) or empty(d.convert_dest_address):
                raise ConvertError('Deposit "convert_to" or "convert_dest_addr" is empty... Cannot convert!')
            with transaction.atomic():
                pair = CoinPair.objects.get(from_coin=d.coin, to_coin=d.convert_to)
                log.debug('Converting deposit ID %s from %s to %s, coin pair: %s', d.id, d.coin, d.convert_to, pair)
                # Convert() will send the coins, update the Deposit, and create the Conversion object in the DB,
                # as well as some additional validation such as balance checks.
                if dry:
                    log.debug(f"DRY RUN: Would run ConvertCore.convert({d}, {pair}, {d.convert_dest_address}, "
                              f"dest_memo='{d.convert_dest_memo}')")
                    return None
                conv = ConvertCore.convert(d, pair, d.convert_dest_address, dest_memo=d.convert_dest_memo)
                return dict(conversion_id=conv.id)
        except (CoinPair.DoesNotExist, Coin.DoesNotExist):
            raise ConvertInvalid('Deposit is for non-existent coin pair')


@app.task
def check_deposit(deposit_id: int) -> int:
    """
    Validates a Deposit through various sanity checks, detects which coin the Deposit is destined for, as well as
    where to send it to.
    
    Stores the destination details onto deposit's the convert_xxx fields and updates the state to 'mapped'.
    
    :param int deposit_id: The primary key `id` for the deposit to check.
    :raises ConvertError: Raised when a serious error occurs that generally isn't the sender's fault.
    :raises ConvertInvalid: Raised when a Deposit fails validation, i.e. the sender ignored our instructions.
    """
    d = Deposit.objects.get(id=deposit_id)
    try:
        with LockMgr(f'detect_deposit:{d.id}'):
            if d.status != 'new':
                raise ConvertError("Deposit is not in 'new' state during detect_deposit... Something is very wrong!")
            log.debug('Validating deposit and getting dest details for deposit %s', d)
            # Validate the deposit, and grab the destination coin details
            with transaction.atomic():
                address, pair, dest_memo = ConvertCore.validate_deposit(d)
                # If no exception was thrown, we change the state to 'mapped' and save the destination details.
                log.debug('Deposit mapped to destination. pair: "%s", addr: "%s", memo: "%s"', pair, address, dest_memo)
                d.status = 'mapped'
                d.convert_to = pair.to_coin
                d.convert_dest_address = address
                d.convert_dest_memo = dest_memo
                d.save()
            
            return d.id
    except (CoinPair.DoesNotExist, Coin.DoesNotExist) as e:
        log.warning('Deposit "%s" is for non-existent coin pair...', d)
        # d.status = 'inv'
        # d.error_reason = str('Deposit is for non-existent coin pair')
        # d.save()
        raise ConvertInvalid(f'Deposit is for non-existent coin / pair: {type(e)} {str(e)}')


@app.task
def load_txs(symbol: str, batch: int = 100):
    log.info('Loading transactions for %s...', symbol)
    log.debug('%s has loader? %s', symbol, has_loader(symbol))
    if not has_loader(symbol):
        log.warning('Coin %s is enabled, but no Coin Handler has a loader setup for it. Skipping.', symbol)
        return
    try:
        with LockMgr(f'load_txs:{symbol}'):
            loaders = get_loaders(symbol)
            for l in loaders:  # type: BaseLoader
                log.debug('Scanning using loader %s', type(l))
                finished = False
                l.load()
                txs = l.list_txs(batch)
                while not finished:
                    log.debug('Loading batch of %s TXs for DB insert', batch)
                    with transaction.atomic():
                        finished = import_batch(txs=txs, batch=batch)
    except Locked:
        log.warning('Warning: A lock is already held for load_txs:%s - Skipping.', symbol)
    except:
        log.exception('Error loading transactions for coin %s. Moving onto the next coin.', symbol)


def import_batch(txs: iter, batch: int = 100) -> bool:
    """
    Inserts up to `batch` amount of transactions from `txs` into the Deposit table per run
    Returns a boolean to determine if there are no more transactions to be loaded

    :param txs:   A generator of transactions to import into Deposit()
    :param batch: Amount of transactions to import from the generator
    :return bool: True if there are no more transactions to load
    :return bool: False if there may be more transactions to be loaded
    """
    i = 0
    # var `tx` should be in this format:
    # May contain either (from_account, to_account, memo) or (address,)
    # {txid:str, coin:str (symbol), vout:int, tx_timestamp:datetime, address:str,
    #                 from_account:str, to_account:str, memo:str, amount:Decimal}
    for tx in txs:
        try:
            tx = dict(tx)
            dupes = Deposit.objects.filter(txid=tx['txid']).count()
            if dupes > 0:
                log.debug('Skipping TX %s as it already exists', tx['txid'])
                continue
            log.debug('Storing TX %s', tx['txid'])
            log.debug(f"From: '{tx.get('from_account', 'n/a')}' - Amount: {tx['amount']} {tx['coin']}")
            log.debug(f"Memo: '{tx.get('memo', '--NO MEMO--')}' - Time: {tx['tx_timestamp']}")
            tx['coin'] = Coin.objects.get(symbol=tx['coin'])
            with transaction.atomic():
                Deposit(**tx).save()
        except:
            log.exception('Error saving TX %s for coin %s, will skip.', tx['txid'], tx['coin'])
        finally:
            i += 1
            if i >= batch:
                return False
    return i < batch
