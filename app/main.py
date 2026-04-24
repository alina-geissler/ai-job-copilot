from fastapi import FastAPI
from app.api.routes.health import router as health_router
from app.api.routes.auth import router as auth_router
from app.api.routes.pages import router as pages_router
from app.api.routes.jobs import router as jobs_router

app = FastAPI(title="AI Job Match & Application Copilot")

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(pages_router)
app.include_router(jobs_router)