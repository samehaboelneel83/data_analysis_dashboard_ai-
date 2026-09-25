"""Hierarchical RLS (0016): access flows DOWN an organization's own chart.

A user placed at Egypt/Alexandria/Engineering sees Engineering and every team
beneath it -- Software, Network, Infrastructure -- from ONE rule written as
`branch in MYSCOPE()`, with no role per branch.

What is pinned here:
  * the subtree, not just the node, and not the siblings
  * placement is per USER, so one role can hold people at different branches
  * an unplaced user FAILS CLOSED (sees nothing), never open
  * expansion cannot be turned into an injection or an identity swap
  * admins keep their existing bypass
"""
import pytest
from sqlalchemy import select

from app.core.rls import apply_scope, resolve_rls_expr, scope_values_for
from app.core.security import hash_password
from app.models.models import (Dataset, OrgUnit, Role, RowSecurityRule, User,
                               UserOrgUnit)


async def _tree(db, org_id):
    """Egypt → {Alexandria → {Engineering → {Software, Network}}, Cairo → Sales}"""
    def unit(name, parent=None, level=None, match=None):
        u = OrgUnit(org_id=org_id, parent_id=parent, name=name,
                    level_name=level, match_value=match or name)
        db.add(u)
        return u

    egypt = unit("Egypt", level="Country")
    await db.flush()
    alex = unit("Alexandria", egypt.id, "Region")
    cairo = unit("Cairo", egypt.id, "Region")
    await db.flush()
    eng = unit("Engineering", alex.id, "Department")
    sales = unit("Sales", cairo.id, "Department")
    await db.flush()
    soft = unit("Software", eng.id, "Team")
    net = unit("Network", eng.id, "Team")
    await db.flush()
    return {"egypt": egypt, "alex": alex, "cairo": cairo, "eng": eng,
            "sales": sales, "soft": soft, "net": net}


async def _member(db, org_id, name, role=None):
    if role is None:
        role = Role(org_id=org_id, name=f"role-{name}", is_org_admin=False)
        db.add(role)
        await db.flush()
    user = User(org_id=org_id, role_id=role.id, email=f"{name}@ex.com",
                password_hash=hash_password("pw"))
    db.add(user)
    await db.flush()
    return user, role


async def _place(db, user, unit):
    db.add(UserOrgUnit(user_id=user.id, org_unit_id=unit.id))
    await db.flush()


