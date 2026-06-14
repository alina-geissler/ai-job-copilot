"""Decide job-search actions before calling the external provider."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from app.core.enums import PrimarySearchAction
from app.models.search_profile import SearchProfile
from app.models.search_run import SearchRun

logger = logging.getLogger(__name__)


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
    has_today_search_run_for_current_version: bool
) -> PrimarySearchDecision:
    """Decide how a primary search request should be handled.

    A run is only shown as existing when it was created with the same profile
    version (``profile_updated_at_snapshot``). Editing the profile clears that
    gate, allowing a fresh run while keeping the old run in history.

    :param today: Current calendar date.
    :param search_profile: Search profile selected by the user.
    :param last_search_run: Most recent persisted search run for this profile, if any.
    :param user_primary_searches_today_count: Number of primary searches the user already started today.
    :param has_today_search_run_for_current_version: Whether a run for today and the current profile version exists.
    :return: Decision object describing whether to start, block, or reuse a search run.
    """
    if has_today_search_run_for_current_version:
        return PrimarySearchDecision(
            action=PrimarySearchAction.SHOW_EXISTING_RUN,
            message=(
                "Du hast heute schon einen Suchlauf für dieses Suchprofil gestartet "
                "und kannst gern weitere Ergebnisse laden."
            ),
            search_run=None,
            date_posted=None,
            start_page=None,
            pages_to_fetch=None,
            loaded_page=None
        )

    if user_primary_searches_today_count >= 5:
        logger.info(
            "Job search blocked: daily primary-search limit reached.",
            extra={
                "search_profile_id": search_profile.id,
                "searches_today": user_primary_searches_today_count,
            },
        )
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
            loaded_page=None
        )

    logger.info(
        "New primary job search run started.",
        extra={"search_profile_id": search_profile.id},
    )
    return PrimarySearchDecision(
        action=PrimarySearchAction.START_NEW_RUN,
        message=None,
        search_run=None,
        date_posted=decide_date_posted(today=today, last_search_run=last_search_run),
        start_page=1,
        pages_to_fetch=5,
        loaded_page=5
    )


def decide_load_more(
    *,
    search_run: SearchRun,
    user_load_more_actions_today_count: int
) -> LoadMoreDecision:
    """Decide whether one more page may be loaded for a persisted search run.

    :param search_run: Existing persisted search run.
    :param user_load_more_actions_today_count: Number of load-more actions the user already used today.
    :return: Decision object describing whether loading more results is allowed.
    """
    if user_load_more_actions_today_count >= 15:
        logger.info(
            "Job search load-more blocked: daily limit reached.",
            extra={
                "search_run_id": search_run.id,
                "load_more_today": user_load_more_actions_today_count,
            },
        )
        return LoadMoreDecision(
            allowed=False,
            message=(
                "Du hast heute bereits alle Nachladeaktionen ausgeschöpft "
                "und kannst morgen erneut suchen."
            ),
            next_page=None,
            pages_to_fetch=None
        )

    if not search_run.can_load_more:
        return LoadMoreDecision(
            allowed=False,
            message=(
                "Heute ist für diesen Suchlauf kein sinnvolles Nachladen mehr möglich. "
                "Du kannst morgen erneut suchen."
            ),
            next_page=None,
            pages_to_fetch=None
        )

    return LoadMoreDecision(
        allowed=True,
        message=None,
        next_page=search_run.current_page + 1,
        pages_to_fetch=1
    )


def evaluate_primary_search_load_more_availability(
    *,
    total_jobs_returned: int,
    new_jobs_for_user_count: int
) -> LoadMoreStopEvaluation:
    """Evaluate whether further load-more requests remain useful after a primary search.

    :param total_jobs_returned: Number of jobs returned by the primary provider fetch.
    :param new_jobs_for_user_count: Number of jobs in the response that are new for the user.
    :return: Evaluation result describing whether further load-more actions should remain enabled.
    """
    if total_jobs_returned < 40 or new_jobs_for_user_count < 15:  # TODO: total war 50
        return LoadMoreStopEvaluation(
            allow_further_load_more=False,
            message=(
                "Heute ist für diesen Suchlauf kein sinnvolles Nachladen mehr möglich. "
                "Du kannst morgen erneut suchen."
            )
        )

    return LoadMoreStopEvaluation(allow_further_load_more=True, message=None)


def evaluate_load_more_availability_after_load_more(
    *,
    total_jobs_returned: int,
    new_jobs_for_user_count: int
) -> LoadMoreStopEvaluation:
    """Evaluate whether another load-more request remains useful.

    :param total_jobs_returned: Number of jobs returned by the latest load-more fetch.
    :param new_jobs_for_user_count: Number of jobs in the response that are new for the user.
    :return: Evaluation result describing whether another load-more action should remain enabled.
    """
    if total_jobs_returned < 7 or new_jobs_for_user_count < 3:  # TODO: total war 10
        return LoadMoreStopEvaluation(
            allow_further_load_more=False,
            message=(
                "Heute ist für diesen Suchlauf kein sinnvolles Nachladen mehr möglich. "
                "Du kannst morgen erneut suchen."
            )
        )

    return LoadMoreStopEvaluation(allow_further_load_more=True, message=None)


def decide_date_posted(*, today: date, last_search_run: SearchRun | None) -> str:
    """Return the provider ``date_posted`` value for a new primary run.

    :param today: Current calendar date.
    :param last_search_run: Most recent persisted search run for this profile, if any.
    :return: Provider-specific ``date_posted`` value for the next primary search.
    """
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
    return "week"  # TODO: -> "month"? oder höchstens "week" überall?


def _has_profile_changed_since_last_run(
    *,
    search_profile: SearchProfile,
    last_search_run: SearchRun | None
) -> bool:
    """Return whether the profile has been modified since the last run was created
    to determine whether a new primary search needs to be initiated.

    :param search_profile: Current search profile selected by the user.
    :param last_search_run: Most recent persisted search run for this profile, if any.
    :return: ``True`` if the profile changed after the last run was created, otherwise ``False``.
    """
    if last_search_run is None:
        return False

    return search_profile.updated_at is not None and search_profile.updated_at > last_search_run.created_at