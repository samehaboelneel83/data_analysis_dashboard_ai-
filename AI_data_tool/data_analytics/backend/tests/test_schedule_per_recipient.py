"""HR evaluation 2026-10-01, item 3.3: each recipient their own view; skip unchanged."""
import pandas as pd
import pytest

from app.models.models import (Dataset, DatasetColumn, Report, ReportPage, ReportSchedule,
                               ReportWidget, Role, RowSecurityRule, User)
from app.services import delivery


async def _setup(db, two_orgs, tmp_path, opts):
    org = two_orgs["a"]["org"].id
    admin = two_orgs["a"]["user"]
    path = tmp_path / "hr.csv"
    pd.DataFrame({"dept": ["Sales", "HR", "Sales"], "salary": [100, 80, 120]}).to_csv(path, index=False)
    ds = Dataset(name="hr", org_id=org, filename=str(path), row_count=3, col_count=2, file_size=1)
    db.add(ds)
    await db.flush()
    for c, t in (("dept", "categorical"), ("salary", "numeric")):
        db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype=t, stats={}))
    role = Role(org_id=org, name="Sales managers", is_org_admin=False)
    db.add(role)
    await db.flush()
    mgr = User(org_id=org, role_id=role.id, email="sales.mgr@example.com", password_hash="x")
    db.add(mgr)
    db.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr="dept == 'Sales'"))
    r = Report(name="Pay", org_id=org, dataset_id=ds.id, created_by=admin.id, published=True)
    db.add(r)
    await db.flush()
    p = ReportPage(report_id=r.id, name="Page 1", position=0)
    db.add(p)
    await db.flush()
    db.add(ReportWidget(page_id=p.id, widget_type="table", title="Rows",
                        config={"columns": ["dept", "salary"]}, layout={"x": 0, "y": 0, "w": 6, "h": 4}))
    s = ReportSchedule(org_id=org, report_id=r.id, creator_user_id=admin.id, interval_minutes=60,
                       recipients=["sales.mgr@example.com", "stranger@example.com", *opts])
    db.add(s)
    await db.commit()
    return s


@pytest.mark.asyncio
async def test_each_recipient_gets_their_own_view(db_session, two_orgs, tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(delivery, "send_email", lambda to, subj, body, att=None: sent.append((to, att)) or None)
    s = await _setup(db_session, two_orgs, tmp_path, [{"__per_recipient__": True}])
    await delivery.run_schedule(db_session, s)
    assert [to for to, _ in sent] == [["sales.mgr@example.com"]]
    assert "skipped 1" in s.last_status


@pytest.mark.asyncio
async def test_only_if_changed_skips_the_second_identical_run(db_session, two_orgs, tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(delivery, "send_email", lambda to, subj, body, att=None: sent.append(to) or None)
    s = await _setup(db_session, two_orgs, tmp_path, [{"__only_if_changed__": True}])
    await delivery.run_schedule(db_session, s)
    await delivery.run_schedule(db_session, s)
    assert len(sent) == 1
    assert "no change" in s.last_status
