"""
tasks.py — Celery task definitions for the payout engine.

All tasks are discoverable because:
  - This module is named 'tasks' inside a registered Django app ('core').
  - app.autodiscover_tasks() in payout_engine/celery.py picks it up automatically.

Task naming convention: <app>.<module>.<function>
  e.g.  core.tasks.process_payout

Queue strategy (defined in settings.CELERY_TASK_ROUTES):
  - 'payouts' queue  → process_payout  (time-sensitive, payment gateway calls)
  - 'default' queue  → everything else (housekeeping, retries)
"""
import logging
import random
import uuid

from celery import shared_task
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)

# Simulated gateway outcome probabilities
_PROB_SUCCESS = 0.70   # 70%
_PROB_FAILURE = 0.20   # 20%  → cumulative 0.90
# _PROB_STUCK  = 0.10  # 10%  → cumulative 1.00 (remainder)


# ---------------------------------------------------------------------------
# process_payout
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    name='core.tasks.process_payout',
    max_retries=3,
    default_retry_delay=30,
    queue='payouts',
)
def process_payout(self, payout_id: str) -> dict:
    """
    Process a single payout through the (simulated) payment gateway.

    Idempotency guarantee:
        The PENDING → PROCESSING transition uses a CAS UPDATE:
            UPDATE payouts SET status='PROCESSING'
            WHERE id=%s AND status='PENDING'
        Only ONE worker can win this race. Any duplicate execution
        (re-delivery, manual retry, beat re-queue) will get
        updated_rows=0 and exit cleanly.

    Simulation outcomes:
        70%  SUCCESS → COMPLETED  (UTR reference generated)
        20%  FAILURE → FAILED     (reversal CREDIT ledger entry written)
        10%  STUCK   → payout reset to PENDING, task retried with
                       exponential backoff (60 × 2^attempt seconds)

    Retry policy (max_retries=3):
        Attempt 1: immediate
        Attempt 2: 30s
        Attempt 3: 60s
        Attempt 4: raises MaxRetriesExceededError → on_failure() marks FAILED

    Args:
        payout_id (str): UUID of the Payout to process.

    Returns:
        dict: {'payout_id', 'outcome', ...outcome-specific fields}
    """
    from .services import (
        transition_payout_to_processing,
        complete_payout,
        fail_payout,
        reset_processing_to_pending,
    )
    from .models import Payout, PayoutStatus

    logger.info("[process_payout] START payout_id=%s attempt=%d",
                payout_id, self.request.retries + 1)

    # ── Step 1: CAS transition PENDING → PROCESSING ───────────────────────
    # Returns the Payout if this worker claimed it, None if already claimed.
    payout = transition_payout_to_processing(payout_id)

    if payout is None:
        # Another worker (or a previous attempt) already moved this payout
        # past PENDING. Fetch its current state for logging only.
        try:
            current = Payout.objects.get(id=payout_id)
            logger.info(
                "[process_payout] SKIP payout_id=%s — already %s",
                payout_id, current.status
            )
        except Payout.DoesNotExist:
            logger.warning("[process_payout] SKIP payout_id=%s — not found", payout_id)
        return {'payout_id': payout_id, 'outcome': 'skipped'}

    # ── Step 2: Simulate gateway call ────────────────────────────────────
    roll = random.random()

    if roll < _PROB_SUCCESS:
        # ── SUCCESS (70%) ─────────────────────────────────────────────────
        reference_id = f"UTR{uuid.uuid4().hex[:12].upper()}"
        applied = complete_payout(payout, reference_id)

        if applied:
            logger.info(
                "[process_payout] COMPLETED payout_id=%s ref=%s",
                payout_id, reference_id
            )
        else:
            # Guarded update applied 0 rows — payout was resolved externally.
            logger.warning(
                "[process_payout] complete_payout noop for payout_id=%s", payout_id
            )

        return {
            'payout_id':    payout_id,
            'outcome':      'completed',
            'reference_id': reference_id,
        }

    elif roll < (_PROB_SUCCESS + _PROB_FAILURE):
        # ── FAILURE (20%) ─────────────────────────────────────────────────
        reason = "Gateway rejected: invalid beneficiary account details"
        applied = fail_payout(payout, reason)

        if applied:
            logger.warning(
                "[process_payout] FAILED payout_id=%s reason=%s",
                payout_id, reason
            )
        else:
            logger.warning(
                "[process_payout] fail_payout noop for payout_id=%s", payout_id
            )

        return {
            'payout_id': payout_id,
            'outcome':   'failed',
            'reason':    reason,
        }

    else:
        # ── STUCK / GATEWAY TIMEOUT (10%) ─────────────────────────────────
        # Reset payout back to PENDING so the next retry attempt can claim
        # it via the CAS update. If we left it in PROCESSING and retried,
        # transition_payout_to_processing() would return None (wrong state).
        reset_processing_to_pending(payout_id, older_than_seconds=0)

        countdown = 60 * (2 ** self.request.retries)  # Exponential backoff
        logger.warning(
            "[process_payout] TIMEOUT payout_id=%s — retry in %ds (attempt %d/%d)",
            payout_id, countdown, self.request.retries + 1, self.max_retries
        )

        # self.retry() raises celery.exceptions.Retry (not a real exception).
        # Celery catches it and re-schedules the task transparently.
        raise self.retry(
            exc=Exception(f"Gateway timeout for payout {payout_id}"),
            countdown=countdown,
        )


