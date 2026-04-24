from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/jobs", tags=["jobs"])
templates = Jinja2Templates(directory="templates")


@router.get("/search", response_class=HTMLResponse)
def render_job_search_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="job_search.html",
        context={}
    )


@router.post("/search", response_class=HTMLResponse)
def submit_job_search(
    request: Request,
    query: Annotated[str, Form(...)],
    location: Annotated[str | None, Form()] = None,
    work_model: Annotated[list[str] | None, Form()] = None,
    employment_type: Annotated[list[str] | None, Form()] = None,
    experience_level: Annotated[str | None, Form()] = None,
    company: Annotated[str | None, Form()] = None,
    industry: Annotated[list[str] | None, Form()] = None
):
    search_data = {
        "query": query,
        "location": location,
        "work_model": work_model or [],
        "employment_type": employment_type or [],
        "experience_level": experience_level,
        "company": company,
        "industry": industry or []
    }

    return templates.TemplateResponse(
        request=request,
        name="job_results.html",
        context={"search_data": search_data}
    )
