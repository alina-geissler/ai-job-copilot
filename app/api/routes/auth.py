from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
def auth_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth.html",
        context={}
    )
