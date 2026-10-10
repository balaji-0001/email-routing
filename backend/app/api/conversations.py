from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_client, workspace_identity
from app.core.database import get_db
from app.core.errors import AppError
from app.api.collab import note_out
from app.repositories import collab as collab_repo
from app.repositories import conversations as conv_repo
from app.schemas.common import Envelope
from app.schemas.conversations import (
    AttachmentOut,
    BatchConversationIn,
    ConversationDetailOut,
    ConversationOut,
    LabelIn,
    LabelOut,
    LabelPatch,
    LabelWithCountOut,
    MailCountsOut,
    OverviewOut,
    SyncMailboxOut,
    SyncOut,
    MessageOut,
    RecipientOut,
    SendMessageIn,
    SetLabelsIn,
    Status,
    UpdateConversationIn,
)
from app.services import collab, email_accounts, email_send, mail, mailbox_access
from app.services.auth import Client, Identity

router = APIRouter(tags=["conversations"])


def _conv_payload(conv, acc, labels=()) -> ConversationOut:
    return ConversationOut(
        id=conv.id,
        email_account_id=conv.email_account_id,
        account_email=acc.email_address,
        account_provider=acc.provider,
        subject=conv.subject,
        snippet=conv.snippet,
        is_read=conv.is_read,
        is_starred=conv.is_starred,
        is_archived=conv.is_archived,
        is_deleted=conv.is_deleted,
        status=conv.status,
        last_message_at=conv.last_message_at,
        last_sender_name=conv.last_sender_name,
        last_sender_email=conv.last_sender_email,
        has_attachments=conv.has_attachments,
        message_count=conv.message_count,
        assignee_user_id=conv.assignee_user_id,
        priority=conv.priority,
        labels=[LabelOut(id=label.id, name=label.name, color=label.color) for label in labels],
    )


def _named(db: Session, payloads: list[ConversationOut]) -> list[ConversationOut]:
    """Fill in who each conversation is assigned to."""
    names = collab_repo.user_names(db, {p.assignee_user_id for p in payloads if p.assignee_user_id})
    for payload in payloads:
        payload.assignee_name = names.get(payload.assignee_user_id)
    return payloads


def _message_payload(m) -> MessageOut:
    return MessageOut(
        id=m.id,
        direction=m.direction,
        sender_name=m.sender_name,
        sender_email=m.sender_email,
        subject=m.subject,
        body_text=m.body_text,
        body_html=m.body_html,
        sent_at=m.sent_at,
        is_read=m.is_read,
        is_starred=m.is_starred,
        provider_message_id=m.provider_message_id,
        recipients=[RecipientOut(kind=r.kind, email=r.email, name=r.name) for r in m.recipients],
        attachments=[AttachmentOut(id=a.id, filename=a.filename, content_type=a.content_type, file_size=a.file_size) for a in m.attachments],
    )


