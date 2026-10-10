from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.email import EmailAccount, EmailOAuthState, Folder, Message


def get_account(db: Session, account_id: int, workspace_id: int) -> EmailAccount | None:
    return db.scalar(
        select(EmailAccount).where(EmailAccount.id == account_id, EmailAccount.workspace_id == workspace_id)
    )


def find_by_email(db: Session, workspace_id: int, email_address: str) -> EmailAccount | None:
    return db.scalar(
        select(EmailAccount).where(EmailAccount.workspace_id == workspace_id, EmailAccount.email_address == email_address)
    )


def list_accounts(db: Session, workspace_id: int) -> list[tuple[EmailAccount, int]]:
    msg_counts = (
        select(Message.email_account_id, func.count(Message.id).label("cnt"))
        .group_by(Message.email_account_id)
        .subquery()
    )
    rows = db.execute(
        select(EmailAccount, func.coalesce(msg_counts.c.cnt, 0))
        .outerjoin(msg_counts, msg_counts.c.email_account_id == EmailAccount.id)
        .where(EmailAccount.workspace_id == workspace_id)
        .order_by(EmailAccount.created_at.desc())
    )
    return [(acc, int(cnt)) for acc, cnt in rows]


def add_account(db: Session, account: EmailAccount) -> EmailAccount:
    db.add(account)
    db.flush()
    return account


def delete_account(db: Session, account: EmailAccount) -> None:
    db.delete(account)
    db.flush()


def get_folder_by_name(db: Session, account_id: int, folder_name: str) -> Folder | None:
    return db.scalar(
        select(Folder).where(Folder.email_account_id == account_id, Folder.name == folder_name)
    )


def add_folder(db: Session, folder: Folder) -> Folder:
    db.add(folder)
    db.flush()
    return folder


def list_folders(db: Session, account_id: int) -> list[Folder]:
    return list(
        db.scalars(select(Folder).where(Folder.email_account_id == account_id).order_by(Folder.name)).all()
    )



def add_oauth_state(db: Session, state: EmailOAuthState) -> EmailOAuthState:
    db.add(state)
    db.flush()
    return state


def take_oauth_state(db: Session, state_hash: str) -> EmailOAuthState | None:
    """Fetch a sign-in attempt and remove it, so it can only ever be used once."""
    state = db.scalar(select(EmailOAuthState).where(EmailOAuthState.state_hash == state_hash).with_for_update())
    if state is not None:
        db.delete(state)
        db.flush()
    return state


def delete_expired_oauth_states(db: Session, now: datetime) -> None:
    db.execute(delete(EmailOAuthState).where(EmailOAuthState.expires_at < now))