@process_payout.on_failure
def on_process_payout_failure(self, exc, task_id, args, kwargs, einfo):
    """
    Called when process_payout exceeds max_retries.

    At this point the payout has been reset to PENDING on each retry but
    the worker has given up. We mark it FAILED with a reversal so funds
    are returned to the merchant.
    """
    from .services import fail_payout, transition_payout_to_processing
    from .models import Payout

    payout_id = args[0] if args else kwargs.get('payout_id')
    logger.error(
        "[process_payout] MAX RETRIES EXCEEDED payout_id=%s exc=%s",
        payout_id, exc
    )

    if not payout_id:
        return

    # Claim the payout (it's in PENDING after the last reset_processing_to_pending)
    payout = transition_payout_to_processing(payout_id)
    if payout:
        fail_payout(payout, f"Max retries exceeded: {exc}")
        logger.error("[process_payout] Marked payout %s as FAILED after max retries", payout_id)


# ---------------------------------------------------------------------------
# retry_stuck_payouts  (Periodic / Beat task — every 5 min)
# ---------------------------------------------------------------------------

@shared_task(
    name='core.tasks.retry_stuck_payouts',
    queue='default',
)
def retry_stuck_payouts() -> dict:
    """
    Scans for payouts stuck in PENDING or PROCESSING and re-enqueues them.

    Runs every 5 minutes via Celery Beat (configured in settings.CELERY_BEAT_SCHEDULE).

    Scenarios handled:
    1. PENDING for > 2 minutes:
       The task may have been dropped from the queue (Redis restart, network
       blip). Re-enqueue it.

    2. PROCESSING for > 30 seconds:
       The worker crashed after the CAS update but before resolving the payout.
       CELERY_TASK_REJECT_ON_WORKER_LOST=True should catch most of these, but
       this is the belt-and-suspenders fallback. Reset to PENDING and re-enqueue.

    Returns:
        dict: {'requeued_pending': N, 'reset_processing': M}
    """
    from .models import Payout, PayoutStatus

    now = timezone.now()
    requeued_pending   = 0
    reset_processing   = 0

    # ── Case 1: PENDING but not yet picked up ────────────────────────────
    stale_pending_cutoff = now - timedelta(minutes=2)
    stuck_pending = Payout.objects.filter(
        status=PayoutStatus.PENDING,
        initiated_at__lte=stale_pending_cutoff,
    ).values_list('id', flat=True)

    for payout_id in stuck_pending:
        process_payout.apply_async(
            args=[str(payout_id)],
            queue='payouts',
        )
        requeued_pending += 1
        logger.info("[retry_stuck_payouts] Re-enqueued PENDING payout %s", payout_id)

    # ── Case 2: PROCESSING for too long (worker crash) ───────────────────
    stale_processing_cutoff = now - timedelta(seconds=30)
    stuck_processing = Payout.objects.filter(
        status=PayoutStatus.PROCESSING,
        initiated_at__lte=stale_processing_cutoff,
    ).values_list('id', flat=True)

    for payout_id in stuck_processing:
        from .services import reset_processing_to_pending
        was_reset = reset_processing_to_pending(str(payout_id), older_than_seconds=30)
        if was_reset:
            process_payout.apply_async(
                args=[str(payout_id)],
                queue='payouts',
            )
            reset_processing += 1
            logger.warning(
                "[retry_stuck_payouts] Reset PROCESSING→PENDING and re-enqueued %s",
                payout_id
            )

    logger.info(
        "[retry_stuck_payouts] Done. requeued_pending=%d reset_processing=%d",
        requeued_pending, reset_processing
    )
    return {
        'requeued_pending':  requeued_pending,
        'reset_processing':  reset_processing,
    }