@router.get("/conversations", response_model=Envelope[list[ConversationOut]])
def list_conversations(
    view: str = Query("inbox"),
    account_id: int | None = Query(None),
    search: str | None = Query(None, max_length=200),
    unread: bool | None = Query(None),
    starred: bool | None = Query(None),
    has_attachments: bool | None = Query(None),
    status: Status | None = Query(None),
    label_id: int | None = Query(None),
    assignee: str | None = Query(None, pattern="^(me|none|[0-9]+)$"),
    priority: str | None = Query(None, pattern="^(low|normal|high|urgent)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    identity: Identity = Depends(workspace_identity),
    db: Session = Depends(get_db),
) -> Envelope[list[ConversationOut]]:
    rows, _ = conv_repo.list_conversations(
        db,
        identity.workspace.id,
        view=view,
        account_id=account_id,
        search=search,
        unread=unread,
        starred=starred,
        has_attachments=has_attachments,
        status=status,
        label_id=label_id,
        account_ids=mailbox_access.allowed_account_ids(db, identity),
        assignee_user_id=identity.user.id if assignee == "me" else int(assignee) if assignee and assignee.isdigit() else None,
        unassigned=assignee == "none",
        priority=priority,
        limit=limit,
        offset=offset,
    )
    labels = conv_repo.labels_for_conversations(db, [conv.id for conv, _ in rows])
    return Envelope(data=_named(db, [_conv_payload(conv, acc, labels.get(conv.id, ())) for conv, acc in rows]))


@router.get("/conversations/counts", response_model=Envelope[MailCountsOut])
def mail_counts(identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[MailCountsOut]:
    by_account = conv_repo.inbox_unread_by_account(db, identity.workspace.id, mailbox_access.allowed_account_ids(db, identity))
    return Envelope(data=MailCountsOut(inbox_unread=sum(by_account.values()), inbox_unread_by_account=by_account))


@router.get("/conversations/overview", response_model=Envelope[OverviewOut])
def overview(identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[OverviewOut]:
    """The numbers and the short list on the Overview page, from the mail that is actually stored."""
    workspace_id = identity.workspace.id
    allowed = mailbox_access.allowed_account_ids(db, identity)
    accounts = email_accounts.list_accounts(db, identity)

    def total(**filters) -> int:
        return conv_repo.list_conversations(db, workspace_id, account_ids=allowed, limit=1, **filters)[1]

    unread_rows, unread = conv_repo.list_conversations(db, workspace_id, view="inbox", unread=True, account_ids=allowed, limit=6)
    labels = conv_repo.labels_for_conversations(db, [conv.id for conv, _ in unread_rows])
    mailboxes: list[SyncMailboxOut] = []
    for acc, stored in accounts:
        if acc.status in ("error", "needs_reconnect"):
            state = "problem"
        elif acc.auth_type == "oauth" and acc.import_state != "done":
            state = "importing"
        elif acc.status == "syncing" and not acc.last_sync_at:
            state = "importing"
        else:
            state = "done"
        # Only the inbox is counted by the provider, so a finished mailbox shows what it holds.
        expected = acc.import_total if acc.import_state != "done" and acc.import_total else None
        mailboxes.append(SyncMailboxOut(email_address=acc.email_address, state=state, stored=stored, total=max(expected, stored) if expected else None))
    importing = [m for m in mailboxes if m.state == "importing"]
    if not mailboxes:
        sync_state = "none"
    elif importing:
        sync_state = "syncing"
    elif any(m.state == "problem" for m in mailboxes):
        sync_state = "attention"
    else:
        sync_state = "complete"
    known = [m for m in importing if m.total]
    sync = SyncOut(
        state=sync_state,
        stored=sum(m.stored for m in mailboxes),
        total=sum(m.total for m in known) if known else None,
        percent=min(99, int(100 * sum(m.stored for m in known) / sum(m.total for m in known))) if known else None,
        mailboxes=mailboxes,
        last_synced_at=max((acc.last_sync_at for acc, _ in accounts if acc.last_sync_at), default=None),
    )
    return Envelope(data=OverviewOut(
        sync=sync,
        connected_inboxes=len(accounts),
        inboxes_needing_attention=sum(1 for acc, _ in accounts if acc.status in ("error", "needs_reconnect")),
        messages_stored=conv_repo.count_messages(db, workspace_id, allowed),
        open_conversations=total(view="inbox", status="open"),
        waiting_on_team=total(view="all", status="pending"),
        unread_conversations=unread,
        needs_attention=_named(db, [_conv_payload(conv, acc, labels.get(conv.id, ())) for conv, acc in unread_rows]),
    ))


@router.get("/conversations/{conversation_id}", response_model=Envelope[ConversationDetailOut])
def get_conversation(
    conversation_id: int,
    identity: Identity = Depends(workspace_identity),
    db: Session = Depends(get_db),
) -> Envelope[ConversationDetailOut]:
    res = conv_repo.get_conversation(db, conversation_id, identity.workspace.id, mailbox_access.allowed_account_ids(db, identity))
    if not res:
        raise AppError(404, "CONVERSATION_NOT_FOUND", "Conversation not found.")
    conv, acc = res

    # Mark as read upon open. A viewer only looks: their opening it changes nothing for the team.
    if not conv.is_read and identity.role != "viewer":
        conv.is_read = True
        db.commit()

    messages = conv_repo.get_messages_for_conversation(db, conversation_id, identity.workspace.id)
    labels = conv_repo.labels_for_conversations(db, [conv.id]).get(conv.id, ())
    notes = collab_repo.notes_for_conversation(db, conv.id)
    names = collab_repo.user_names(db, {n.author_user_id for n in notes if n.author_user_id})
    return Envelope(data=ConversationDetailOut(
        conversation=_named(db, [_conv_payload(conv, acc, labels)])[0],
        messages=[_message_payload(m) for m in messages],
        notes=[note_out(n, names, identity) for n in notes],
    ))


@router.patch("/conversations/{conversation_id}", response_model=Envelope[ConversationOut])
def update_conversation(
    conversation_id: int,
    body: UpdateConversationIn,
    identity: Identity = Depends(workspace_identity),
    client: Client = Depends(get_client),
    db: Session = Depends(get_db),
) -> Envelope[ConversationOut]:
    res = conv_repo.get_conversation(db, conversation_id, identity.workspace.id, mailbox_access.allowed_account_ids(db, identity))
    if not res:
        raise AppError(404, "CONVERSATION_NOT_FOUND", "Conversation not found.")
    conv, acc = res
    if identity.role == "viewer":
        raise AppError(403, "FORBIDDEN", "Viewers can read mail but not change it.")

    # Only "unassign" is meant by an explicit null; for every other field a null is ignored rather than stored.
    changes = {key: value for key, value in body.model_dump(exclude_unset=True).items() if value is not None or key == "assignee_user_id"}
    if "assignee_user_id" in changes:
        collab.assign(db, identity, conv.id, changes.pop("assignee_user_id"), client)
    conv_repo.update_conversation(db, conv, changes)
    db.commit()

    labels = conv_repo.labels_for_conversations(db, [conv.id]).get(conv.id, ())
    return Envelope(data=_named(db, [_conv_payload(conv, acc, labels)])[0])


@router.put("/conversations/{conversation_id}/labels", response_model=Envelope[list[LabelOut]])
def set_conversation_labels(
    conversation_id: int,
    body: SetLabelsIn,
    identity: Identity = Depends(workspace_identity),
    db: Session = Depends(get_db),
) -> Envelope[list[LabelOut]]:
    mail.set_labels(db, identity, conversation_id, body.label_ids)
    labels = conv_repo.labels_for_conversations(db, [conversation_id]).get(conversation_id, ())
    return Envelope(data=[LabelOut(id=label.id, name=label.name, color=label.color) for label in labels])


@router.post("/conversations/batch", response_model=Envelope[dict[str, int]])
def batch_conversations(
    body: BatchConversationIn,
    identity: Identity = Depends(workspace_identity),
    db: Session = Depends(get_db),
) -> Envelope[dict[str, int]]:
    if identity.role == "viewer":
        raise AppError(403, "FORBIDDEN", "Viewers can read mail but not change it.")
    updated = conv_repo.batch_update_conversations(
        db,
        identity.workspace.id,
        body.conversation_ids,
        body.action,
        mailbox_access.allowed_account_ids(db, identity),
    )
    db.commit()
    return Envelope(data={"updated": updated})


@router.get("/labels", response_model=Envelope[list[LabelWithCountOut]])
def list_labels(identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[list[LabelWithCountOut]]:
    rows = conv_repo.list_labels(db, identity.workspace.id)
    return Envelope(data=[LabelWithCountOut(id=label.id, name=label.name, color=label.color, conversation_count=count) for label, count in rows])


@router.post("/labels", response_model=Envelope[LabelOut], status_code=201)
def create_label(body: LabelIn, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[LabelOut]:
    label = mail.create_label(db, identity, body.name, body.color)
    return Envelope(data=LabelOut(id=label.id, name=label.name, color=label.color))


@router.patch("/labels/{label_id}", response_model=Envelope[LabelOut])
def update_label(label_id: int, body: LabelPatch, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[LabelOut]:
    label = mail.update_label(db, identity, label_id, body.name, body.color)
    return Envelope(data=LabelOut(id=label.id, name=label.name, color=label.color))


@router.delete("/labels/{label_id}", status_code=204)
def delete_label(label_id: int, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> None:
    mail.delete_label(db, identity, label_id)


@router.get("/attachments/{attachment_id}")
def download_attachment(attachment_id: int, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Response:
    attachment, content = mail.download_attachment(db, identity, attachment_id)
    return Response(
        content=content,
        # Always a download, never a page: an attachment must not be able to run in the app's address.
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(attachment.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/messages/send", response_model=Envelope[MessageOut], status_code=201)
def send_message(
    body: SendMessageIn,
    identity: Identity = Depends(workspace_identity),
    client: Client = Depends(get_client),
    db: Session = Depends(get_db),
) -> Envelope[MessageOut]:
    msg = email_send.send_message(
        db,
        identity,
        account_id=body.account_id,
        to=body.to,
        subject=body.subject,
        body_text=body.body_text,
        body_html=body.body_html,
        cc=body.cc,
        bcc=body.bcc,
        conversation_id=body.conversation_id,
        in_reply_to=body.in_reply_to,
        attachments=body.attachments,
        forward_attachments_of=body.forward_attachments_of,
        client=client,
    )
    if body.draft_id:
        collab.delete_draft(db, identity, body.draft_id, missing_ok=True)
    return Envelope(data=_message_payload(msg))
