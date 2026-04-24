from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
def render_index_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )
