import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import Organization, RowSecurityRule, User

# Dynamic user context in RLS (and, as of S0, ordinary author) expressions:
# USEREMAIL()/USER() resolve to the caller's email, USERID() to their numeric id,
# ORGID()/ORGNAME() to their organization. This lets ONE role-level rule such as
# `owner_email == USEREMAIL()` scope every user to their own rows, instead of needing a
# separate role (and rule) per user. USER is not a prefix hazard for USEREMAIL — the
# `()` immediately follows the name, so `\bUSER\s*\(` cannot match inside `USEREMAIL(`.
_USER_TOKEN = re.compile(r"\b(USEREMAIL|USERID|USER|ORGID|ORGNAME)\s*\(\s*\)", re.IGNORECASE)

# Cheap presence probe used to decide whether ORGNAME's backing query is worth
# paying for at all (see call sites below). Must tolerate the same whitespace
# the real substitution regex above tolerates (`ORGNAME ( )`, `ORGNAME  (  )`)
# -- a plain `"ORGNAME(" in expr.upper()` substring check does not, so a rule
# written with a space before the parens would sail past this probe, org_name
# would stay None, and the token would come back from apply_user_context
# unexpanded (fail-closed: zero rows) instead of resolved.
_ORGNAME_PRESENT = re.compile(r"\bORGNAME\s*\(", re.IGNORECASE)

# HIERARCHICAL RLS. `MYSCOPE()` expands to the list of org-unit match values
# this user may see: the units they are placed at, plus every descendant. So a
# rule written once --
#
#     branch in MYSCOPE()
#
# -- gives the Egypt/Alexandria/Engineering user Software, Network and
# Infrastructure automatically, and gives their colleague in Cairo/Sales a
# different set, with no second rule and no role per branch.
#
# Expansion happens HERE, server-side, from the database's own tree. The
# expression that reaches either evaluator contains only literals, so the
# existing injection defence, the SQL parameter binding and the per-user
# DirectQuery cache key all keep working unchanged.
_MYSCOPE_PRESENT = re.compile(r"\bMYSCOPE\s*\(", re.IGNORECASE)
_MYSCOPE_TOKEN = re.compile(r"\bMYSCOPE\s*\(\s*\)", re.IGNORECASE)


def _encode_scope(values: list[str]) -> str:
    """A python/pandas-and-SQL-translatable list literal of safe string values.

    `repr` per element, exactly as `apply_user_context` encodes USEREMAIL():
    a value containing a quote stays one literal rather than closing it.
    """
    return "[" + ", ".join(repr(str(v)) for v in values) + "]"


def apply_scope(expr: str | None, values: list[str] | None) -> str | None:
    """Substitute MYSCOPE() with the caller's permitted value list.

    `values is None` means "this user has no placement in the org tree". The
    token is then left UNRESOLVED, which fails closed at evaluation exactly
    like an absent ORGNAME -- deliberately NOT an empty list, because
    `col in []` is a valid expression that quietly returns nothing and reads,
    to whoever debugs it later, like a data problem rather than a missing
    assignment.
    """
    if not expr or values is None:
        return expr
    return _MYSCOPE_TOKEN.sub(lambda _m: _encode_scope(values), expr)


async def scope_values_for(db: AsyncSession, user: User) -> list[str] | None:
    """Every org-unit match value this user may see: their placements and all
    descendants, deduplicated.

    Returns None when the user holds no placement at all -- see `apply_scope`
    for why that is not an empty list.

    The whole org's units are loaded once and walked in memory rather than
    issued as a recursive CTE: an org chart is hundreds of rows, not millions,
    and one portable query beats a dialect-specific WITH RECURSIVE that would
    have to work on both Postgres and the SQLite the tests run on.
    """
    from ..models.models import OrgUnit, UserOrgUnit

    placements = (await db.execute(
        select(UserOrgUnit.org_unit_id).where(UserOrgUnit.user_id == user.id)
    )).scalars().all()
    if not placements:
        return None

    rows = (await db.execute(
        select(OrgUnit.id, OrgUnit.parent_id, OrgUnit.match_value)
        .where(OrgUnit.org_id == user.org_id)
    )).all()
    children: dict[int | None, list[tuple[int, str]]] = {}
    for uid, parent_id, match_value in rows:
        children.setdefault(parent_id, []).append((uid, match_value))

    out: list[str] = []
    seen_units: set[int] = set()
    stack = [p for p in placements]
    by_id = {uid: match_value for uid, _p, match_value in rows}
    while stack:
        uid = stack.pop()
        if uid in seen_units:
            # A cycle would otherwise spin forever. The API refuses to create
            # one, but a hand-edited database must not be able to hang a read.
            continue
        seen_units.add(uid)
        if uid in by_id:
            out.append(by_id[uid])
        stack.extend(cid for cid, _v in children.get(uid, []))

    # A placement pointing at another org's unit contributes nothing, because
    # `rows` is org-scoped -- so cross-org leakage is structurally impossible
    # here rather than checked for.
    return list(dict.fromkeys(out))


