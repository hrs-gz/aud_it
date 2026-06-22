from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas import HardResetResponse
from backend.services.reset import hard_reset_app

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/hard-reset", response_model=HardResetResponse)
def post_hard_reset(db: Session = Depends(get_db)):
    return HardResetResponse(**hard_reset_app(db))
