from fastapi import APIRouter, Depends

from app.core.security import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/status")
async def admin_status() -> dict[str, str]:
    return {"status": "ready"}
