from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import workspace_identity
from app.core.database import get_db
from app.schemas.common import Envelope
from app.services import analytics
from app.services.auth import Identity

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("", response_model=Envelope[dict])
def report(days: int = Query(30, ge=1, le=90), identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[dict]:
    return Envelope(data=analytics.report(db, identity, days))
