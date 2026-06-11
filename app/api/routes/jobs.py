"""Define browser routes for profile-based job search runs and history."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud.application_tracker_entry import list_tracker_entries_for_user
from app.crud.cover_letter import get_completed_drafts_for_user, get_saved_cover_letters_for_user
from app.crud.job_normalization import get_normalization_by_job_id, get_normalizations_for_job_ids
from app.crud.search_profile import get_search_profile_by_id_for_user, get_search_profiles_for_user
from app.crud.search_run import (
    count_load_more_actions_for_user_today,
    count_primary_searches_for_user_today,
    get_latest_search_run_for_profile,
    get_search_run_by_id_for_user,
    get_today_search_run_for_profile_version,
    list_search_runs_for_user
)
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.providers import get_job_search_provider
from app.dependencies.templates import build_feedback_query, get_base_template_context
from app.models.user import User
from app.services.job_normalization_task import NORM_ERRORS, norm_task_key, run_normalization_task
from app.services.job_search_persistence import (
    PersistedSearchResult,
    persist_load_more_response,
    persist_primary_search_response
)
from app.services.job_search_policy import (
    PrimarySearchAction,
    decide_load_more,
    decide_primary_search
)
from app.services.job_search_provider import JobSearchProvider

router = APIRouter(prefix="/jobs", tags=["jobs"])
templates = Jinja2Templates(directory="templates")


def _build_job_search_page_context(
        request: Request,
        *,
        current_user: User,
        search_profiles: list[Any]
) -> dict[str, Any]:
    """Build the template context for the search-profile overview page.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param search_profiles: Search profiles available to the user.
    :return: Template context for the search-profile overview page.
    """
    return {
        **get_base_template_context(request),
        "current_user": current_user,
        "search_profiles": search_profiles
    }


def _build_results_page_context(
        request: Request,
        *,
        current_user: User,
        search_run,
        db: Session,
) -> dict[str, Any]:
    """Build the template context for one persisted search run.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param search_run: Persisted search run with related jobs and profile data.
    :param db: Active database session used for tracker and normalisation lookups.
    :return: Template context for the search-run detail page.
    """
    search_run_jobs = sorted(
        search_run.search_run_jobs,
        key=lambda item: (item.result_position, item.id)
    )

    tracker_entries = list_tracker_entries_for_user(db, user_id=current_user.id)
    tracked_job_map: dict[int, int] = {e.job_id: e.id for e in tracker_entries}

    all_cls = (
        get_saved_cover_letters_for_user(db, user_id=current_user.id)
        + get_completed_drafts_for_user(db, user_id=current_user.id)
    )
    jobs_with_cover_letters: set[int] = {cl.job_id for cl in all_cls if cl.job_id is not None}
    cover_letter_id_map: dict[int, int] = {}
    for cl in all_cls:
        if cl.job_id is not None and cl.job_id not in cover_letter_id_map:
            cover_letter_id_map[cl.job_id] = cl.id

    job_ids = [item.job.id for item in search_run_jobs]
    job_norm_map = get_normalizations_for_job_ids(db, job_ids=job_ids)

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
                "tracker_entry_id": tracked_job_map.get(job.id),
                "has_cover_letter": job.id in jobs_with_cover_letters,
                "cover_letter_id": cover_letter_id_map.get(job.id),
                "normalization": job_norm_map.get(job.id),
            }
        )

    return {
        **get_base_template_context(request),
        "current_user": current_user,
        "search_profile": search_run.search_profile,
        "search_run": search_run,
        "search_results": {
            "results": results,
            "total": len(results)
        },
        "can_load_more": search_run.can_load_more
    }


@router.get("/search", response_class=HTMLResponse, name="render_job_search_page")
def render_job_search_page(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)]
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
            search_profiles=search_profiles
        )
    )


@router.post("/search/{search_profile_id}/run", response_class=HTMLResponse, name="run_job_search")
def run_job_search(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        search_profile_id: int,
        provider: JobSearchProvider = Depends(get_job_search_provider)
) -> RedirectResponse:
    """Start or resume a search run for the selected search profile.

    :param request: Incoming HTTP request.
    :param search_profile_id: Identifier of the selected search profile.
    :param current_user: Authenticated user.
    :param db: Active SQLAlchemy database session.
    :param provider: Job-search provider implementation.
    :return: Redirect response to an existing or newly persisted search run, or a rendered page with an error message.
    """
    search_profile = get_search_profile_by_id_for_user(
        db,
        search_profile_id=search_profile_id,
        user_id=current_user.id
    )

    if search_profile is None:
        search_page_url = str(request.url_for("render_job_search_page"))
        query_string = build_feedback_query(
            message="Suchprofil nicht gefunden.",
            message_type="error"
        )
        return RedirectResponse(
            url=f"{search_page_url}?{query_string}",
            status_code=303
        )

    today = date.today()
    profile_updated_at_snapshot: datetime = (
        search_profile.updated_at or search_profile.created_at or datetime.now(timezone.utc)
    )
    last_search_run = get_latest_search_run_for_profile(
        db,
        user_id=current_user.id,
        search_profile_id=search_profile.id
    )
    today_search_run_current_version = get_today_search_run_for_profile_version(
        db,
        user_id=current_user.id,
        search_profile_id=search_profile.id,
        today=today,
        profile_updated_at_snapshot=profile_updated_at_snapshot
    )

    primary_decision = decide_primary_search(
        today=today,
        search_profile=search_profile,
        last_search_run=last_search_run,
        user_primary_searches_today_count=count_primary_searches_for_user_today(
            db,
            user_id=current_user.id,
            today=today
        ),
        has_today_search_run_for_current_version=today_search_run_current_version is not None
    )

    if primary_decision.action == PrimarySearchAction.SHOW_EXISTING_RUN and today_search_run_current_version is not None:
        results_url = str(request.url_for("render_search_run_detail_page",
                                          search_run_id=today_search_run_current_version.id)
                          )
        query_string = build_feedback_query(
            message="Für dieses Suchprofil wurde heute bereits eine Suche durchgeführt.",
            message_type="info"
        )
        return RedirectResponse(
            url=f"{results_url}?{query_string}",
            status_code=303
        )

    if primary_decision.action == PrimarySearchAction.BLOCKED_DAILY_LIMIT:
        search_page_url = str(request.url_for("render_job_search_page"))
        query_string = build_feedback_query(
            message=primary_decision.message,
            message_type="error"
        )
        return RedirectResponse(
            url=f"{search_page_url}?{query_string}",
            status_code=303
        )

    try:
        search_response = provider.search_jobs(
            search_profile,
            start_page=primary_decision.start_page,
            pages_to_fetch=primary_decision.pages_to_fetch,
            date_posted=primary_decision.date_posted
        )
    except (httpx.RequestError, httpx.HTTPStatusError):
        search_page_url = str(request.url_for("render_job_search_page"))
        query_string = build_feedback_query(
            message="Die Jobsuche konnte nicht durchgeführt werden. Bitte versuche es erneut.",
            message_type="error"
        )
        return RedirectResponse(url=f"{search_page_url}?{query_string}", status_code=303)

    try:
        persisted_result: PersistedSearchResult = persist_primary_search_response(
            db,
            user_id=current_user.id,
            search_profile=search_profile,
            run_date=today,
            profile_updated_at_snapshot=profile_updated_at_snapshot,
            date_posted=primary_decision.date_posted,
            loaded_page=primary_decision.loaded_page,
            search_response=search_response
        )
    except IntegrityError:
        # A concurrent request already committed a run for this profile+version today.
        concurrent_run = get_today_search_run_for_profile_version(
            db,
            user_id=current_user.id,
            search_profile_id=search_profile.id,
            today=today,
            profile_updated_at_snapshot=profile_updated_at_snapshot
        )
        if concurrent_run is not None:
            return RedirectResponse(
                url=str(request.url_for("render_search_run_detail_page",
                                        search_run_id=concurrent_run.id)),
                status_code=303
            )
        raise

    results_url = str(request.url_for("render_search_run_detail_page",
                                      search_run_id=persisted_result.search_run.id)
                      )
    return RedirectResponse(url=results_url, status_code=303)


@router.get("/runs/{search_run_id}", response_class=HTMLResponse, name="render_search_run_detail_page")
def render_search_run_detail_page(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        search_run_id: int
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
        user_id=current_user.id
    )

    if search_run is None:
        search_page_url = str(request.url_for("render_job_search_page"))
        query_string = build_feedback_query(
            message="Suchlauf nicht gefunden.",
            message_type="error"
        )
        return RedirectResponse(
            url=f"{search_page_url}?{query_string}",
            status_code=303
        )

    return templates.TemplateResponse(
        request=request,
        name="job_results.html",
        context=_build_results_page_context(
            request,
            current_user=current_user,
            search_run=search_run,
            db=db,
        )
    )


@router.post("/runs/{search_run_id}/load-more", response_class=HTMLResponse, name="load_more_search_run_results")
def load_more_search_run_results(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        search_run_id: int,
        provider: JobSearchProvider = Depends(get_job_search_provider)
) -> RedirectResponse:
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
        user_id=current_user.id
    )

    if search_run is None:
        search_page_url = str(request.url_for("render_job_search_page"))
        query_string = build_feedback_query(
            message="Suchlauf nicht gefunden.",
            message_type="error"
        )
        return RedirectResponse(
            url=f"{search_page_url}?{query_string}",
            status_code=303
        )

    load_more_decision = decide_load_more(
        search_run=search_run,
        user_load_more_actions_today_count=count_load_more_actions_for_user_today(
            db,
            user_id=current_user.id,
            today=date.today()
        )
    )

    if not load_more_decision.allowed:
        results_url = str(
            request.url_for(
                "render_search_run_detail_page",
                search_run_id=search_run.id
            )
        )
        query_string = build_feedback_query(
            message=load_more_decision.message,
            message_type="error"
        )
        return RedirectResponse(
            url=f"{results_url}?{query_string}",
            status_code=303
        )

    try:
        search_response = provider.search_jobs(
            search_run.search_profile,
            start_page=load_more_decision.next_page,
            pages_to_fetch=load_more_decision.pages_to_fetch,
            date_posted=search_run.date_posted
        )
    except (httpx.RequestError, httpx.HTTPStatusError):
        results_url = str(request.url_for("render_search_run_detail_page",
                                          search_run_id=search_run.id))
        query_string = build_feedback_query(
            message="Die Ergebnisse konnten nicht geladen werden. Bitte versuche es erneut.",
            message_type="error"
        )
        return RedirectResponse(url=f"{results_url}?{query_string}", status_code=303)

    persisted_result = persist_load_more_response(
        db,
        user_id=current_user.id,
        search_run=search_run,
        loaded_page=load_more_decision.next_page,
        search_response=search_response
    )

    results_url = str(request.url_for("render_search_run_detail_page",
                                      search_run_id=persisted_result.search_run.id)
                      )

    if persisted_result.total_jobs_in_response == 0:
        query_string = build_feedback_query(
            message="Keine weiteren Ergebnisse gefunden. Bitte versuche es morgen erneut oder nutze ein anderes Suchprofil.",
            message_type="info"
        )
        return RedirectResponse(url=f"{results_url}?{query_string}", status_code=303)

    first_new_position = (
        persisted_result.search_run.total_jobs_loaded - persisted_result.total_jobs_in_response + 1
    )
    return RedirectResponse(url=f"{results_url}#job-{first_new_position}", status_code=303)


@router.get("/runs", response_class=HTMLResponse, name="render_search_run_history_page")
def render_search_run_history_page(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        search_profile_id: Annotated[int | None, Query()] = None
) -> Response:
    """Render the search-run history page, optionally filtered by search profile.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active SQLAlchemy database session.
    :param search_profile_id: Optional identifier used to filter the history by search profile.
    :return: Rendered search-run history page.
    """
    search_profiles = get_search_profiles_for_user(db, user_id=current_user.id)

    if search_profile_id is not None:
        has_matching_profile = any(
            profile.id == search_profile_id for profile in search_profiles
        )
        if not has_matching_profile:
            history_url = str(request.url_for("render_search_run_history_page"))
            query_string = build_feedback_query(
                message="Suchprofil nicht gefunden.",
                message_type="error"
            )
            return RedirectResponse(
                url=f"{history_url}?{query_string}",
                status_code=303
            )

    search_runs = list_search_runs_for_user(
        db,
        user_id=current_user.id,
        search_profile_id=search_profile_id
    )

    return templates.TemplateResponse(
        request=request,
        name="search_run_history.html",
        context={
            **get_base_template_context(request),
            "current_user": current_user,
            "search_runs": search_runs,
            "search_profiles": search_profiles,
            "selected_search_profile_id": search_profile_id
        }
    )


@router.post("/{job_id}/analyse", response_class=HTMLResponse, name="analyse_job_for_results_action")
def analyse_job_for_results_route(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        background_tasks: BackgroundTasks,
        job_id: int,
) -> Response:
    """Trigger job normalisation from a search-results job card.

    If normalisation already exists, returns the completed section partial
    immediately. Otherwise enqueues a background task and returns a spinner
    partial that polls for completion.

    :param request: Incoming HTTP request.
    :param job_id: Identifier of the job to analyse.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param background_tasks: FastAPI background task queue.
    :return: Spinner or completed analysis partial.
    """
    existing_norm = get_normalization_by_job_id(db, job_id=job_id)
    if existing_norm is not None:
        return templates.TemplateResponse(
            request=request,
            name="_job_analyse_done.html",
            context={"job_id": job_id, "normalization": existing_norm.normalized_data},
        )

    NORM_ERRORS.pop(norm_task_key(job_id, None), None)
    background_tasks.add_task(run_normalization_task, job_id=job_id, manual_job_id=None)

    status_url = str(request.url_for("job_analyse_status_for_results", job_id=job_id))
    return templates.TemplateResponse(
        request=request,
        name="_job_analyse_spinner.html",
        context={"job_id": job_id, "status_url": status_url},
    )


@router.get("/{job_id}/analyse/status", response_class=HTMLResponse, name="job_analyse_status_for_results")
def job_analyse_status_for_results_route(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        job_id: int,
) -> Response:
    """HTMX polling endpoint: check normalisation progress for a search-results job.

    Returns the spinner partial while the background task is still running.
    Returns the completed analysis partial when normalisation finishes.
    Returns an error snippet on failure.

    :param request: Incoming HTTP request.
    :param job_id: Identifier of the job being analysed.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: Spinner partial, completed partial, or error HTML.
    """
    key = norm_task_key(job_id, None)

    if key in NORM_ERRORS:
        error_msg = NORM_ERRORS.pop(key)
        return HTMLResponse(content=f'<div id="job-analyse-{job_id}" class="mt-2 text-sm text-red-600">Fehler bei der Analyse: {error_msg}</div>')

    existing_norm = get_normalization_by_job_id(db, job_id=job_id)
    if existing_norm is not None:
        return templates.TemplateResponse(
            request=request,
            name="_job_analyse_done.html",
            context={"job_id": job_id, "normalization": existing_norm.normalized_data},
        )

    status_url = str(request.url_for("job_analyse_status_for_results", job_id=job_id))
    return templates.TemplateResponse(
        request=request,
        name="_job_analyse_spinner.html",
        context={"job_id": job_id, "status_url": status_url},
    )