def apply_user_context(
    expr: str | None, *, email: str, user_id: int,
    org_id: int | None = None, org_name: str | None = None,
) -> str | None:
    """Substitute USEREMAIL()/USER()/USERID()/ORGID()/ORGNAME() with SAFE literals
    before the expression reaches either evaluator. Strings are emitted via repr(), so a
    value carrying a quote stays one string literal (the same injection defense the
    parameters use); ids are emitted as ints. Both the pandas AST evaluator and the SQL
    translator then see an ordinary literal — the translator further binds it as a query
    parameter.

    org_id/org_name default to None for backward compatibility with every existing
    caller. When the token's corresponding value is absent (org info not loaded), that
    token is left UNTOUCHED rather than substituted with something misleading — the
    expression then fails at evaluation (fail-closed), same as any other unresolved
    reference, instead of silently matching everything."""
    if not expr:
        return expr

    def _sub(m: re.Match) -> str:
        fn = m.group(1).upper()
        if fn == "USERID":
            return str(int(user_id))
        if fn in ("USEREMAIL", "USER"):
            return repr(str(email))
        if fn == "ORGID":
            return str(int(org_id)) if org_id is not None else m.group(0)
        if fn == "ORGNAME":
            return repr(str(org_name)) if org_name is not None else m.group(0)
        return m.group(0)  # pragma: no cover - regex only matches the names above
    return _USER_TOKEN.sub(_sub, expr)


async def _aggregate_source(db: AsyncSession, dataset_id: int) -> tuple[int, dict | None]:
    """The dataset whose rules govern `dataset_id`, and the aggregate spec if
    there is one.

    An aggregate dataset (services/aggregates.py) carries no rules of its own:
    it points at its DirectQuery source, and the source's rules are applied to
    it at read time. Rules are never copied -- a copy would drift the moment
    the source's changed. Every other dataset governs itself.
    """
    from ..models.models import Dataset
    row = (await db.execute(
        select(Dataset.aggregate_of_dataset_id, Dataset.aggregate_spec)
        .where(Dataset.id == dataset_id))).first()
    if row is None or row[0] is None:
        return dataset_id, None
    return int(row[0]), row[1]