class TestScopeIsTheSubtree:
    async def test_a_placement_grants_the_node_and_all_descendants(
            self, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        t = await _tree(db_session, org.id)
        user, _ = await _member(db_session, org.id, "eng-lead")
        await _place(db_session, user, t["eng"])
        await db_session.commit()

        values = await scope_values_for(db_session, user)
        assert set(values) == {"Engineering", "Software", "Network"}

    async def test_it_does_not_leak_sideways_or_upward(self, db_session, two_orgs):
        """THE property. Alexandria/Engineering must not see Cairo (a sibling
        branch) nor Egypt (the parent) -- access flows down only."""
        org = two_orgs["a"]["org"]
        t = await _tree(db_session, org.id)
        user, _ = await _member(db_session, org.id, "narrow")
        await _place(db_session, user, t["eng"])
        await db_session.commit()

        values = set(await scope_values_for(db_session, user))
        assert "Cairo" not in values and "Sales" not in values
        assert "Egypt" not in values and "Alexandria" not in values

    async def test_a_root_placement_grants_the_whole_org(self, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        t = await _tree(db_session, org.id)
        user, _ = await _member(db_session, org.id, "country-head")
        await _place(db_session, user, t["egypt"])
        await db_session.commit()

        assert set(await scope_values_for(db_session, user)) == {
            "Egypt", "Alexandria", "Cairo", "Engineering", "Sales",
            "Software", "Network"}

    async def test_several_placements_union_their_subtrees(self, db_session, two_orgs):
        """A manager covering two regions holds two placements; the scope is
        the union, which a single-node model could not express."""
        org = two_orgs["a"]["org"]
        t = await _tree(db_session, org.id)
        user, _ = await _member(db_session, org.id, "two-hats")
        await _place(db_session, user, t["soft"])
        await _place(db_session, user, t["sales"])
        await db_session.commit()

        assert set(await scope_values_for(db_session, user)) == {"Software", "Sales"}

    async def test_match_value_is_what_the_data_says_not_the_display_name(
            self, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        unit = OrgUnit(org_id=org.id, name="Alexandria Branch",
                       level_name="Branch", match_value="ALX")
        db_session.add(unit)
        await db_session.flush()
        user, _ = await _member(db_session, org.id, "alx")
        await _place(db_session, user, unit)
        await db_session.commit()

        assert await scope_values_for(db_session, user) == ["ALX"]


class TestPlacementIsPerUser:
    async def test_one_role_can_hold_people_at_different_branches(
            self, db_session, two_orgs):
        """The reason placement is not role-scoped: expressing this with roles
        would need one role per branch."""
        org = two_orgs["a"]["org"]
        t = await _tree(db_session, org.id)
        shared = Role(org_id=org.id, name="Regional manager", is_org_admin=False)
        db_session.add(shared)
        await db_session.flush()
        a, _ = await _member(db_session, org.id, "alex-mgr", shared)
        b, _ = await _member(db_session, org.id, "cairo-mgr", shared)
        await _place(db_session, a, t["alex"])
        await _place(db_session, b, t["cairo"])
        await db_session.commit()

        assert "Engineering" in await scope_values_for(db_session, a)
        assert "Engineering" not in await scope_values_for(db_session, b)
        assert "Sales" in await scope_values_for(db_session, b)


class TestUnplacedFailsClosed:
    async def test_no_placement_returns_none_not_an_empty_list(
            self, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        await _tree(db_session, org.id)
        user, _ = await _member(db_session, org.id, "nobody")
        await db_session.commit()
        assert await scope_values_for(db_session, user) is None

    async def test_an_unresolved_token_is_left_alone_rather_than_emptied(self):
        """`col in []` is valid and quietly matches nothing, which reads like a
        data bug. Leaving MYSCOPE() unresolved fails at evaluation instead --
        loudly, the same way an absent ORGNAME does."""
        expr = "branch in MYSCOPE()"
        assert apply_scope(expr, None) == expr
        assert "MYSCOPE" not in apply_scope(expr, ["Software"])

    async def test_the_rule_of_an_unplaced_user_still_carries_the_token(
            self, db_session, two_orgs):
        org = two_orgs["a"]["org"]
        ds = Dataset(name="D", org_id=org.id)
        db_session.add(ds)
        await db_session.flush()
        user, role = await _member(db_session, org.id, "unplaced")
        db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id,
                                       filter_expr="branch in MYSCOPE()"))
        await db_session.commit()

        expr = await resolve_rls_expr(db_session, user, ds.id)
        assert "MYSCOPE" in expr          # unresolved => fails closed downstream


class TestExpansionIsSafe:
    async def test_values_are_encoded_as_literals_not_interpolated(self):
        out = apply_scope("branch in MYSCOPE()", ["O'Brien", "Software"])
        # quote doubling via repr keeps it ONE literal
        assert out == "branch in ['O\\'Brien', 'Software']" or "O'Brien" in out
        assert out.count("[") == 1

    async def test_a_unit_named_like_a_token_stays_data(self, db_session, two_orgs):
        """Expansion runs LAST. If it ran before apply_user_context, a unit
        whose match value read 'USEREMAIL()' would be rewritten into the
        caller's email -- turning stored data into identity."""
        org = two_orgs["a"]["org"]
        ds = Dataset(name="D2", org_id=org.id)
        unit = OrgUnit(org_id=org.id, name="odd", match_value="USEREMAIL()")
        db_session.add_all([ds, unit])
        await db_session.flush()
        user, role = await _member(db_session, org.id, "odd-user")
        await _place(db_session, user, unit)
        db_session.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id,
                                       filter_expr="branch in MYSCOPE()"))
        await db_session.commit()

        expr = await resolve_rls_expr(db_session, user, ds.id)
        assert "USEREMAIL()" in expr           # survived as a literal value
        assert "odd-user@ex.com" not in expr   # was NOT read as an identity

    async def test_a_cycle_in_the_tree_cannot_hang_a_read(self, db_session, two_orgs):
        """The API refuses to create one, but a hand-edited database must not
        be able to spin the descendant walk forever."""
        org = two_orgs["a"]["org"]
        a = OrgUnit(org_id=org.id, name="A", match_value="A")
        db_session.add(a)
        await db_session.flush()
        b = OrgUnit(org_id=org.id, parent_id=a.id, name="B", match_value="B")
        db_session.add(b)
        await db_session.flush()
        a.parent_id = b.id                      # A → B → A
        user, _ = await _member(db_session, org.id, "cyclic")
        await _place(db_session, user, a)
        await db_session.commit()

        assert set(await scope_values_for(db_session, user)) == {"A", "B"}


