from typing import Optional, Tuple

from lockmgr.lockmgr import Locked

from payments import tasks
from payments.exceptions import ConvertError, ConvertInvalid
from payments.models import TaskLog

import logging

log = logging.getLogger(__name__)


def handle_convert_deposit_errors(tl: TaskLog) -> Tuple[Optional[dict], bool]:
    d = tl.deposit
    res, success = None, False
    try:
        res = tl.task_get(timeout=600)
        log.debug('Convert Deposit task ran cleanly, no exceptions. %s', tl)
        success = True
    except Locked:
        log.warning('Warning: Deposit "%s" is currently locked in conversion phase. Skipping.', d)
    except ConvertError as e:
        # Something went very wrong while processing this deposit. Log the error, store the reason
        # onto the deposit, and then save it.
        log.error('ConvertError while converting deposit "%s" !!! Message: %s', d, str(e))
        d.status = 'err'
        d.error_reason = f"<ConvertError>: {str(e)}"
        d.save()
    except ConvertInvalid as e:
        # This exception usually means the sender didn't read the instructions properly, or simply
        # that the transaction wasn't intended to be exchanged.
        log.error('ConvertInvalid (user mistake) while converting deposit "%s" Message: %s', d, str(e))
        d.status = 'inv'
        d.error_reason = f"<ConvertInvalid>: {str(e)}"
        tl.error_log = tl.error_log + "\n" + d.error_reason
        d.save()
    except (BaseException, Exception) as e:
        log.exception('UNHANDLED EXCEPTION. Deposit could not be validated/detected... %s', d)
        d.status = 'err'
        d.error_reason = "Unknown error while running conversion. An admin should check the error logs.\n" \
                         f"Last Exception was:\n{type(e)}\n{str(e)}"
        tl.error_log = tl.error_log + "\n" + d.error_reason
        d.save()
    finally:
        tl.task_read = True
        tl.save()
    return res, success


def handle_auto_refund_errors(tl: TaskLog) -> Tuple[Optional[dict], bool]:
    d = tl.deposit
    res, success = None, False
    try:
        res = tl.task_get(timeout=600)
        log.debug('Auto Refund task ran cleanly, no exceptions. %s', tl)
        success = True
    except Locked:
        log.warning('Warning: (Locked) A refund is already in progress for deposit "%s". Skipping.', d)
    except (BaseException, Exception) as e:
        log.exception('An exception occurred during auto_refund...')
        d.status = 'err'
        d.error_reason = f'Auto refund failure: {type(e)} {str(e)}'
        tl.error_log = tl.error_log + "\n" + d.error_reason
        d.save()
    finally:
        tl.task_read = True
        tl.save()
    return res, success


def handle_deposit_errors(tl: TaskLog) -> Tuple[Optional[int], bool]:
    """
    Handles errors raised by :py:func:`payments.tasks.check_deposit` by processing the background task
    from a :class:`.TaskLog` object.
    
    :param TaskLog tl: A :class:`.TaskLog` object for running :py:func:`payments.tasks.check_deposit`
    """
    d = tl.deposit
    dep_id = d.id
    res, success = None, False
    try:
        res = tl.task_get(timeout=60)
        log.debug('Deposit task ran cleanly, no exceptions. %s', tl)
        success = True
    except Locked:
        log.warning('Warning: Deposit "%s" is currently locked in detection phase. Skipping.', d)
    except ConvertError as e:
        # Something went very wrong while processing this deposit.
        log.error('ConvertError while validating deposit "%s" !!! Message: %s', d, str(e))
        tl.error_log = tl.error_log + "\n" + d.error_reason
        # Fire off to auto_refund which will automatically refund the deposit if enabled, otherwise will set the
        # error state on the deposit with the error reason.
        tasks.background_task(tasks.auto_refund, tl.queued_by, deposit_id=dep_id, last_error=str(e))

    except ConvertInvalid as e:
        # This exception usually means the sender didn't read the instructions properly, or simply
        # that the transaction wasn't intended to be exchanged.
        log.error('ConvertInvalid (user mistake) while validating deposit "%s" Message: %s', d, str(e))
        d.status = 'inv'
        d.error_reason = f"<ConvertInvalid>: str(e)"
        tl.error_log = tl.error_log + "\n" + d.error_reason
        d.save()
    except (BaseException, Exception) as e:
        log.exception('UNHANDLED EXCEPTION. Deposit could not be validated/detected... %s', d)
        d.status = 'err'
        d.error_reason = "Unknown error while validating deposit. An admin should check the error logs.\n" \
            f"Last Exception was:\n{type(e)}\n{str(e)}"
        tl.error_log = tl.error_log + "\n" + d.error_reason
        d.save()
    finally:
        tl.task_read = True
        tl.save()
    
    return res, success


task_error_handlers = {
    tasks.convert_deposit.name: handle_convert_deposit_errors,
    tasks.check_deposit.name:   handle_deposit_errors,
    tasks.auto_refund.name:     handle_auto_refund_errors
}
