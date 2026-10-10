from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_client, workspace_identity
from app.core.database import get_db
from app.schemas.automation import (
    AutomationSettingsIn,
    AutomationSettingsOut,
    AutomationSummary,
    ReorderIn,
    RuleIn,
    RuleOut,
    RuleToggle,
    RunRecentIn,
    RunRecentOut,
    RunOut,
    TestOut,
)
from app.schemas.common import Envelope
from app.services import automation
from app.services.auth import Client, Identity

router = APIRouter(prefix="/automation", tags=["automation"])


@router.get("/summary", response_model=Envelope[AutomationSummary])
def summary(identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[AutomationSummary]:
    return Envelope(data=AutomationSummary(**automation.summary(db, identity)))


@router.get("/settings", response_model=Envelope[AutomationSettingsOut])
def get_settings(identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[AutomationSettingsOut]:
    return Envelope(data=AutomationSettingsOut(**automation.get_settings(db, identity)))


@router.put("/settings", response_model=Envelope[AutomationSettingsOut])
def update_settings(body: AutomationSettingsIn, identity: Identity = Depends(workspace_identity), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[AutomationSettingsOut]:
    return Envelope(data=AutomationSettingsOut(**automation.update_settings(db, identity, body.enabled, body.mailboxes, client)))


@router.get("/rules", response_model=Envelope[list[RuleOut]])
def list_rules(identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[list[RuleOut]]:
    return Envelope(data=[RuleOut(**rule) for rule in automation.list_rules(db, identity)])


@router.post("/rules", response_model=Envelope[RuleOut], status_code=201)
def create_rule(body: RuleIn, identity: Identity = Depends(workspace_identity), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[RuleOut]:
    return Envelope(data=RuleOut(**automation.create_rule(db, identity, body, client)))


@router.post("/rules/test", response_model=Envelope[TestOut])
def test_rule(body: RuleIn, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[TestOut]:
    checked, matches = automation.test_rule(db, identity, body)
    return Envelope(data=TestOut(checked=checked, matches=matches))


@router.put("/rules/order", status_code=204)
def reorder(body: ReorderIn, identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> None:
    automation.reorder(db, identity, body.rule_ids)


@router.put("/rules/{rule_id}", response_model=Envelope[RuleOut])
def update_rule(rule_id: int, body: RuleIn, identity: Identity = Depends(workspace_identity), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[RuleOut]:
    return Envelope(data=RuleOut(**automation.update_rule(db, identity, rule_id, body, client)))


@router.patch("/rules/{rule_id}", response_model=Envelope[RuleOut])
def toggle_rule(rule_id: int, body: RuleToggle, identity: Identity = Depends(workspace_identity), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[RuleOut]:
    return Envelope(data=RuleOut(**automation.set_enabled(db, identity, rule_id, body.enabled, client)))


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, identity: Identity = Depends(workspace_identity), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> None:
    automation.delete_rule(db, identity, rule_id, client)


@router.post("/run-recent", response_model=Envelope[RunRecentOut])
def run_on_recent(body: RunRecentIn, identity: Identity = Depends(workspace_identity), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[RunRecentOut]:
    return Envelope(data=RunRecentOut(**automation.run_on_recent(db, identity, body.per_mailbox, client)))


@router.get("/runs", response_model=Envelope[list[RunOut]])
def list_runs(rule_id: int | None = Query(None), limit: int = Query(50, ge=1, le=200), identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[list[RunOut]]:
    return Envelope(data=[RunOut(**run) for run in automation.runs(db, identity, rule_id, limit)])
