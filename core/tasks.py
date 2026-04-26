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

from celery import shared_task

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# process_payout
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    name='core.tasks.process_payout',
    max_retries=5,
    default_retry_delay=60,          # Start with 60s, apply exponential below
    queue='payouts',
    # acks_late & reject_on_worker_lost are set globally in settings but
    # can be overridden per-task if needed.
)
def process_payout(self, payout_id: str) -> dict:
    """
    Dispatch a single PENDING payout to the payment gateway.

    This task is enqueued by the API view immediately after a Payout
    is created (status=PENDING). It is responsible for:
      1. Fetching the Payout and verifying its status is still PENDING.
      2. Transitioning status → PROCESSING.
      3. Calling the payment gateway (IMPS/NEFT/RTGS/UPI).
      4. On success  → status = COMPLETED, record reference_id.
      5. On failure  → retry with exponential backoff.
      6. On max retries exhausted → status = FAILED, release held funds.

    Args:
        payout_id (str): UUID of the Payout to process.

    Returns:
        dict: Summary of the outcome (logged by Celery).

    Retry policy:
        Attempt 1 → immediate
        Attempt 2 → 60s
        Attempt 3 → 120s  (2× countdown each retry)
        Attempt 4 → 240s
        Attempt 5 → 480s
        Attempt 6 → FAILED (max_retries=5 means 5 retries after the 1st attempt)
    """
    # Implementation will be added in the payout processing step.
    # For now, just log and acknowledge the task.
    logger.info("process_payout called for payout_id=%s (not yet implemented)", payout_id)

    # Example of how retry with exponential backoff will look:
    # try:
    #     result = gateway.dispatch(payout)
    # except GatewayTemporaryError as exc:
    #     raise self.retry(
    #         exc=exc,
    #         countdown=60 * (2 ** self.request.retries),  # exponential
    #     )

    return {'payout_id': payout_id, 'status': 'queued'}


# ---------------------------------------------------------------------------
# retry_stuck_payouts  (Periodic / Beat task)
# ---------------------------------------------------------------------------

@shared_task(
    name='core.tasks.retry_stuck_payouts',
    queue='default',
)
def retry_stuck_payouts() -> dict:
    """
    Periodic task (runs every 5 min via Celery Beat) that finds any
    Payout stuck in PENDING or PROCESSING state beyond a timeout
    threshold and re-enqueues it for processing.

    This acts as a safety net for:
      - Tasks that were dropped before being picked up by a worker.
      - Workers that crashed mid-task (PROCESSING but never resolved).

    Implementation will be added in the payout processing step.
    """
    logger.info("retry_stuck_payouts: scanning for stuck payouts (not yet implemented)")
    return {'checked': 0, 'requeued': 0}
