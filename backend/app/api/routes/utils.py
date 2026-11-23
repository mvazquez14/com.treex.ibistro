from fastapi import APIRouter, HTTPException

from app.core.redis import ping_redis

router = APIRouter(prefix="/utils", tags=["utils"])


@router.get("/health-check/")
async def health_check() -> bool:
    try:
        ok = await ping_redis()
    except Exception:
        ok = False
    if not ok:
        raise HTTPException(status_code=503, detail=False)
    return True
