from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_client, workspace_identity
from app.core.database import get_db
from app.schemas.ai import AnalyseRecentIn, AnalyseRecentOut, AiSettingsIn, AiSettingsOut, AiStatus, AnalysisOut, ReplyApprove, ReplyEdit, ReplyOut, WriteIn, WriteOut
from app.schemas.common import Envelope
from app.services import ai_triage
from app.services.auth import Client, Identity

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status", response_model=Envelope[AiStatus])
def status(identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[AiStatus]:
    return Envelope(data=AiStatus(**ai_triage.status(db, identity)))


@router.get("/settings", response_model=Envelope[AiSettingsOut])
def get_settings(identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[AiSettingsOut]:
    return Envelope(data=AiSettingsOut(**ai_triage.get_settings_view(db, identity)))


@router.put("/settings", response_model=Envelope[AiSettingsOut])
def update_settings(body: AiSettingsIn, identity: Identity = Depends(workspace_identity), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[AiSettingsOut]:
    return Envelope(data=AiSettingsOut(**ai_triage.update_settings(db, identity, body.enabled, body.paused, body.business_info, body.mailboxes, client, body.auto_send_low, body.auto_send_medium, body.daily_limit, body.mailbox_auto_send)))


@router.get("/activity", response_model=Envelope[list[AnalysisOut]])
def activity(limit: int = Query(50, ge=1, le=200), identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[list[AnalysisOut]]:
    return Envelope(data=[AnalysisOut(**row) for row in ai_triage.activity(db, identity, limit)])


@router.get("/conversations/{conversation_id}", response_model=Envelope[AnalysisOut | None])
def for_conversation(conversation_id: int, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[AnalysisOut | None]:
    row = ai_triage.for_conversation(db, identity, conversation_id)
    return Envelope(data=AnalysisOut(**row) if row else None)


@router.post("/conversations/{conversation_id}/analyse", response_model=Envelope[AnalysisOut])
def analyse(conversation_id: int, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[AnalysisOut]:
    return Envelope(data=AnalysisOut(**ai_triage.analyse_now(db, identity, conversation_id)))


@router.post("/analyse-recent", response_model=Envelope[AnalyseRecentOut])
def analyse_recent(body: AnalyseRecentIn, identity: Identity = Depends(workspace_identity), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[AnalyseRecentOut]:
    return Envelope(data=AnalyseRecentOut(**ai_triage.analyse_recent(db, identity, body.per_mailbox, client)))


@router.post("/write", response_model=Envelope[WriteOut])
def write(body: WriteIn, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[WriteOut]:
    return Envelope(data=WriteOut(**ai_triage.write_with_ai(db, identity, body.instruction, body.current, body.conversation_id)))


@router.get("/replies", response_model=Envelope[list[ReplyOut]])
def list_replies(which: str = Query("waiting", pattern="^(waiting|sent|rejected)$"), limit: int = Query(50, ge=1, le=200), identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[list[ReplyOut]]:
    return Envelope(data=[ReplyOut(**row) for row in ai_triage.list_replies(db, identity, which, limit)])


@router.put("/replies/{reply_id}", response_model=Envelope[ReplyOut])
def edit_reply(reply_id: int, body: ReplyEdit, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[ReplyOut]:
    return Envelope(data=ReplyOut(**ai_triage.edit_reply(db, identity, reply_id, body.body)))


@router.post("/replies/{reply_id}/approve", response_model=Envelope[ReplyOut])
def approve(reply_id: int, body: ReplyApprove, identity: Identity = Depends(workspace_identity), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[ReplyOut]:
    return Envelope(data=ReplyOut(**ai_triage.approve_and_send(db, identity, reply_id, body.body_hash, client)))


@router.post("/replies/{reply_id}/reject", response_model=Envelope[ReplyOut])
def reject(reply_id: int, identity: Identity = Depends(workspace_identity), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[ReplyOut]:
    return Envelope(data=ReplyOut(**ai_triage.reject_reply(db, identity, reply_id, client)))
