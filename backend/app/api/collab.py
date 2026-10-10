from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import workspace_identity
from app.core.database import get_db
from app.repositories import collab as repo
from app.schemas.collab import (
    ContactOut,
    DraftIn,
    DraftOut,
    MarkReadIn,
    NoteIn,
    NoteOut,
    NotificationOut,
    NotificationsOut,
    RecentNoteOut,
    TemplateIn,
    TemplateOut,
)
from app.schemas.common import Envelope
from app.services import collab, mailbox_access
from app.services.auth import Identity

router = APIRouter(tags=["collaboration"])


def _draft_out(draft, account_email: str) -> DraftOut:
    return DraftOut(
        id=draft.id, email_account_id=draft.email_account_id, account_email=account_email, mode=draft.mode, conversation_id=draft.conversation_id,
        in_reply_to=draft.in_reply_to, forward_of_message_id=draft.forward_of_message_id, to=draft.to_addresses, cc=draft.cc_addresses, bcc=draft.bcc_addresses,
        subject=draft.subject, body_text=draft.body_text or "", updated_at=draft.updated_at,
    )


def note_out(note, names: dict[int, str], identity: Identity) -> NoteOut:
    return NoteOut(id=note.id, conversation_id=note.conversation_id, author_user_id=note.author_user_id, author_name=names.get(note.author_user_id),
                   is_yours=note.author_user_id == identity.user.id, body=note.body, created_at=note.created_at)


@router.get("/drafts", response_model=Envelope[list[DraftOut]])
def list_drafts(identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[list[DraftOut]]:
    allowed = mailbox_access.allowed_account_ids(db, identity)
    rows = repo.list_drafts(db, identity.workspace.id, identity.user.id)
    return Envelope(data=[_draft_out(draft, account.email_address) for draft, account in rows if allowed is None or account.id in allowed])


@router.post("/drafts", response_model=Envelope[DraftOut], status_code=201)
def create_draft(body: DraftIn, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[DraftOut]:
    draft = collab.create_draft(db, identity, body)
    return Envelope(data=_draft_out(draft, dict((a.id, a.email_address) for _d, a in repo.list_drafts(db, identity.workspace.id, identity.user.id)).get(draft.email_account_id, "")))


@router.put("/drafts/{draft_id}", response_model=Envelope[DraftOut])
def update_draft(draft_id: int, body: DraftIn, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[DraftOut]:
    draft = collab.update_draft(db, identity, draft_id, body)
    return Envelope(data=_draft_out(draft, dict((a.id, a.email_address) for _d, a in repo.list_drafts(db, identity.workspace.id, identity.user.id)).get(draft.email_account_id, "")))


@router.delete("/drafts/{draft_id}", status_code=204)
def delete_draft(draft_id: int, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> None:
    collab.delete_draft(db, identity, draft_id)


@router.post("/conversations/{conversation_id}/notes", response_model=Envelope[NoteOut], status_code=201)
def add_note(conversation_id: int, body: NoteIn, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[NoteOut]:
    note = collab.add_note(db, identity, conversation_id, body.body)
    return Envelope(data=note_out(note, {identity.user.id: identity.user.name}, identity))


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> None:
    collab.delete_note(db, identity, note_id)


@router.get("/notes", response_model=Envelope[list[RecentNoteOut]])
def recent_notes(limit: int = Query(50, ge=1, le=200), identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[list[RecentNoteOut]]:
    rows = repo.recent_notes(db, identity.workspace.id, mailbox_access.allowed_account_ids(db, identity), limit)
    names = repo.user_names(db, {note.author_user_id for note, _ in rows if note.author_user_id})
    return Envelope(data=[RecentNoteOut(**note_out(note, names, identity).model_dump(), conversation_subject=conversation.subject) for note, conversation in rows])


@router.get("/notifications", response_model=Envelope[NotificationsOut])
def list_notifications(limit: int = Query(50, ge=1, le=200), identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[NotificationsOut]:
    rows = repo.list_notifications(db, identity.workspace.id, identity.user.id, limit)
    names = repo.user_names(db, {n.actor_user_id for n in rows if n.actor_user_id})
    return Envelope(data=NotificationsOut(
        unread=repo.unread_notifications(db, identity.workspace.id, identity.user.id),
        items=[NotificationOut(id=n.id, kind=n.kind, title=n.title, body=n.body, conversation_id=n.conversation_id, actor_name=names.get(n.actor_user_id), is_read=n.read_at is not None, created_at=n.created_at) for n in rows],
    ))


@router.get("/notifications/email", response_model=Envelope[dict])
def email_preference(identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[dict]:
    from app.services import notify_email

    return Envelope(data=notify_email.preference(db, identity))


@router.put("/notifications/email", response_model=Envelope[dict])
def set_email_preference(body: dict, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[dict]:
    from app.core.errors import AppError
    from app.services import notify_email

    if not isinstance(body.get("enabled"), bool):
        raise AppError(422, "VALIDATION_ERROR", "Say whether email notifications should be on or off.")
    return Envelope(data=notify_email.set_preference(db, identity, body["enabled"]))


@router.post("/notifications/read", status_code=204)
def mark_read(body: MarkReadIn, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> None:
    collab.mark_read(db, identity, body.ids)


@router.get("/contacts", response_model=Envelope[list[ContactOut]])
def list_contacts(
    search: str | None = Query(None, max_length=200), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db),
) -> Envelope[list[ContactOut]]:
    rows, _total = collab.list_contacts(db, identity, search, limit, offset)
    return Envelope(data=[ContactOut(**row) for row in rows])


def _template_out(template, names: dict[int, str]) -> TemplateOut:
    return TemplateOut(id=template.id, name=template.name, subject=template.subject, body=template.body, created_by_name=names.get(template.created_by_user_id), updated_at=template.updated_at)


@router.get("/templates", response_model=Envelope[list[TemplateOut]])
def list_templates(identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[list[TemplateOut]]:
    rows = repo.list_templates(db, identity.workspace.id)
    names = repo.user_names(db, {t.created_by_user_id for t in rows if t.created_by_user_id})
    return Envelope(data=[_template_out(t, names) for t in rows])


@router.post("/templates", response_model=Envelope[TemplateOut], status_code=201)
def create_template(body: TemplateIn, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[TemplateOut]:
    return Envelope(data=_template_out(collab.create_template(db, identity, body), {identity.user.id: identity.user.name}))


@router.put("/templates/{template_id}", response_model=Envelope[TemplateOut])
def update_template(template_id: int, body: TemplateIn, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[TemplateOut]:
    template = collab.update_template(db, identity, template_id, body)
    return Envelope(data=_template_out(template, repo.user_names(db, {template.created_by_user_id} if template.created_by_user_id else set())))


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: int, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> None:
    collab.delete_template(db, identity, template_id)
