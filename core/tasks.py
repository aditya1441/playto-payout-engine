import logging
import random
import uuid

from celery import shared_task
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)

_PROB_SUCCESS = 0.70
_PROB_FAILURE = 0.20


@shared_task(bind=True, name='core.tasks.process_payout', max_retries=3, default_retry_delay=30)
def process_payout(self, payout_id: str) -> dict:
    from .services import transition_payout_to_processing, complete_payout, fail_payout
    from .models import Payout, PayoutStatus

    logger.info("process_payout payout_id=%s attempt=%d", payout_id, self.request.retries + 1)

    payout = transition_payout_to_processing(payout_id)
    if payout is None:
        try:
            current = Payout.objects.get(id=payout_id)
            logger.info("Skipping payout_id=%s — already %s", payout_id, current.status)
        except Payout.DoesNotExist:
            logger.warning("Payout %s not found", payout_id)
        return {'payout_id': payout_id, 'outcome': 'skipped'}

    roll = random.random()

    if roll < _PROB_SUCCESS:
        ref = f"UTR{uuid.uuid4().hex[:12].upper()}"
        complete_payout(payout, ref)
        logger.info("Completed payout_id=%s ref=%s", payout_id, ref)
        return {'payout_id': payout_id, 'outcome': 'completed', 'reference_id': ref}

    if roll < _PROB_SUCCESS + _PROB_FAILURE:
        reason = "Gateway rejected: invalid beneficiary account"
        fail_payout(payout, reason)
        logger.warning("Failed payout_id=%s reason=%s", payout_id, reason)
        return {'payout_id': payout_id, 'outcome': 'failed', 'reason': reason}

    # Timeout path — reset to PENDING and retry with backoff
    Payout.objects.filter(id=payout_id, status=PayoutStatus.PROCESSING).update(
        status=PayoutStatus.PENDING
    )

    countdown = 30 * (2 ** self.request.retries)
    logger.warning("Timeout payout_id=%s retry_in=%ds", payout_id, countdown)

    from celery.exceptions import MaxRetriesExceededError
    try:
        raise self.retry(exc=Exception(f"Gateway timeout: {payout_id}"), countdown=countdown)
    except MaxRetriesExceededError:
        logger.error("Max retries hit for payout_id=%s", payout_id)
        p = transition_payout_to_processing(payout_id)
        if p:
            fail_payout(p, "Max retries exceeded after gateway timeouts")
        return {'payout_id': payout_id, 'outcome': 'max_retries_failed'}


@shared_task(name='core.tasks.retry_stuck_payouts', queue='default')
def retry_stuck_payouts() -> dict:
    from .models import Payout, PayoutStatus
    from .services import reset_processing_to_pending

    now = timezone.now()
    requeued = reset = 0

    for pid in Payout.objects.filter(
        status=PayoutStatus.PENDING, initiated_at__lte=now - timedelta(minutes=2),
    ).values_list('id', flat=True):
        process_payout.apply_async(args=[str(pid)], task_id=f"retry-{pid}")
        requeued += 1

    for pid in Payout.objects.filter(
        status=PayoutStatus.PROCESSING, initiated_at__lte=now - timedelta(seconds=30),
    ).values_list('id', flat=True):
        if reset_processing_to_pending(str(pid)):
            process_payout.apply_async(args=[str(pid)], task_id=f"reset-{pid}")
            reset += 1

    logger.info("retry_stuck: requeued=%d reset=%d", requeued, reset)
    return {'requeued': requeued, 'reset': reset}


@shared_task(name='core.tasks.cleanup_expired_idempotency_keys')
def cleanup_expired_idempotency_keys_task() -> dict:
    from .services import cleanup_expired_idempotency_keys
    return {'deleted': cleanup_expired_idempotency_keys()}
