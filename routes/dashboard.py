from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def dashboard_health():
    return {"status": "ok"}
