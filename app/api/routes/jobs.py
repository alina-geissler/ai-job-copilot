"""Define browser routes for profile-based job search runs and history."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.crud.search_profile import get_search_profiles_for_user
from app.crud.search_run import (
    count_load_more_actions_for_user_today,
    count_primary_searches_for_user_today,
    get_latest_search_run_for_profile,
    get_search_run_by_id_for_user,
    get_today_search_run_for_profile,
    list_search_runs_for_user,
)
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.providers import get_job_search_provider
from app.dependencies.templates import get_base_template_context
from app.models.user import User
from app.services.job_search_persistence import (
    PersistedSearchResult,
    persist_load_more_response,
    persist_primary_search_response,
)
from app.services.job_search_policy import (
    PrimarySearchAction,
    decide_load_more,
    decide_primary_search,
)
from app.services.job_search_provider import JobSearchProvider

router = APIRouter(prefix="/jobs", tags=["jobs"])
templates = Jinja2Templates(directory="templates")


def _build_job_search_page_context(
    request: Request,
    *,
    current_user: User,
    search_profiles: list[Any],
    page_message: str | None = None,
) -> dict[str, Any]:
    """Build the template context for the search-profile overview page.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param search_profiles: Search profiles available to the user.
    :param page_message: Optional page-level feedback message.
    :return: Template context for the search-profile overview page.
    """
    return {
        **get_base_template_context(request),
        "current_user": current_user,
        "search_profiles": search_profiles,
        "page_message": page_message,
    }


def _build_results_page_context(
    request: Request,
    *,
    current_user: User,
    search_run,
    page_message: str | None = None,
) -> dict[str, Any]:
    """Build the template context for one persisted search run.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param search_run: Persisted search run with related jobs and profile data.
    :param page_message: Optional page-level feedback message.
    :return: Template context for the search-run detail page.
    """
    search_run_jobs = sorted(
        search_run.search_run_jobs,
        key=lambda item: (item.result_position, item.id),
    )

    results = []
    for item in search_run_jobs:
        job = item.job
        results.append(
            {
                "id": job.id,
                "external_job_id": job.external_job_id,
                "source": job.source,
                "title": job.title,
                "company": job.company,
                "company_logo": job.company_logo,
                "location": job.location,
                "is_remote": job.is_remote,
                "employment_type": job.employment_type,
                "job_url": job.job_url,
                "description": job.description,
                "published_at": job.published_at,
                "is_previously_seen": item.is_previously_seen,
                "page_number": item.page_number,
                "result_position": item.result_position,
            }
        )

    return {
        **get_base_template_context(request),
        "current_user": current_user,
        "search_profile": search_run.search_profile,
        "search_run": search_run,
        "search_results": {
            "results": results,
            "total": len(results),
        },
        "page_message": page_message,
        "can_load_more": search_run.can_load_more,
    }


@router.get("/search", response_class=HTMLResponse, name="render_job_search_page")
def render_job_search_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HTMLResponse:
    """Render the search-profile overview page.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active SQLAlchemy database session.
    :return: Rendered job-search overview page.
    """
    search_profiles = get_search_profiles_for_user(db, user_id=current_user.id)

    return templates.TemplateResponse(
        request=request,
        name="job_search.html",
        context=_build_job_search_page_context(
            request,
            current_user=current_user,
            search_profiles=search_profiles,
            page_message=request.query_params.get("message"),
        ),
    )


@router.post("/search/{search_profile_id}/run", response_class=HTMLResponse, name="run_job_search")
def run_job_search(
    request: Request,
    search_profile_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    provider: JobSearchProvider = Depends(get_job_search_provider),
) -> Response:
    """Start or resume a search run for the selected search profile.

    :param request: Incoming HTTP request.
    :param search_profile_id: Identifier of the selected search profile.
    :param current_user: Authenticated user.
    :param db: Active SQLAlchemy database session.
    :param provider: Job-search provider implementation.
    :return: Redirect response to an existing or newly persisted search run, or a rendered page with an error message.
    """
    from app.crud.search_profile import get_search_profile_by_id_for_user

    search_profile = get_search_profile_by_id_for_user(
        db,
        search_profile_id=search_profile_id,
        user_id=current_user.id,
    )
    if search_profile is None:
        return RedirectResponse(
            url=str(request.url_for("render_job_search_page")),
            status_code=303,
        )

    today = date.today()
    last_search_run = get_latest_search_run_for_profile(
        db,
        user_id=current_user.id,
        search_profile_id=search_profile.id,
    )
    today_search_run = get_today_search_run_for_profile(
        db,
        user_id=current_user.id,
        search_profile_id=search_profile.id,
        today=today,
    )

    primary_decision = decide_primary_search(
        today=today,
        search_profile=search_profile,
        last_search_run=last_search_run,
        user_primary_searches_today_count=count_primary_searches_for_user_today(
            db,
            user_id=current_user.id,
            today=today,
        ),
        has_primary_search_for_profile_today=today_search_run is not None,
    )

    if primary_decision.action == PrimarySearchAction.SHOW_EXISTING_RUN and today_search_run is not None:
        return RedirectResponse(
            url=str(
                request.url_for(
                    "render_search_run_detail_page",
                    search_run_id=today_search_run.id,
                )
            ),
            status_code=303,
        )

    if primary_decision.action in {
        PrimarySearchAction.BLOCKED_DAILY_LIMIT,
        PrimarySearchAction.BLOCKED_PROFILE_LIMIT,
    }:
        search_profiles = get_search_profiles_for_user(db, user_id=current_user.id)
        return templates.TemplateResponse(
            request=request,
            name="job_search.html",
            context=_build_job_search_page_context(
                request,
                current_user=current_user,
                search_profiles=search_profiles,
                page_message=primary_decision.message,
            ),
            status_code=409,
        )

    search_response = provider.search_jobs(
        search_profile,
        start_page=primary_decision.start_page,
        pages_to_fetch=primary_decision.pages_to_fetch,
        date_posted=primary_decision.date_posted,
    )

    persisted_result: PersistedSearchResult = persist_primary_search_response(
        db,
        user_id=current_user.id,
        search_profile=search_profile,
        run_date=today,
        date_posted=primary_decision.date_posted,
        loaded_page=primary_decision.loaded_page,
        search_response=search_response,
    )

    return RedirectResponse(
        url=str(
            request.url_for(
                "render_search_run_detail_page",
                search_run_id=persisted_result.search_run.id,
            )
        ),
        status_code=303,
    )


@router.get("/runs/{search_run_id}", response_class=HTMLResponse, name="render_search_run_detail_page")
def render_search_run_detail_page(
    request: Request,
    search_run_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Render the persisted detail page of one search run.

    :param request: Incoming HTTP request.
    :param search_run_id: Identifier of the search run to display.
    :param current_user: Authenticated user.
    :param db: Active SQLAlchemy database session.
    :return: Rendered search-run detail page or redirect response.
    """
    search_run = get_search_run_by_id_for_user(
        db,
        search_run_id=search_run_id,
        user_id=current_user.id,
    )
    if search_run is None:
        return RedirectResponse(
            url=str(request.url_for("render_job_search_page")),
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="job_results.html",
        context=_build_results_page_context(
            request,
            current_user=current_user,
            search_run=search_run,
        ),
    )


