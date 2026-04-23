from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/placeholder")
def auth_placeholder():
    return {"message": "Auth routes will be added later"}