async def resolve_rls_expr(db: AsyncSession, current_user: User, dataset_id: int) -> str | None:
    """Return the calling user's RowSecurityRule.filter_expr for this dataset, or None if
    unrestricted (is_org_admin roles bypass the lookup entirely; a role with no rule for
    this dataset is also None — unrestricted within the org, not "no access").

    USEREMAIL()/USER()/USERID() tokens are resolved to THIS user's identity here, so the
    returned expression is already user-specific — which also makes the DirectQuery cache
    key (built from the verbatim expression) differ per user, as it must for security."""
    if current_user.role.is_org_admin:
        return None
    dataset_id, _spec = await _aggregate_source(db, dataset_id)
    result = await db.execute(
        select(RowSecurityRule).where(
            RowSecurityRule.role_id == current_user.role_id, RowSecurityRule.dataset_id == dataset_id,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        return None
    org_name = None
    if _ORGNAME_PRESENT.search(rule.filter_expr):
        # Only paid for when the rule actually references it -- avoids a second query
        # on the (far more common) rule that doesn't. User.organization is a lazy
        # relationship that can't be awaited from async code without a fresh query.
        org_name = await db.scalar(select(Organization.name).where(Organization.id == current_user.org_id))
    expr = apply_user_context(
        rule.filter_expr, email=current_user.email, user_id=current_user.id,
        org_id=current_user.org_id, org_name=org_name,
    )
    if expr and _MYSCOPE_PRESENT.search(expr):
        # Same "only pay when referenced" stance as ORGNAME above. Expanded
        # LAST, deliberately: the substituted values are DATA (org-unit names
        # out of the database), and running apply_user_context over them would
        # re-read a value like "USEREMAIL()" as a token and rewrite it into the
        # caller's email -- turning stored data into identity and producing a
        # malformed literal. Nothing scans the expression after this point.
        expr = apply_scope(expr, await scope_values_for(db, current_user))
    return expr


async def expand_author_expressions(
    db: AsyncSession, current_user: User,
    filter_expr: str | None, calc_cols: list[dict] | None, measure_defs: list[dict] | None,
    *, email_override: str | None = None, org_id_override: int | None = None,
) -> tuple[str | None, list[dict], list[dict]]:
    """USEREMAIL()/USERID()/ORGID()/ORGNAME() previously only expanded inside RLS
    rules (resolve_rls_expr above). This is the choke point that makes them usable in
    ORDINARY author-written expressions too -- a dataset's default_filter_expr, a
    calculated column, or a measure -- so e.g. `owner == USEREMAIL()` works as a plain
    filter, not just a row-security rule. Expands for the VIEWING user (`current_user`),
    before the pandas pipeline ever sees the expression text. Shared by the live
    widget-data path and the PDF export/delivery path so the two can't drift.

    `email_override`/`org_id_override` (Task E1): an embedded report has no real
    user, only a host-signed JWT's declared `viewer_email`/`viewer_org` -- these
    substitute for `current_user.email`/`.org_id` in the expansion ONLY, never in
    anything that gates access (tenancy checks keep using `current_user.org_id`
    directly, never this override) -- see routers/embed.py."""
    calc_cols = calc_cols or []
    measure_defs = measure_defs or []
    texts = ([filter_expr] if filter_expr else []) \
        + [c.get("expression") for c in calc_cols if c.get("expression")] \
        + [m.get("expression") for m in measure_defs if m.get("expression")]
    if not texts:
        return filter_expr, calc_cols, measure_defs

    org_id = org_id_override if org_id_override is not None else current_user.org_id
    org_name = None
    if any(_ORGNAME_PRESENT.search(t) for t in texts):
        org_name = await db.scalar(select(Organization.name).where(Organization.id == org_id))

    def _expand(expr: str | None) -> str | None:
        return apply_user_context(
            expr, email=(email_override if email_override is not None else current_user.email),
            user_id=current_user.id, org_id=org_id, org_name=org_name,
        )

    new_filter = _expand(filter_expr)
    new_calc = [{**c, "expression": _expand(c["expression"])} if c.get("expression") else c for c in calc_cols]
    new_measures = [{**m, "expression": _expand(m["expression"])} if m.get("expression") else m for m in measure_defs]
    return new_filter, new_calc, new_measures


async def resolve_denied_columns(db: AsyncSession, current_user: User, dataset_id: int) -> list[str]:
    """Columns this user's role must not see on this dataset. Empty for admins and
    for roles with no rule -- mirroring resolve_rls_expr's shape exactly, so the two
    controls read the same way at every call site."""
    if current_user.role.is_org_admin:
        return []
    agg_id = dataset_id
    dataset_id, spec = await _aggregate_source(db, dataset_id)
    if dataset_id != agg_id and not (isinstance(spec, dict) and isinstance(spec.get("measures"), list)):
        # This IS an aggregate (the redirect found a source) but its spec is
        # missing or malformed, so the measure-expansion below has nothing to
        # expand from. Skipping it here (the `if spec:` guard further down)
        # would FAIL OPEN -- a source column denied to this role would deny
        # nothing on the aggregate. Raise instead: a broken spec must refuse
        # the read, never quietly serve it unfiltered.
        raise RuntimeError(
            f"aggregate dataset {agg_id} has no usable aggregate_spec; "
            f"refusing to resolve column security")
    from ..models.models import ColumnSecurityRule
    result = await db.execute(
        select(ColumnSecurityRule).where(
            ColumnSecurityRule.role_id == current_user.role_id,
            ColumnSecurityRule.dataset_id == dataset_id,
        )
    )
    denied: list[str] = []
    for rule in result.scalars().all():
        denied.extend(c for c in (rule.denied_columns or []) if isinstance(c, str))
    if spec:
        # A source column denied to this role denies, on the aggregate, the
        # column itself (if it is in the grain) and every measure built on it.
        # `row_count` is never denied: it reveals nothing about any column.
        from ..services.aggregates import derived_measure_names
        expanded = list(denied)
        for c in list(denied):
            expanded.extend(derived_measure_names(spec, c))
        denied = [c for c in dict.fromkeys(expanded) if c != "row_count"]
    return denied
