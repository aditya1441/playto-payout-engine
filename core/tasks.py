import logging
import random
import uuid

from celery import shared_task
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)

_PROB_SUCCESS = 0.70
_PROB_FAILURE = 0.20


@shared_task(
    bind=True,
    name='core.tasks.process_payout',
    max_retries=3,
    default_retry_delay=30,
)
def process_payout(self, payout_id: str) -> dict:
    """
    Pick up a payout and drive it through the simulated payment gateway.

    Uses a CAS update (PENDING → PROCESSING) to guarantee exactly-once
    execution across concurrent or duplicate task deliveries.

    Simulated outcomes: 70% success, 20% failure, 10% gateway timeout.
    Stuck payouts are retried with exponential backoff; after max_retries
    the on_failure handler marks the payout FAILED and reverses the funds.
    """
    from .services import (
        transition_payout_to_processing,
        complete_payout,
        fail_payout,
        reset_processing_to_pending,
    )
    from .models import Payout

    logger.info("process_payout start payout_id=%s attempt=%d", payout_id, self.request.retries + 1)

    payout = transition_payout_to_processing(payout_id)
    if payout is None:
        try:
            current = Payout.objects.get(id=payout_id)
            logger.info("process_payout skip payout_id=%s status=%s", payout_id, current.status)
        except Payout.DoesNotExist:
            logger.warning("process_payout skip payout_id=%s not found", payout_id)
        return {'payout_id': payout_id, 'outcome': 'skipped'}

    roll = random.random()

    if roll < _PROB_SUCCESS:
        reference_id = f"UTR{uuid.uuid4().hex[:12].upper()}"
        complete_payout(payout, reference_id)
        logger.info("process_payout completed payout_id=%s ref=%s", payout_id, reference_id)
        return {'payout_id': payout_id, 'outcome': 'completed', 'reference_id': reference_id}

    if roll < _PROB_SUCCESS + _PROB_FAILURE:
        reason = "Gateway rejected: invalid beneficiary account details"
        fail_payout(payout, reason)
        logger.warning("process_payout failed payout_id=%s reason=%s", payout_id, reason)
        return {'payout_id': payout_id, 'outcome': 'failed', 'reason': reason}

    # Gateway timeout — reset state and retry with exponential backoff.
    reset_processing_to_pending(payout_id, older_than_seconds=0)
    countdown = 30 * (2 ** self.request.retries)
    logger.warning(
        "process_payout timeout payout_id=%s retry_in=%ds attempt=%d/%d",
        payout_id, countdown, self.request.retries + 1, self.max_retries,
    )
    raise self.retry(exc=Exception(f"Gateway timeout for payout {payout_id}"), countdown=countdown)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """All retries exhausted — mark the payout FAILED and reverse the hold."""
        from .services import fail_payout, transition_payout_to_processing

        payout_id = args[0] if args else kwargs.get('payout_id')
        logger.error("process_payout max retries exceeded payout_id=%s", payout_id)

        if not payout_id:
            return

        payout = transition_payout_to_processing(payout_id)
        if payout:
            fail_payout(payout, f"Max retries exceeded: {exc}")


@shared_task(name='core.tasks.retry_stuck_payouts', queue='default')
def retry_stuck_payouts() -> dict:
    """
    Periodic safety-net (runs every 5 minutes via Celery Beat).

    Re-enqueues payouts that fell out of the normal processing flow:
    - PENDING for > 2 min: the task was likely dropped from the queue.
    - PROCESSING for > 30 s: the worker crashed after the CAS update.
    """
    from .models import Payout, PayoutStatus
    from .services import reset_processing_to_pending

    now = timezone.now()
    requeued_pending = 0
    reset_processing = 0

    stale_pending = Payout.objects.filter(
        status=PayoutStatus.PENDING,
        initiated_at__lte=now - timedelta(minutes=2),
    ).values_list('id', flat=True)

    for payout_id in stale_pending:
        process_payout.apply_async(args=[str(payout_id)])
        requeued_pending += 1

    stale_processing = Payout.objects.filter(
        status=PayoutStatus.PROCESSING,
        initiated_at__lte=now - timedelta(seconds=30),
    ).values_list('id', flat=True)

    for payout_id in stale_processing:
        if reset_processing_to_pending(str(payout_id), older_than_seconds=30):
            process_payout.apply_async(args=[str(payout_id)])
            reset_processing += 1

    logger.info(
        "retry_stuck_payouts done requeued_pending=%d reset_processing=%d",
        requeued_pending, reset_processing,
    )
    return {'requeued_pending': requeued_pending, 'reset_processing': reset_processing}
