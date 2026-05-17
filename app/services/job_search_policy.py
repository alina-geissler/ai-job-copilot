"""Decide job-search actions before calling the external provider."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.models.search_profile import SearchProfile
from app.models.search_run import SearchRun


class PrimarySearchAction(StrEnum):
    """Represent the next allowed action for a primary search request."""

    START_NEW_RUN = "start_new_run"
    SHOW_EXISTING_RUN = "show_existing_run"
    BLOCKED_DAILY_LIMIT = "blocked_daily_limit"
    BLOCKED_PROFILE_LIMIT = "blocked_profile_limit"


@dataclass(slots=True)
class PrimarySearchDecision:
    """Describe how a primary search request should be handled."""

    action: PrimarySearchAction
    message: str | None
    search_run: SearchRun | None
    date_posted: str | None
    start_page: int | None
    pages_to_fetch: int | None
    loaded_page: int | None


@dataclass(slots=True)
class LoadMoreDecision:
    """Describe whether and how a search run may be continued."""

    allowed: bool
    message: str | None
    next_page: int | None
    pages_to_fetch: int | None


@dataclass(slots=True)
class LoadMoreStopEvaluation:
    """Describe whether further load-more requests should remain available."""

    allow_further_load_more: bool
    message: str | None


def decide_primary_search(
    *,
    today: date,
    search_profile: SearchProfile,
    last_search_run: SearchRun | None,
    user_primary_searches_today_count: int,
    has_primary_search_for_profile_today: bool,
) -> PrimarySearchDecision:
    """Decide how a primary search request should be handled."""
    profile_changed_since_last_run = _has_profile_changed_since_last_run(
        search_profile=search_profile,
        last_search_run=last_search_run,
    )

    if has_primary_search_for_profile_today and last_search_run is not None and not profile_changed_since_last_run:
        return PrimarySearchDecision(
            action=PrimarySearchAction.SHOW_EXISTING_RUN,
            message=(
                "Du hast heute schon einen Suchlauf für dieses Suchprofil gestartet "
                "und kannst gern weitere Ergebnisse laden."
            ),
            search_run=last_search_run,
            date_posted=None,
            start_page=None,
            pages_to_fetch=None,
            loaded_page=None,
        )

    if user_primary_searches_today_count >= 100: # TODO: -> 5 !!!
        return PrimarySearchDecision(
            action=PrimarySearchAction.BLOCKED_DAILY_LIMIT,
            message=(
                "Du hast heute bereits alle Primärsuchen ausgeschöpft "
                "und kannst morgen erneut suchen."
            ),
            search_run=None,
            date_posted=None,
            start_page=None,
            pages_to_fetch=None,
            loaded_page=None,
        )

    if has_primary_search_for_profile_today and profile_changed_since_last_run:
        return PrimarySearchDecision(
            action=PrimarySearchAction.BLOCKED_PROFILE_LIMIT,
            message=(
                "Für dieses Suchprofil wurde heute bereits eine Primärsuche gestartet. "
                "Durch die Profiländerung wäre ein neuer Suchlauf nötig, "
                "aber pro Suchprofil ist nur eine Primärsuche möglich."
            ),
            search_run=None,
            date_posted=None,
            start_page=None,
            pages_to_fetch=None,
            loaded_page=None,
        )

    return PrimarySearchDecision(
        action=PrimarySearchAction.START_NEW_RUN,
        message=None,
        search_run=None,
        date_posted=decide_date_posted(today=today, last_search_run=last_search_run),
        start_page=1,
        pages_to_fetch=5,
        loaded_page=5,
    )


def decide_load_more(
    *,
    search_run: SearchRun,
    user_load_more_actions_today_count: int,
) -> LoadMoreDecision:
    """Decide whether one more page may be loaded for a persisted search run."""
    if user_load_more_actions_today_count >= 100:  # TODO: -> 15 !!!
        return LoadMoreDecision(
            allowed=False,
            message=(
                "Du hast heute bereits alle Nachladeaktionen ausgeschöpft "
                "und kannst morgen erneut suchen."
            ),
            next_page=None,
            pages_to_fetch=None,
        )

    if not search_run.can_load_more:
        return LoadMoreDecision(
            allowed=False,
            message=(
                "Heute ist für diesen Suchlauf kein sinnvolles Nachladen mehr möglich. "
                "Du kannst morgen erneut suchen."
            ),
            next_page=None,
            pages_to_fetch=None,
        )

    return LoadMoreDecision(
        allowed=True,
        message=None,
        next_page=search_run.current_page + 1,
        pages_to_fetch=1,
    )


def evaluate_primary_search_load_more_availability(
    *,
    total_jobs_returned: int,
    new_jobs_for_user_count: int,
) -> LoadMoreStopEvaluation:
    """Evaluate whether further load-more requests remain useful after a primary search."""
    if total_jobs_returned < 50 or new_jobs_for_user_count < 15:
        return LoadMoreStopEvaluation(
            allow_further_load_more=False,
            message=(
                "Heute ist für diesen Suchlauf kein sinnvolles Nachladen mehr möglich. "
                "Du kannst morgen erneut suchen."
            ),
        )

    return LoadMoreStopEvaluation(allow_further_load_more=True, message=None)


def evaluate_load_more_availability_after_load_more(
    *,
    total_jobs_returned: int,
    new_jobs_for_user_count: int,
) -> LoadMoreStopEvaluation:
    """Evaluate whether another load-more request remains useful."""
    if total_jobs_returned < 10 or new_jobs_for_user_count < 3:
        return LoadMoreStopEvaluation(
            allow_further_load_more=False,
            message=(
                "Heute ist für diesen Suchlauf kein sinnvolles Nachladen mehr möglich. "
                "Du kannst morgen erneut suchen."
            ),
        )

    return LoadMoreStopEvaluation(allow_further_load_more=True, message=None)


def decide_date_posted(*, today: date, last_search_run: SearchRun | None) -> str:
    """Return the provider ``date_posted`` value for a new primary run."""
    if last_search_run is None:
        return "week"

    days_since_last_run = (today - last_search_run.run_date).days

    if days_since_last_run <= 0:
        return last_search_run.date_posted
    if days_since_last_run == 1:
        return "today"
    if 2 <= days_since_last_run <= 3:
        return "three_days"
    if 4 <= days_since_last_run <= 7:
        return "week"
    if 8 <= days_since_last_run <= 30:
        return "month"
    return "week"


def _has_profile_changed_since_last_run(
    *,
    search_profile: SearchProfile,
    last_search_run: SearchRun | None,
) -> bool:
    """Return whether the profile has been modified since the last run was created
    to determine whether a new primary search needs to be initiated."""
    if last_search_run is None:
        return False

    return search_profile.updated_at is not None and search_profile.updated_at > last_search_run.created_at