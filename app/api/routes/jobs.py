from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.schemas.job_search import JobSearchFilters
from app.services.fixture_job_search_provider import FixtureJobSearchProvider
from app.services.job_search_provider import JobSearchProvider

router = APIRouter(prefix="/jobs", tags=["jobs"])
templates = Jinja2Templates(directory="templates")


def get_job_search_provider() -> JobSearchProvider:
    return FixtureJobSearchProvider()


def _build_form_data(
    query: str = "",
    location: str = "Deutschland",
    work_model: list[str] | None = None,
    employment_type: list[str] | None = None,
    experience_level: str | None = None,
    company: str | None = None,
    industry: list[str] | None = None,
) -> dict[str, str | list[str]]:
    return {
        "query": query,
        "location": location,
        "work_model": work_model or [],
        "employment_type": employment_type or [],
        "experience_level": experience_level or "",
        "company": company or "",
        "industry": industry or [],
    }


def _build_search_filters(
    query: str,
    location: str,
    work_model: list[str] | None = None,
    employment_type: list[str] | None = None,
    experience_level: str | None = None,
    company: str | None = None,
    industry: list[str] | None = None,
) -> JobSearchFilters:
    return JobSearchFilters(
        query=query,
        location=location,
        work_model=work_model or [],
        employment_type=employment_type or [],
        experience_level=experience_level.strip() if experience_level else None,
        company=company.strip() if company else None,
        industry=industry or [],
    )


def _build_results_redirect_url(request: Request, search_data: JobSearchFilters) -> str:
    params: list[tuple[str, str]] = [
        ("query", search_data.query),
        ("location", search_data.location),
    ]

    for item in search_data.work_model:
        params.append(("work_model", item))

    for item in search_data.employment_type:
        params.append(("employment_type", item))

    if search_data.experience_level:
        params.append(("experience_level", search_data.experience_level))

    if search_data.company:
        params.append(("company", search_data.company))

    for item in search_data.industry:
        params.append(("industry", item))

    base_url = str(request.url_for("render_job_results_page"))
    return f"{base_url}?{urlencode(params, doseq=True)}"


@router.get("/search", response_class=HTMLResponse, name="render_job_search_page")
def render_job_search_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="job_search.html",
        context={
            "errors": {},
            "form_data": _build_form_data(),
        },
    )


@router.post("/search", response_class=HTMLResponse)
def submit_job_search(
    request: Request,
    query: Annotated[str, Form()],
    location: Annotated[str, Form()],
    work_model: Annotated[list[str] | None, Form()] = None,
    employment_type: Annotated[list[str] | None, Form()] = None,
    experience_level: Annotated[str | None, Form()] = None,
    company: Annotated[str | None, Form()] = None,
    industry: Annotated[list[str] | None, Form()] = None,
):
    form_data = _build_form_data(
        query=query,
        location=location,
        work_model=work_model,
        employment_type=employment_type,
        experience_level=experience_level,
        company=company,
        industry=industry,
    )

    try:
        search_data = _build_search_filters(
            query=query,
            location=location,
            work_model=work_model,
            employment_type=employment_type,
            experience_level=experience_level,
            company=company,
            industry=industry,
        )
    except ValidationError as e:
        errors: dict[str, str] = {}

        for error in e.errors():
            field_name = error["loc"][0]

            if field_name == "query":
                errors["query"] = "Bitte gib einen Suchbegriff ein."
            elif field_name == "location":
                errors["location"] = "Bitte gib einen Ort ein."

        return templates.TemplateResponse(
            request=request,
            name="job_search.html",
            context={
                "errors": errors,
                "form_data": form_data,
            },
            status_code=422,
        )

    redirect_url = _build_results_redirect_url(request, search_data)
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/results", response_class=HTMLResponse, name="render_job_results_page")
def render_job_results_page(
    request: Request,
    query: Annotated[str, Query()],
    location: Annotated[str, Query()],
    work_model: Annotated[list[str] | None, Query()] = None,
    employment_type: Annotated[list[str] | None, Query()] = None,
    experience_level: Annotated[str | None, Query()] = None,
    company: Annotated[str | None, Query()] = None,
    industry: Annotated[list[str] | None, Query()] = None,
    provider: JobSearchProvider = Depends(get_job_search_provider),
):
    try:
        search_data = _build_search_filters(
            query=query,
            location=location,
            work_model=work_model,
            employment_type=employment_type,
            experience_level=experience_level,
            company=company,
            industry=industry,
        )
    except ValidationError:
        return RedirectResponse(
            url=str(request.url_for("render_job_search_page")),
            status_code=303,
        )

    search_results = provider.search_jobs(search_data)

    return templates.TemplateResponse(
        request=request,
        name="job_results.html",
        context={
            "search_data": search_data.model_dump(),
            "search_results": search_results.model_dump(),
        },
    )