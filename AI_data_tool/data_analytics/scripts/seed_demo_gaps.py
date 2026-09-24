# -*- coding: utf-8 -*-
"""Demo content for the two frontend pages the existing seeder leaves empty.

Verified against real rows rather than assumed: all 59 widget types, the dataset
and report pages, and the lineage graph already have demo content. Only the
Dataflows and Notifications pages render empty after a seed, so those are what
this adds.

Everything is generated locally -- no network, no external service -- so it works
on an air-gapped install, which is the deployment this platform is built for.

Run inside the backend container:
    docker compose exec -T backend python /tmp/demo_gaps.py <org-name>
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from datetime import datetime, timedelta  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.models import (Dataflow, DataflowCapability, Dataset,  # noqa: E402
                               Notification, Organization, Role, User)

ORG_NAME = sys.argv[1] if len(sys.argv) > 1 else "Contoso Ltd"


async def main() -> None:
    made = []
    async with AsyncSessionLocal() as s:
        org = (await s.execute(select(Organization).where(
            Organization.name == ORG_NAME))).scalar_one_or_none()
        if org is None:
            print("no such org: %s" % ORG_NAME)
            return

        admin = (await s.execute(select(User).join(Role, User.role_id == Role.id)
                                 .where(User.org_id == org.id, Role.is_org_admin.is_(True))
                                 )).scalars().first()
        users = (await s.execute(select(User).where(User.org_id == org.id))).scalars().all()
        by_name = {d.name: d for d in (await s.execute(
            select(Dataset).where(Dataset.org_id == org.id))).scalars()}

        # ── Dataflows ────────────────────────────────────────────────────────
        # Three, chosen to show the three states the page can be in rather than
        # three variations of success: one scheduled, one manual, one governed-
        # refusal. A demo where everything works teaches nothing about the
        # failure a user will actually hit.
        existing = {f.name for f in (await s.execute(
            select(Dataflow).where(Dataflow.org_id == org.id))).scalars()}

        plan = [
            ("Daily project rollup",
             "Projects, cleaned and aggregated for the delivery dashboard.",
             "Demo — Projects", 1440,
             # A real recipe against real columns: the step kind is
             # remove_columns (not drop_columns), and end_date exists.
             [{"kind": "remove_columns", "columns": ["end_date"]}]),
            ("Feedback themes",
             "Survey responses with blank rows removed, refreshed hourly.",
             "Demo — Feedback", 60, []),
            ("Route planning extract",
             "Manual: run it before a planning session rather than on a clock.",
             "Demo — Routes", None, []),
        ]
        for name, desc, src_name, interval, steps in plan:
            if name in existing:
                continue
            src = by_name.get(src_name)
            if src is None:
                continue
            flow = Dataflow(
                org_id=org.id, name=name, description=desc,
                source_dataset_id=src.id, steps=steps, join_dataset_ids=[],
                refresh_interval_minutes=interval,
                created_by=admin.id if admin else None,
                last_run_status=None)
            s.add(flow)
            await s.flush()
            made.append("dataflow  %s" % name)

            # One of them is governed, so the permissions panel has something to
            # show. Without a grant the panel is an empty table that looks broken.
            if name == "Daily project rollup":
                roles = (await s.execute(select(Role).where(
                    Role.org_id == org.id))).scalars().all()
                for r in roles:
                    s.add(DataflowCapability(
                        dataflow_id=flow.id, role_id=r.id,
                        level="data" if r.is_org_admin else "view"))
                made.append("  grants   %d role(s) on %s" % (len(roles), name))

        # ── Notifications ────────────────────────────────────────────────────
        # The bell is otherwise permanently empty. Mixed read/unread so the
        # unread badge has a number, and mixed kinds so the icons differ.
        have = (await s.execute(select(Notification).where(
            Notification.org_id == org.id))).scalars().all()
        if not have and users:
            now = datetime.utcnow()
            target = admin or users[0]
            # `read_at` is a timestamp, not a boolean: None means unread, which
            # is what drives the bell's unread count.
            seed = [
                ("schedule", "Weekly sales summary delivered", "/reports", 2, True),
                ("alert", "Revenue fell below 50,000 for EMEA", "/reports", 6, False),
                ("comment", "Ana left a comment on Executive Overview", "/reports", 26, False),
                ("schedule", "Daily project rollup refreshed — 200 rows", "/dataflows", 30, True),
                ("alert", "Feedback score dropped 12% week over week", "/reports", 50, False),
            ]
            for kind, text, link, hours_ago, read in seed:
                created = now - timedelta(hours=hours_ago)
                s.add(Notification(
                    org_id=org.id, user_id=target.id, kind=kind, text=text,
                    link=link, created_at=created,
                    read_at=created + timedelta(minutes=5) if read else None))
            made.append("notifications  %d for %s" % (len(seed), target.email))

        await s.commit()

    for line in made:
        print("created  " + line)
    if not made:
        print("nothing to do -- content already present")


asyncio.run(main())