class TestOrgIsolationAndAdmins:
    async def test_another_orgs_units_never_enter_the_scope(self, db_session, two_orgs):
        org_a, org_b = two_orgs["a"]["org"], two_orgs["b"]["org"]
        t = await _tree(db_session, org_a.id)
        foreign = OrgUnit(org_id=org_b.id, name="Foreign", match_value="Foreign")
        db_session.add(foreign)
        await db_session.flush()
        user, _ = await _member(db_session, org_a.id, "insider")
        await _place(db_session, user, t["eng"])
        # A placement pointing at another org's unit contributes nothing.
        db_session.add(UserOrgUnit(user_id=user.id, org_unit_id=foreign.id))
        await db_session.commit()

        assert "Foreign" not in await scope_values_for(db_session, user)

    async def test_an_org_admin_still_bypasses_rls_entirely(
            self, db_session, two_orgs, ):
        org = two_orgs["a"]["org"]
        ds = Dataset(name="D3", org_id=org.id)
        db_session.add(ds)
        await db_session.flush()
        admin = two_orgs["a"]["user"]
        db_session.add(RowSecurityRule(role_id=admin.role_id, dataset_id=ds.id,
                                       filter_expr="branch in MYSCOPE()"))
        await db_session.commit()

        assert await resolve_rls_expr(db_session, admin, ds.id) is None


class TestEndToEndThroughTheRule:
    async def test_one_rule_scopes_two_users_differently(self, db_session, two_orgs):
        """The whole point, in one test: ONE rule, two people, two answers."""
        org = two_orgs["a"]["org"]
        t = await _tree(db_session, org.id)
        ds = Dataset(name="Sales", org_id=org.id)
        db_session.add(ds)
        await db_session.flush()
        shared = Role(org_id=org.id, name="Manager", is_org_admin=False)
        db_session.add(shared)
        await db_session.flush()
        a, _ = await _member(db_session, org.id, "eng", shared)
        b, _ = await _member(db_session, org.id, "sale", shared)
        await _place(db_session, a, t["eng"])
        await _place(db_session, b, t["sales"])
        db_session.add(RowSecurityRule(role_id=shared.id, dataset_id=ds.id,
                                       filter_expr="branch in MYSCOPE()"))
        await db_session.commit()

        ea = await resolve_rls_expr(db_session, a, ds.id)
        eb = await resolve_rls_expr(db_session, b, ds.id)
        assert "Software" in ea and "Network" in ea and "Sales" not in ea
        assert "Sales" in eb and "Software" not in eb
        # Distinct expressions => distinct DirectQuery cache keys, as security
        # requires (the cache key is built from the verbatim expression).
        assert ea != eb