@router.post("/runs/{search_run_id}/load-more", response_class=HTMLResponse, name="load_more_search_run_results")
def load_more_search_run_results(
    request: Request,
    search_run_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    provider: JobSearchProvider = Depends(get_job_search_provider),
) -> Response:
    """Load one more provider page into an existing search run.

    :param request: Incoming HTTP request.
    :param search_run_id: Identifier of the search run to extend.
    :param current_user: Authenticated user.
    :param db: Active SQLAlchemy database session.
    :param provider: Job-search provider implementation.
    :return: Redirect response to the updated search run, or a rendered page with an error message.
    """
    search_run = get_search_run_by_id_for_user(
        db,
        search_run_id=search_run_id,
        user_id=current_user.id,
    )
    if search_run is None:
        return RedirectResponse(
            url=str(request.url_for("render_job_search_page")),
            status_code=303,
        )

    load_more_decision = decide_load_more(
        search_run=search_run,
        user_load_more_actions_today_count=count_load_more_actions_for_user_today(
            db,
            user_id=current_user.id,
            today=date.today(),
        ),
    )

    if not load_more_decision.allowed:
        return templates.TemplateResponse(
            request=request,
            name="job_results.html",
            context=_build_results_page_context(
                request,
                current_user=current_user,
                search_run=search_run,
                page_message=load_more_decision.message,
            ),
            status_code=409,
        )

    search_response = provider.search_jobs(
        search_run.search_profile,
        start_page=load_more_decision.next_page,
        pages_to_fetch=load_more_decision.pages_to_fetch,
        date_posted=search_run.date_posted,
    )

    persisted_result = persist_load_more_response(
        db,
        user_id=current_user.id,
        search_run=search_run,
        loaded_page=load_more_decision.next_page,
        search_response=search_response,
    )

    return RedirectResponse(
        url=str(
            request.url_for(
                "render_search_run_detail_page",
                search_run_id=persisted_result.search_run.id,
            )
        ),
        status_code=303,
    )


@router.get("/runs", response_class=HTMLResponse, name="render_search_run_history_page")
def render_search_run_history_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    search_profile_id: Annotated[int | None, Query()] = None,
) -> HTMLResponse:
    """Render the search-run history page, optionally filtered by search profile.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active SQLAlchemy database session.
    :param search_profile_id: Optional identifier used to filter the history by search profile.
    :return: Rendered search-run history page.
    """
    search_runs = list_search_runs_for_user(
        db,
        user_id=current_user.id,
        search_profile_id=search_profile_id,
    )
    search_profiles = get_search_profiles_for_user(db, user_id=current_user.id)

    return templates.TemplateResponse(
        request=request,
        name="search_run_history.html",
        context={
            **get_base_template_context(request),
            "current_user": current_user,
            "search_runs": search_runs,
            "search_profiles": search_profiles,
            "selected_search_profile_id": search_profile_id,
        },
    )