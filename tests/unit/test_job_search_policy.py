"""Unit tests for the pure job-search policy decision functions."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.core.enums import PrimarySearchAction
from app.services.job_search_policy import (
    LoadMoreDecision,
    PrimarySearchDecision,
    decide_date_posted,
    decide_load_more,
    decide_primary_search,
    evaluate_load_more_availability_after_load_more,
    evaluate_primary_search_load_more_availability,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile(updated_at=None):
    profile = MagicMock()
    profile.updated_at = updated_at
    return profile


def _make_run(run_date: date, date_posted: str = "week", current_page: int = 5,
              can_load_more: bool = True, created_at=None):
    run = MagicMock()
    run.run_date = run_date
    run.date_posted = date_posted
    run.current_page = current_page
    run.can_load_more = can_load_more
    run.created_at = created_at
    return run


TODAY = date(2025, 6, 11)


# ---------------------------------------------------------------------------
# decide_primary_search
# ---------------------------------------------------------------------------

class TestDecidePrimarySearch:
    """Tests for ``decide_primary_search``."""

    def test_show_existing_run_when_todays_run_exists(self):
        """Returning SHOW_EXISTING_RUN when a run for today already exists."""
        decision = decide_primary_search(
            today=TODAY,
            search_profile=_make_profile(),
            last_search_run=_make_run(TODAY),
            user_primary_searches_today_count=0,
            has_today_search_run_for_current_version=True,
        )
        assert decision.action == PrimarySearchAction.SHOW_EXISTING_RUN

    def test_blocked_when_daily_limit_exactly_5(self):
        """Returning BLOCKED when the user has reached 5 primary searches."""
        decision = decide_primary_search(
            today=TODAY,
            search_profile=_make_profile(),
            last_search_run=None,
            user_primary_searches_today_count=5,
            has_today_search_run_for_current_version=False,
        )
        assert decision.action == PrimarySearchAction.BLOCKED_DAILY_LIMIT

    def test_blocked_when_daily_limit_exceeded(self):
        """Returning BLOCKED when the user has exceeded 5 primary searches."""
        decision = decide_primary_search(
            today=TODAY,
            search_profile=_make_profile(),
            last_search_run=None,
            user_primary_searches_today_count=10,
            has_today_search_run_for_current_version=False,
        )
        assert decision.action == PrimarySearchAction.BLOCKED_DAILY_LIMIT

    def test_allowed_when_count_is_4(self):
        """Returning START_NEW_RUN when the user has only 4 searches so far."""
        decision = decide_primary_search(
            today=TODAY,
            search_profile=_make_profile(),
            last_search_run=None,
            user_primary_searches_today_count=4,
            has_today_search_run_for_current_version=False,
        )
        assert decision.action == PrimarySearchAction.START_NEW_RUN

    def test_start_new_run_when_no_prior_run(self):
        """Returning START_NEW_RUN with correct defaults when no prior run exists."""
        decision = decide_primary_search(
            today=TODAY,
            search_profile=_make_profile(),
            last_search_run=None,
            user_primary_searches_today_count=0,
            has_today_search_run_for_current_version=False,
        )
        assert decision.action == PrimarySearchAction.START_NEW_RUN
        assert decision.start_page == 1
        assert decision.pages_to_fetch == 5
        assert decision.loaded_page == 5

    def test_show_existing_run_takes_priority_over_limit(self):
        """SHOW_EXISTING_RUN is returned even when the daily limit would block."""
        decision = decide_primary_search(
            today=TODAY,
            search_profile=_make_profile(),
            last_search_run=_make_run(TODAY),
            user_primary_searches_today_count=5,
            has_today_search_run_for_current_version=True,
        )
        assert decision.action == PrimarySearchAction.SHOW_EXISTING_RUN


# ---------------------------------------------------------------------------
# decide_load_more
# ---------------------------------------------------------------------------

class TestDecideLoadMore:
    """Tests for ``decide_load_more``."""

    def test_load_more_allowed(self):
        """Returns allowed=True when count is below 15 and can_load_more is True."""
        run = _make_run(TODAY, current_page=5, can_load_more=True)
        decision = decide_load_more(search_run=run, user_load_more_actions_today_count=0)
        assert decision.allowed is True
        assert decision.next_page == 6

    def test_next_page_is_current_plus_1(self):
        """next_page must be exactly current_page + 1."""
        run = _make_run(TODAY, current_page=8, can_load_more=True)
        decision = decide_load_more(search_run=run, user_load_more_actions_today_count=5)
        assert decision.next_page == 9

    def test_load_more_blocked_at_daily_limit_15(self):
        """Returns allowed=False when the user has used 15 load-more actions."""
        run = _make_run(TODAY, can_load_more=True)
        decision = decide_load_more(search_run=run, user_load_more_actions_today_count=15)
        assert decision.allowed is False
        assert decision.next_page is None

    def test_load_more_allowed_at_count_14(self):
        """Returns allowed=True at 14 — the boundary just below the limit."""
        run = _make_run(TODAY, can_load_more=True)
        decision = decide_load_more(search_run=run, user_load_more_actions_today_count=14)
        assert decision.allowed is True

    def test_load_more_blocked_by_can_load_more_false(self):
        """Returns allowed=False when the search run signals no more pages."""
        run = _make_run(TODAY, can_load_more=False)
        decision = decide_load_more(search_run=run, user_load_more_actions_today_count=0)
        assert decision.allowed is False
        assert decision.next_page is None


# ---------------------------------------------------------------------------
# decide_date_posted
# ---------------------------------------------------------------------------

class TestDecidesDatePosted:
    """Tests for ``decide_date_posted``."""

    def test_no_previous_run_returns_week(self):
        """With no prior run the date_posted window defaults to 'week'."""
        result = decide_date_posted(today=TODAY, last_search_run=None)
        assert result == "week"

    def test_same_day_run_reuses_existing_date_posted(self):
        """Searching on the same day re-uses the last run's date_posted."""
        run = _make_run(TODAY, date_posted="three_days")
        result = decide_date_posted(today=TODAY, last_search_run=run)
        assert result == "three_days"

    def test_1_day_ago_returns_today(self):
        """A run from yesterday should fetch only today's postings."""
        run = _make_run(date(2025, 6, 10))
        result = decide_date_posted(today=TODAY, last_search_run=run)
        assert result == "today"

    def test_2_days_ago_returns_three_days(self):
        run = _make_run(date(2025, 6, 9))
        result = decide_date_posted(today=TODAY, last_search_run=run)
        assert result == "three_days"

    def test_3_days_ago_returns_three_days(self):
        run = _make_run(date(2025, 6, 8))
        result = decide_date_posted(today=TODAY, last_search_run=run)
        assert result == "three_days"

    def test_4_days_ago_returns_week(self):
        run = _make_run(date(2025, 6, 7))
        result = decide_date_posted(today=TODAY, last_search_run=run)
        assert result == "week"

    def test_7_days_ago_returns_week(self):
        run = _make_run(date(2025, 6, 4))
        result = decide_date_posted(today=TODAY, last_search_run=run)
        assert result == "week"

    def test_8_days_ago_returns_month(self):
        run = _make_run(date(2025, 6, 3))
        result = decide_date_posted(today=TODAY, last_search_run=run)
        assert result == "month"

    def test_30_days_ago_returns_month(self):
        run = _make_run(date(2025, 5, 12))
        result = decide_date_posted(today=TODAY, last_search_run=run)
        assert result == "month"

    def test_31_days_ago_returns_week(self):
        run = _make_run(date(2025, 5, 11))
        result = decide_date_posted(today=TODAY, last_search_run=run)
        assert result == "week"


