from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import workspace_identity
from app.core.database import get_db
from app.schemas.common import Envelope
from app.schemas.reminders import ReminderIn, ReminderOut
from app.services import reminders
from app.services.auth import Identity

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("", response_model=Envelope[list[ReminderOut]])
def list_reminders(conversation_id: int | None = Query(None), identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[list[ReminderOut]]:
    return Envelope(data=[ReminderOut(**row) for row in reminders.mine(db, identity, conversation_id)])


@router.post("", response_model=Envelope[ReminderOut], status_code=201)
def create_reminder(body: ReminderIn, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[ReminderOut]:
    return Envelope(data=ReminderOut(**reminders.create(db, identity, body.conversation_id, body.due_at, body.note, body.only_if_no_reply)))


@router.delete("/{reminder_id}", status_code=204)
def cancel_reminder(reminder_id: int, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> None:
    reminders.cancel(db, identity, reminder_id)
