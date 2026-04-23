from fastapi import FastAPI
from app.api.routes.health import router as health_router
from app.api.routes.auth import router as auth_router

app = FastAPI(title="AI Job Match & Application Copilot")

app.include_router(health_router)
app.include_router(auth_router)
