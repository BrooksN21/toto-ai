from datetime import datetime, timezone

from toto_ai.external_odds.collection import (
    PinnedRevalidationEvent,
    PinnedRevalidationSummary,
)


def ready_pinned_revalidation(
    observed_at: datetime | None = None,
) -> PinnedRevalidationSummary:
    observed = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stamp = observed.isoformat()
    return PinnedRevalidationSummary(
        expected_count=15,
        matched_count=15,
        missing_event_orders=(),
        provider_failure_event_orders=(),
        stale_event_orders=(),
        date_failure_event_orders=(),
        identity_failure_event_orders=(),
        start_time_failure_event_orders=(),
        failed_schedule_dates=(),
        oldest_schedule_fetched_at=stamp,
        newest_schedule_fetched_at=stamp,
        maximum_schedule_age_seconds=0.0,
        schedule_fresh=True,
        provider_checks_passed=True,
        fixture_checks_passed=True,
        team_checks_passed=True,
        orientation_checks_passed=True,
        start_time_checks_passed=True,
        required_dates_complete=True,
        ready_for_play=True,
        events=tuple(
            PinnedRevalidationEvent(
                event_order=order,
                status="matched",
                reason="exact valid drawing pin; name rematching bypassed",
            )
            for order in range(15)
        ),
    )