# ---------------------------------------------------------------------------
# evaluate_primary_search_load_more_availability
# ---------------------------------------------------------------------------

class TestEvaluatePrimaryLoadMoreAvailability:
    """Tests for ``evaluate_primary_search_load_more_availability``."""

    def test_allow_when_total_ge_40_and_new_ge_15(self):
        result = evaluate_primary_search_load_more_availability(
            total_jobs_returned=40, new_jobs_for_user_count=15
        )
        assert result.allow_further_load_more is True

    def test_allow_on_large_result_set(self):
        result = evaluate_primary_search_load_more_availability(
            total_jobs_returned=100, new_jobs_for_user_count=50
        )
        assert result.allow_further_load_more is True

    def test_stop_when_total_below_40(self):
        result = evaluate_primary_search_load_more_availability(
            total_jobs_returned=39, new_jobs_for_user_count=20
        )
        assert result.allow_further_load_more is False

    def test_stop_when_new_below_15(self):
        result = evaluate_primary_search_load_more_availability(
            total_jobs_returned=50, new_jobs_for_user_count=14
        )
        assert result.allow_further_load_more is False

    def test_stop_when_both_below_threshold(self):
        result = evaluate_primary_search_load_more_availability(
            total_jobs_returned=5, new_jobs_for_user_count=2
        )
        assert result.allow_further_load_more is False


# ---------------------------------------------------------------------------
# evaluate_load_more_availability_after_load_more
# ---------------------------------------------------------------------------

class TestEvaluateLoadMoreAfterLoadMore:
    """Tests for ``evaluate_load_more_availability_after_load_more``."""

    def test_allow_when_total_ge_7_and_new_ge_3(self):
        result = evaluate_load_more_availability_after_load_more(
            total_jobs_returned=7, new_jobs_for_user_count=3
        )
        assert result.allow_further_load_more is True

    def test_allow_on_large_result_set(self):
        result = evaluate_load_more_availability_after_load_more(
            total_jobs_returned=20, new_jobs_for_user_count=10
        )
        assert result.allow_further_load_more is True

    def test_stop_when_total_below_7(self):
        result = evaluate_load_more_availability_after_load_more(
            total_jobs_returned=6, new_jobs_for_user_count=5
        )
        assert result.allow_further_load_more is False

    def test_stop_when_new_below_3(self):
        result = evaluate_load_more_availability_after_load_more(
            total_jobs_returned=10, new_jobs_for_user_count=2
        )
        assert result.allow_further_load_more is False

    def test_stop_when_both_below_threshold(self):
        result = evaluate_load_more_availability_after_load_more(
            total_jobs_returned=2, new_jobs_for_user_count=1
        )
        assert result.allow_further_load_more is False
