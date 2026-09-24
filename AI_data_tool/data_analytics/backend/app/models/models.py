from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, BigInteger, DateTime, ForeignKey, JSON, Boolean, LargeBinary, UniqueConstraint, text
from sqlalchemy.orm import relationship
from ..core.database import Base


class Dataset(Base):
    __tablename__ = "datasets"
    id          = Column(Integer, primary_key=True)
    name        = Column(String(255), nullable=False)
    description = Column(Text)
    filename    = Column(String(500))
    row_count   = Column(Integer, default=0)
    col_count   = Column(Integer, default=0)
    file_size   = Column(BigInteger, default=0)
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at  = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    calculated_columns  = Column(JSON, default=list)
    # Named, parameterized expression templates usable from calculated-column
    # expressions on this dataset -- see services/custom_functions.py. Each
    # item: {"name": str, "params": list[str], "expression": str}. Never
    # wired into apply_filter_expr/apply_rls_filter -- see that module's
    # docstring for why.
    custom_functions    = Column(JSON, default=list)
    column_formats      = Column(JSON, default=dict)
    # Post-aggregation measures — evaluated at the requesting widget's grouping grain,
    # unlike calculated_columns which are row-level and applied before aggregation.
    measures            = Column(JSON, default=list)
    # Per-column author overrides, keyed by column name: role (classification
    # override), aggregation (default when assigned to a measure role), hidden,
    # label. Detection stays the source of truth for dtype; this only overrides it.
    column_meta         = Column(JSON, default=dict)
    default_filter_expr = Column(Text, nullable=True)
    data_source_id      = Column(Integer, ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True)
    source_table        = Column(String(500), nullable=True)
    source_query        = Column(Text, nullable=True)
    # The visual query-builder's graph (table/joins/columns/filters/sort) that
    # compiled to source_query, so "Edit query" can reopen the builder hydrated
    # instead of losing the design to raw SQL. NULL for uploads, hand-SQL, and
    # any query-builder dataset whose SQL was since hand-edited (script mode is
    # one-way -- see QueryBuilderDialog).
    query_model         = Column(JSON, nullable=True)
    mode                = Column(String(20), nullable=False, default="import", server_default="import")
    # Scheduled refresh. NULL means unscheduled; last_refreshed_at is advanced even on
    # a failed attempt so a broken source retries on its schedule, not every tick.
    refresh_interval_minutes = Column(Integer, nullable=True)
    last_refreshed_at        = Column(DateTime(timezone=True), nullable=True)
    # An aggregate dataset: a scheduled GROUP BY over a DirectQuery source
    # (services/aggregates.py). The pointer is how read-time security finds
    # the SOURCE's rules -- they are never copied -- so it cascades: an
    # aggregate must not outlive the rules that govern it. `aggregate_spec`
    # is what was asked for ({"grain": [...], "measures": [...]}), kept so the
    # SQL can be recompiled and the UI can show it.
    aggregate_of_dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"),
                                     nullable=True, index=True)
    aggregate_spec          = Column(JSON, nullable=True)
    # Layer 1. Deprecation is INFERRED (name looks like _old/_bak/tmp_, zero rows,
    # stale relative to siblings) and is advisory only — it downranks a table in
    # retrieval and review, and never hides or deletes anything.
    is_deprecated      = Column(Boolean, nullable=False, default=False, server_default="0")
    description_source = Column(String(20), nullable=True)   # inferred | confirmed
    last_profiled_at   = Column(DateTime(timezone=True), nullable=True)
    org_id          = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    # WHO UPLOADED IT (0020). Datasets were org-wide readable by every member;
    # this is the anchor for `core.capability.readable_dataset_ids`, which now
    # answers "may this person open this data at all" -- owner, an explicit
    # DatasetShare, or a dashboard they can already see.
    #
    # SET NULL, not CASCADE: deleting a departing colleague's account must not
    # delete the company's data. A NULL owner reads as UNOWNED and stays open
    # (the same grandfathering reports use); migration 0020 backfills existing
    # rows to an org admin so a live install has none.
    created_by      = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                             nullable=True, index=True)

    columns          = relationship("DatasetColumn", back_populates="dataset", cascade="all, delete-orphan")
    analysis_results = relationship("AnalysisResult", back_populates="dataset", cascade="all, delete-orphan")
    hierarchy_nodes  = relationship("HierarchyNode", back_populates="dataset", cascade="all, delete-orphan")


class DatasetShare(Base):
    """SH1: a dataset has no owner concept in this codebase, so sharing is an
    org-admin-managed grant (mirrors the admin gating on row-security rules,
    not report ownership). The share itself only flags visibility/provenance
    (`shared: true` in the shared user's dataset list) -- read access to any
    dataset in the org is already open to every org member; RLS still narrows
    what the shared user sees, resolved as THEIR identity via the normal
    base-frame path."""
    __tablename__ = "dataset_shares"
    id          = Column(Integer, primary_key=True)
    dataset_id  = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    user_id     = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("dataset_id", "user_id", name="uq_dataset_share"),)

    dataset = relationship("Dataset")
    user    = relationship("User")


class DatasetColumn(Base):
    __tablename__ = "dataset_columns"
    id          = Column(Integer, primary_key=True)
    dataset_id  = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    name        = Column(String(255), nullable=False)
    dtype       = Column(String(50), nullable=False)
    missing_pct = Column(Float, default=0)
    stats       = Column(JSON, default=dict)
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)
    # Layer 1 inference. `stats` stays the untyped blob detection already writes;
    # these are the typed, queryable facts the metadata plane derives.
    # semantic_type: email | phone | url | ip | iban | national_id | coordinate |
    #                currency | percentage — what the value MEANS, beyond its dtype.
    semantic_type      = Column(String(40), nullable=True)
    description        = Column(Text, nullable=True)
    # inferred | confirmed — never absent when description is set.
    description_source = Column(String(20), nullable=True)
    # Provenance: the SOURCE column this one was imported from, when there is
    # one. The bridge between the two metadata stores — `source_columns` holds
    # what a live database's catalog and the describe pass know (the DBA's
    # COMMENT, the inferred sentence, `enum_labels` saying 2 means "paid"), and
    # `services/knowledge.py` resolves through this pointer at READ time rather
    # than copying the text here. A copy would drift the moment either side is
    # edited, which is the defect `relationships` vs `source_relationships`
    # already demonstrates. NULL is normal: an upload has no source column, and
    # a hand-written query whose output name matches nothing stays unlinked
    # because a wrong link puts another column's sentence beside these numbers.
    source_column_id   = Column(Integer, ForeignKey("source_columns.id", ondelete="SET NULL"),
                                nullable=True, index=True)
    dataset     = relationship("Dataset", back_populates="columns")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id            = Column(Integer, primary_key=True)
    dataset_id    = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    analysis_type = Column(String(100), nullable=False)
    result        = Column(JSON, nullable=False)
    #: What produced this and with what parameters. A regression result whose
    #: predictors are not recorded is uninterpretable; a result with no run
    #: cannot be found from the run that made it. Nullable: results a person
    #: ran by hand from the Analysis tab have neither.
    run_id        = Column(Integer, ForeignKey("automation_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    params        = Column(JSON, nullable=True)
    created_by    = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at    = Column(DateTime(timezone=True), default=datetime.utcnow)
    dataset       = relationship("Dataset", back_populates="analysis_results")


class Report(Base):
    __tablename__ = "reports"
    id                     = Column(Integer, primary_key=True)
    name                   = Column(String(255), nullable=False)
    description            = Column(Text)
    dataset_id             = Column(Integer, ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True)
    additional_dataset_ids = Column(JSON, default=list)
    theme                  = Column(String(20), nullable=False, default="default", server_default="default")
    # Report-level display rules: applied to every object on every page, ahead of any
    # widget-level rules, which override them by list order. See services/display_rules.py.
    display_rules          = Column(JSON, default=list)
    # Monotonic counter bumped by every mutation to this report or anything nested
    # under it. Every edit here persists immediately with no explicit save, so this
    # is what lets a client notice another session moved the report underneath it.
    revision               = Column(Integer, nullable=False, default=0, server_default="0")
    # Authorship, added late (0013): reports historically had no owner at all,
    # so every pre-existing row is NULL. NULL means "unowned" and is never
    # "mine" for anyone -- the same stance WorkspaceNode.created_by takes.
    # This drives GROUPING (my workspaces vs granted), never access control:
    # access stays role-scoped through ReportCapability.
    created_by             = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    # Publish/grant model (0014). An AUTHORED dashboard is a private draft
    # until published: invisible to other org members (list, tree, and every
    # /reports/{id} endpoint 404s) unless they hold a per-user grant. Published
    # = org members may OPEN it view-only -- the layout is locked; not one
    # widget can be moved without an explicit grant. A folder can publish its
    # whole subtree (WorkspaceNode.published). UNOWNED reports (created_by
    # NULL, i.e. everything from before 0013) are grandfathered into the old
    # default-open world and ignore this flag's absence -- flipping them would
    # lock every member out of every pre-existing report overnight.
    published              = Column(Boolean, nullable=False, default=False, server_default="0")
    #: Who made this report. "user" for one a person built; "automation" for
    #: one the Power Pi chain composed. Recents could not tell a finished
    #: automated report from a draft somebody started and abandoned, and both
    #: step 7 and the Home page need that difference. A string rather than a
    #: boolean because the next origin (a template, an import) is a value here
    #: rather than a second column.
    origin                 = Column(String(20), nullable=False, default="user",
                                    server_default="user", index=True)
    org_id                 = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    created_at             = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at             = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    pages                  = relationship("ReportPage", back_populates="report", cascade="all, delete-orphan",
                                          order_by="ReportPage.position")
    bookmarks              = relationship("Bookmark", back_populates="report", cascade="all, delete-orphan",
                                          order_by="Bookmark.position")


class ReportPage(Base):
    __tablename__ = "report_pages"
    id             = Column(Integer, primary_key=True)
    report_id      = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False)
    name           = Column(String(255), nullable=False, default="Page 1")
    title          = Column(String(255))
    page_type      = Column(String(20), nullable=False, default="normal")
    prompt_column  = Column(String(255))
    prompt_label   = Column(String(255))
    position       = Column(Integer, nullable=False, default=0)
    page_size      = Column(String(20), nullable=False, default="16:9", server_default="16:9")
    custom_width   = Column(Integer, nullable=True)
    custom_height  = Column(Integer, nullable=True)
    mobile_layout  = Column(JSON, nullable=True)
    #: A picture the page's objects sit on. An object can then stop drawing its
    #: own panel (`config.transparent`) and let the image show through, which is
    #: how a SAS page puts a bar chart and two big numbers over a photograph.
    background_url = Column(String(1000), nullable=True)
    #: packed (default tiled recipes) or free (opt-in canvas). NULL on legacy
    #: rows so the builder auto-packs them once.
    layout_mode    = Column(String(20), nullable=True)
    layout_template = Column(String(40), nullable=True)
    created_at     = Column(DateTime(timezone=True), default=datetime.utcnow)
    report         = relationship("Report", back_populates="pages")
    widgets        = relationship("ReportWidget", back_populates="page", cascade="all, delete-orphan")


class ReportVersion(Base):
    """One restorable snapshot of a report's CONTENT, captured automatically
    by `reports._bump_revision` just before every mutation commits (R2 of the
    2026-09-03 competitive assessment: the revision counter could detect a
    concurrent edit but offered no way back).

    `revision` is the counter value the snapshot describes — the state AS OF
    that revision, taken from the last-committed rows (core selects, so a
    request's own in-flight ORM changes never leak into their own "before"
    picture). `snapshot` holds report content (theme, display rules) plus
    every page with its widgets; identity fields (name, owner, publish state,
    classification) are deliberately NOT restored — going back to Tuesday's
    charts must not also rename or re-share the dashboard.

    Restoring recreates pages and widgets with NEW ids, which cascades away
    pins and per-page role visibility pointing at the old ones — stated in
    the restore endpoint's response, not hidden. Pruned to the newest
    `VERSIONS_KEPT` per report."""
    __tablename__ = "report_versions"
    id         = Column(Integer, primary_key=True)
    report_id  = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    revision   = Column(Integer, nullable=False, default=0)
    snapshot   = Column(JSON, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ReportWidget(Base):
    __tablename__ = "report_widgets"
    id          = Column(Integer, primary_key=True)
    page_id     = Column(Integer, ForeignKey("report_pages.id", ondelete="CASCADE"), nullable=False)
    widget_type = Column(String(50), nullable=False)
    title       = Column(String(255))
    config      = Column(JSON, default=dict)
    layout      = Column(JSON, default=lambda: {"x": 0, "y": 0, "w": 6, "h": 4})
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)
    page        = relationship("ReportPage", back_populates="widgets")


class HierarchyNode(Base):
    __tablename__ = "hierarchy_nodes"
    id          = Column(Integer, primary_key=True)
    dataset_id  = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    parent_id   = Column(Integer, ForeignKey("hierarchy_nodes.id", ondelete="CASCADE"), nullable=True)
    name        = Column(String(255), nullable=False)
    node_type   = Column(String(20), nullable=False, default="folder")
    column_name = Column(String(255))
    aggregation = Column(String(50))
    format      = Column(String(100))
    position    = Column(Integer, nullable=False, default=0)
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)
    dataset     = relationship("Dataset", back_populates="hierarchy_nodes")
    children    = relationship("HierarchyNode", cascade="all, delete-orphan")


class DataSource(Base):
    __tablename__ = "data_sources"
    id         = Column(Integer, primary_key=True)
    name       = Column(String(255), nullable=False)
    type       = Column(String(50), nullable=False)
    config     = Column(JSON, default=dict)
    cache_ttl_seconds = Column(Integer, nullable=False, default=60, server_default="60")
    # Layer 1. Consent for ARCHITECTURE.md open decision #4: may sample data reach
    # the model? Default off, per source, deliberately. Even a self-hosted endpoint
    # is a disclosure, and some sources must never be described by an LLM.
    allow_llm_sampling = Column(Boolean, nullable=False, default=False, server_default="0")
    # A plain-language account of what this database holds, written by Stage 5
    # from the tables, their columns and the relationships between them. This is
    # the artefact a person actually reads after a sync -- the column-level
    # descriptions are for the agent; this one is for the human deciding whether
    # the connection is even the right one.
    description        = Column(Text, nullable=True)
    description_source = Column(String(20), nullable=True)   # inferred | confirmed
    last_synced_at     = Column(DateTime(timezone=True), nullable=True)
    sync_status        = Column(String(20), nullable=False, default="pending", server_default="pending")
    org_id     = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    # Who added the connection (0020). Every member could previously list --
    # and DELETE -- every connection in the org; mutations now need the
    # creator or an admin. NULL means unowned (pre-0020, or seeded).
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                        nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    # T6: bumped every time a drift sync finds `changed: true` for this source.
    # DirectQuery result-cache keys fold this in, so a schema/data drift makes
    # every old cache entry for the source unaddressable by any new key --
    # nothing is actively evicted, the LRU just naturally ages the orphaned
    # entries out. Not itself a migration column that needs backfilling
    # semantics: 0 means "no drift observed since this column existed".
    cache_epoch = Column(Integer, nullable=False, default=0, server_default="0")
    # Phase 5: custom connector presets. NULL for every DataSource created
    # before this feature and for any plain (non-preset) connection.
    # ondelete="RESTRICT": deleting a preset that is still in use must fail
    # loudly, not silently turn a locked-down connection into an unlocked one.
    custom_connector_id = Column(Integer, ForeignKey("custom_connectors.id", ondelete="RESTRICT"),
                                  nullable=True, index=True)


class CustomConnector(Base):
    """A named, org-scoped preset of an existing connectors.py base type.
    `base_config` holds fixed field values (secrets encrypted, same as
    DataSource.config); `locked_fields` is the subset of those keys a
    DataSource created from this preset may not override. See
    docs/superpowers/specs/2026-09-09-custom-connector-framework-design.md."""
    __tablename__ = "custom_connectors"
    id            = Column(Integer, primary_key=True)
    org_id        = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    key           = Column(String(100), nullable=False)
    label         = Column(String(255), nullable=False)
    base_type     = Column(String(50), nullable=False)
    base_config   = Column(JSON, default=dict)
    locked_fields = Column(JSON, default=list)
    created_by    = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at    = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at    = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_custom_connectors_org_key"),)


class BoundarySet(Base):
    """Customer-supplied map boundaries: governorates, states, districts.

    The bundled atlas is countries only, and admin-1 for every country is tens
    of megabytes, so sub-national geometry cannot ship with the app. This is the
    org-scoped store for a file the customer already has — the capability SAS
    calls "custom boundaries from a geographic data provider".

    `geometry` holds the GeoJSON FeatureCollection verbatim. Verbatim because
    simplifying somebody's boundaries for them changes their map without telling
    them, and because the browser draws these directly. `key_properties` are the
    per-feature string properties a data column can be matched against —
    DETECTED at upload (services/boundary_sets.py), not configured, since real
    files name their regions `name`, `NAME_1`, `shapeName` or `ADM1_EN` and
    asking the uploader which means asking them to read the file first.
    """
    __tablename__ = "boundary_sets"
    id             = Column(Integer, primary_key=True)
    org_id         = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name           = Column(String(200), nullable=False)
    geometry       = Column(JSON, nullable=False)
    key_properties = Column(JSON, default=list)
    feature_count  = Column(Integer, nullable=False, default=0)
    created_by     = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at     = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_boundary_sets_org_name"),)


class PredictionModel(Base):
    """A fitted model kept so it can score rows it has never seen.

    Every analysis in this codebase refits and discards, which answers "what
    could predict this, and how well" and never "score these new rows". This is
    the store that closes that gap -- the capability SAS calls automated
    prediction, whose champion is a model you can then apply.

    `artifact` is a joblib pickle, so LOADING ONE EXECUTES CODE. Nothing
    accepts an uploaded model: the only writer is
    `services/analysis/model_store.py`, and rows are org-scoped like every
    other table here.

    `features` are the columns a caller must supply; `feature_columns` are the
    ENCODED columns the estimator expects, in order. They differ whenever a
    categorical predictor is one-hot encoded, and scoring has to reindex onto
    the second -- otherwise a frame missing one category shifts every feature
    after it and the estimator reads the wrong number as the wrong input.

    `features` is also a SECURITY record, not just bookkeeping. A saved model
    carries the influence of every column it was trained on, so a user who has
    since been denied one of them must be refused at score time -- the model
    would otherwise answer from data they are not allowed to read.
    """
    __tablename__ = "prediction_models"
    id              = Column(Integer, primary_key=True)
    org_id          = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id      = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    name            = Column(String(200), nullable=False)
    target          = Column(String(255), nullable=False)
    features        = Column(JSON, nullable=False, default=list)
    feature_columns = Column(JSON, nullable=False, default=list)
    categories      = Column(JSON, nullable=False, default=dict)
    task            = Column(String(32), nullable=False)
    model_family    = Column(String(64), nullable=False)
    score           = Column(Float, nullable=True)
    score_name      = Column(String(32), nullable=True)
    artifact        = Column(LargeBinary, nullable=False)
    #: The row filter in force when this model was FITTED, verbatim. A model is
    #: a derivative of the rows it saw -- a tree's leaves and a forest's splits
    #: are built from them -- so it may only be used by somebody who sees the
    #: same rows. `materialize` refuses governed data outright for the
    #: neighbouring reason; this can be narrower because the filter is recorded.
    trained_rls     = Column(Text, nullable=True)
    created_by      = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("org_id", "dataset_id", "name", name="uq_prediction_models_org_dataset_name"),)


class OrgReviewSettings(Base):
    """Report quality as CI (MASTER_PLAN Phase 7.4): the org's optional publish
    gate. A table of its own for the same reason as OrgMapSettings. No row =
    gate off, today's behaviour."""
    __tablename__ = "org_review_settings"
    id           = Column(Integer, primary_key=True)
    org_id       = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    publish_gate = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    updated_by   = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at   = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class OrgMapSettings(Base):
    """The org's basemap tile server (MASTER_PLAN Phase 4 item 4).

    A table of its own, not columns on `organizations`: create_all never alters
    a deployed table. One row per org; no row = no basemap, which is the
    default -- the platform runs air-gapped and ships no public tile service.
    """
    __tablename__ = "org_map_settings"
    id                = Column(Integer, primary_key=True)
    org_id            = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    tile_url          = Column(String(500), nullable=True)
    attribution       = Column(String(300), nullable=True)
    #: Swapped in for viewers whose system asks for more contrast.
    contrast_tile_url = Column(String(500), nullable=True)
    updated_by        = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at        = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class Organization(Base):
    __tablename__ = "organizations"
    id         = Column(Integer, primary_key=True)
    name       = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    roles = relationship("Role", back_populates="organization", cascade="all, delete-orphan")
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"
    id           = Column(Integer, primary_key=True)
    org_id       = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name         = Column(String(255), nullable=False)
    is_org_admin = Column(Boolean, nullable=False, default=False)
    created_at   = Column(DateTime(timezone=True), default=datetime.utcnow)

    organization = relationship("Organization", back_populates="roles")
    users        = relationship("User", back_populates="role")
    rules        = relationship("RowSecurityRule", back_populates="role", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True)
    org_id        = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role_id       = Column(Integer, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    email         = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(DateTime(timezone=True), default=datetime.utcnow)

    organization = relationship("Organization", back_populates="users")
    role         = relationship("Role", back_populates="users")


class OrgUnit(Base):
    """One node of an organization's own hierarchy: Country → Region → Branch →
    Department → Team, or whatever depth that org actually uses.

    NOT the same thing as `HierarchyNode`, which is a drill-down path over a
    dataset's COLUMNS (with aggregation and format) for charting. This is the
    org chart itself: the thing a person belongs to, and the thing row access
    is scoped by.

    `level_name` is free text ("Country", "Branch") rather than an enum,
    because the depth and the vocabulary differ per organization -- a fixed
    seven-level enum would force every org into one shape and make the
    six-level org store a NULL it has to remember to ignore.

    `match_value` is what the DATA says. The tree exists to answer "which
    values may this person see", and the answer has to be comparable against a
    column in a dataset -- so each node carries the literal that appears in the
    data (e.g. "Alexandria"), defaulting to its name when they agree.
    """
    __tablename__ = "org_units"
    __table_args__ = (UniqueConstraint("org_id", "parent_id", "name",
                                       name="uq_org_unit_sibling_name"),)
    id          = Column(Integer, primary_key=True)
    org_id      = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    # Self-referential: NULL parent is a root (e.g. a Country).
    parent_id   = Column(Integer, ForeignKey("org_units.id", ondelete="CASCADE"),
                         nullable=True, index=True)
    name        = Column(String(255), nullable=False)
    level_name  = Column(String(60))
    #: The value this unit takes in the DATA. Defaults to `name` on create.
    match_value = Column(String(255), nullable=False)
    position    = Column(Integer, nullable=False, default=0)
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)


class UserOrgUnit(Base):
    """Which org unit(s) a user is placed at. Access flows DOWNWARD from here.

    Per USER, not per role, and that is the whole point: two people can share
    the "Regional manager" role while sitting at different branches, and a
    role-scoped rule cannot express that -- it would need one role per branch,
    which is the combinatorial explosion this table exists to avoid.

    A user may hold several placements (a manager covering two regions); the
    resulting scope is the UNION of each placement's subtree.
    """
    __tablename__ = "user_org_units"
    __table_args__ = (UniqueConstraint("user_id", "org_unit_id",
                                       name="uq_user_org_unit"),)
    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    org_unit_id = Column(Integer, ForeignKey("org_units.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)


class RowSecurityRule(Base):
    __tablename__ = "row_security_rules"
    id          = Column(Integer, primary_key=True)
    role_id     = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    dataset_id  = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    filter_expr = Column(Text, nullable=False)
    # S0c: True when this rule (or its current filter_expr) was produced by
    # /admin/rls-rules/auto-generate rather than typed by an admin. Cleared the
    # moment an admin edits the rule through the normal update flow, so a later
    # auto-generate re-run never clobbers a human's deliberate change.
    auto_generated = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("role_id", "dataset_id", name="uq_role_dataset_rule"),)

    role    = relationship("Role", back_populates="rules")
    dataset = relationship("Dataset")


class Relationship(Base):
    __tablename__ = "relationships"
    id              = Column(Integer, primary_key=True)
    org_id          = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    from_dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    from_column     = Column(String(255), nullable=False)
    to_dataset_id   = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    to_column       = Column(String(255), nullable=False)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)
    # Provenance (Layer 1). `source` is the precedence ladder:
    #   confirmed > declared > inferred
    # A row a human approved is never overwritten by a resync; see
    # services/metadata/store.py, which is the ONLY writer that enforces this.
    # Rows that predate Layer 1 default to declared/1.0 — a user typed them in,
    # so they outrank anything inference proposes.
    confidence      = Column(Float, nullable=False, default=1.0, server_default="1.0")
    source          = Column(String(20), nullable=False, default="declared", server_default="declared")
    # Why this was proposed: {"overlap": 0.97, "name_score": 1.0, "sample_size": 1000,
    # "child_distinct": 812, "parent_distinct": 830}. The review UI renders this so a
    # human can judge the suggestion instead of being asked for blind trust.
    evidence        = Column(JSON, nullable=True)
    cardinality     = Column(String(20), nullable=True)   # one_to_many | many_to_one | one_to_one

    from_dataset = relationship("Dataset", foreign_keys=[from_dataset_id])
    to_dataset   = relationship("Dataset", foreign_keys=[to_dataset_id])


class Bookmark(Base):
    __tablename__ = "bookmarks"
    id         = Column(Integer, primary_key=True)
    report_id  = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False)
    name       = Column(String(255), nullable=False)
    position   = Column(Integer, nullable=False, default=0)
    state      = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    report     = relationship("Report", back_populates="bookmarks")


class AuditLogEntry(Base):
    """Append-only record of who did what, when.

    Written by the mutation paths, never updated or deleted through the app -- an
    audit log that can be edited by the actions it audits is theatre. Reads are
    org-scoped and admin-only.
    """
    __tablename__ = "audit_log"
    id         = Column(Integer, primary_key=True)
    org_id     = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_email = Column(String(255))          # denormalised: the log must outlive the user row
    action     = Column(String(50), nullable=False)    # e.g. "report.delete", "dataset.export"
    entity     = Column(String(50))                    # "report", "dataset", ...
    entity_id  = Column(Integer)
    detail     = Column(String(500))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class OrgTheme(Base):
    """An org-defined chart palette, selectable per report as theme "custom:<id>".

    A separate table rather than a column on Report because Report.theme is a
    String(20) in deployed databases and create_all never alters existing tables --
    and because a palette defined once should be reusable across every report in the
    org, which a per-report blob would prevent.
    """
    __tablename__ = "org_themes"
    id         = Column(Integer, primary_key=True)
    org_id     = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name       = Column(String(100), nullable=False)
    colors     = Column(JSON, nullable=False, default=list)   # ["#rrggbb", ...]
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ReportParameter(Base):
    """A named, typed value a report's viewers can set.

    Referenced as `@name` in widget filters and calculated expressions. The TYPE is
    load-bearing, not descriptive: substitution encodes the value as a literal of that
    type before any expression is evaluated, which is what keeps a parameter from
    being an injection path into the eval sandbox.
    """
    __tablename__ = "report_parameters"
    id            = Column(Integer, primary_key=True)
    report_id     = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    name          = Column(String(60), nullable=False)     # identifier-ish; validated at the router
    param_type    = Column(String(20), nullable=False, default="number")  # number | text | date
    label         = Column(String(120))
    default_value = Column(String(500))
    # For text parameters: an optional fixed choice list, so a prompt can be a
    # dropdown instead of free text.
    options       = Column(JSON, default=list)
    position      = Column(Integer, nullable=False, default=0)


class ReportSchedule(Base):
    """A recurring delivery of one report's data by email.

    `creator_user_id` is the security identity, not bookkeeping: a scheduled run has
    no user at the keyboard, so row-level security is resolved AS THE CREATOR. A
    schedule made by a restricted user delivers that user's slice, forever, to every
    recipient -- and deleting the creator disables the schedule rather than letting
    it fall back to unfiltered data.
    """
    __tablename__ = "report_schedules"
    id               = Column(Integer, primary_key=True)
    org_id           = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id        = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False)
    creator_user_id  = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    interval_minutes = Column(Integer, nullable=False)
    recipients       = Column(JSON, nullable=False, default=list)   # email strings
    subject          = Column(String(200))
    last_run_at      = Column(DateTime(timezone=True), nullable=True)
    last_status      = Column(String(200))
    created_at       = Column(DateTime(timezone=True), default=datetime.utcnow)
    # T3: an IANA zone name (e.g. "Asia/Riyadh") the scheduler interprets this
    # schedule's calendar hour/minute in, via zoneinfo. NULL means UTC -- the
    # historical behaviour, unchanged for every row that predates this column.
    timezone         = Column(String(64), nullable=True)


class Delivery(Base):
    """T3: one log row per delivery ATTEMPT -- a schedule's digest/PDF send or
    an alert's fire, success and failure alike. Written fire-and-forget via
    `query_log.log_delivery_sync`, the same dedicated-sync-engine contract as
    QueryRun/ShareLinkAccess: a logging failure must never fail, slow, or
    lose the outcome of the delivery it describes.

    `schedule_id` and `report_id` are both NULL for `kind="alert"` rows -- an
    alert watches a dataset, not a report or a schedule, so neither FK
    applies to it.
    """
    __tablename__ = "deliveries"
    id            = Column(Integer, primary_key=True)
    org_id        = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    schedule_id   = Column(Integer, ForeignKey("report_schedules.id", ondelete="CASCADE"), nullable=True, index=True)
    report_id     = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=True, index=True)
    kind          = Column(String(20), nullable=False)              # schedule | alert | manual
    status        = Column(String(10), nullable=False)              # ok | error
    error         = Column(Text, nullable=True)
    artifact_kind = Column(String(10), nullable=False, default="none")  # pdf | csv | xlsx | none
    duration_ms   = Column(Integer, nullable=True)
    created_at    = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class DataAlert(Base):
    """A data condition watched on a schedule, firing an email on its rising edge.

    The condition is a display-rule-style expression over a dataset, evaluated by the
    same sandbox widgets use. Rising-edge only: an alert that emails every tick while
    the condition stays true trains everyone to delete the emails, which is worse
    than no alert.
    """
    __tablename__ = "data_alerts"
    id               = Column(Integer, primary_key=True)
    org_id           = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id       = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    creator_user_id  = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name             = Column(String(200), nullable=False)
    expression       = Column(Text, nullable=False)                 # e.g. "SUM(revenue) < 100000"
    interval_minutes = Column(Integer, nullable=False, default=60)
    recipients       = Column(JSON, nullable=False, default=list)
    last_checked_at  = Column(DateTime(timezone=True), nullable=True)
    last_state       = Column(String(10), nullable=False, default="clear")   # clear | firing
    last_status      = Column(String(200))
    created_at       = Column(DateTime(timezone=True), default=datetime.utcnow)


class PageTemplate(Base):
    """A serialised page (or container subtree), instantiable into any report.

    The payload stores widgets with INDEX-based container references rather than ids:
    ids are meaningless outside the page they came from, and rehydration assigns new
    ones -- the remap through indices is what keeps a templated container attached to
    its children wherever the template lands.
    """
    __tablename__ = "page_templates"
    id         = Column(Integer, primary_key=True)
    org_id     = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name       = Column(String(120), nullable=False)
    kind       = Column(String(20), nullable=False, default="page")   # page | object
    payload    = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class RecentView(Base):
    """The last time ONE user opened ONE dashboard.

    Home's "Recents" previously ordered by `reports.updated_at`, which answers
    "what changed" -- a different question, and the wrong one: a dashboard
    somebody else edited jumps to the top of YOUR recents, and one you read
    every morning without editing never appears at all.

    Deliberately UPSERT-per-(user, report) rather than an append-only event
    log. A history of every open would grow without bound and be read only as
    "max(viewed_at) per report" anyway; one row per pair keeps the read a
    plain indexed sort and needs no retention policy. The audit log already
    exists for the append-only, admin-facing account of what happened -- this
    is a personal convenience, and conflating the two would put a privacy
    surface into a feature that is meant to be forgettable.

    Cascades on both FKs: a deleted report or departed user leaves no orphan
    pointing at nothing.
    """
    __tablename__ = "recent_views"
    __table_args__ = (UniqueConstraint("user_id", "report_id",
                                       name="uq_recent_user_report"),)
    id        = Column(Integer, primary_key=True)
    user_id   = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    report_id = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    viewed_at = Column(DateTime(timezone=True), default=datetime.utcnow,
                       onupdate=datetime.utcnow, nullable=False)


class PinnedTile(Base):
    """One widget pinned to a user's home dashboard.

    A REFERENCE, not a copy: the tile stores which widget, never the widget's
    config or its data. Rendering re-reads the live widget and re-queries
    widget-data as the VIEWER, so the tile shows exactly what that person would
    see inside the report -- same RLS, same column mask, same numbers. A
    snapshot would drift from the report and, worse, freeze one identity's
    row visibility into a picture shown to nobody-in-particular.

    Per user on purpose (`user_id`, not org): a home dashboard is the set of
    numbers ONE person checks daily. Deleting the widget or the user cascades
    the pin away -- a tile pointing at nothing is not worth a tombstone.
    """
    __tablename__ = "pinned_tiles"
    # Two pin kinds share the table because they share ONE dashboard grid and
    # one ordering. Postgres treats NULLs as distinct in unique constraints, so
    # widget pins (finding_key NULL) never collide on the insight unique and
    # insight pins (widget_id NULL) never collide on the widget unique.
    __table_args__ = (UniqueConstraint("user_id", "widget_id",
                                       name="uq_pin_user_widget"),
                      UniqueConstraint("user_id", "dataset_id", "finding_key",
                                       name="uq_pin_user_finding"),)
    id         = Column(Integer, primary_key=True)
    org_id     = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    #: Widget pin: which widget. NULL for insight pins.
    widget_id  = Column(Integer, ForeignKey("report_widgets.id", ondelete="CASCADE"), nullable=True)
    #: Insight pin: which dataset + which finding. The key is the same identity
    #: apply_novelty uses -- `kind|col|col` with columns sorted -- so a pinned
    #: finding and its NEW/CHANGED accent can never disagree about what "the
    #: same finding" means. Both NULL for widget pins.
    dataset_id  = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True)
    finding_key = Column(Text, nullable=True)
    #: Dashboard order (dense, 1-based) and size token ('s' | 'm' | 'l').
    position   = Column(Integer, nullable=True)
    size       = Column(String(1), nullable=False, default="m", server_default="m")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class PageRoleVisibility(Base):
    """Restricts one report page to specific roles.

    No rows for a page = everyone in the org sees it (the default, and the migration
    story for every existing page). Any rows = only those roles, plus org admins --
    an admin locked out of a page could not administer the restriction that locked
    them out. Enforced SERVER-SIDE when the report is read: a page the viewer cannot
    see is absent from the response, not hidden by the client, so its widgets' data
    is never serialised to them at all.
    """
    __tablename__ = "page_role_visibility"
    id      = Column(Integer, primary_key=True)
    page_id = Column(Integer, ForeignKey("report_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)


class ReportUserGrant(Base):
    """'Share to': a per-USER capability grant on one authored dashboard.

    Distinct from ReportCapability (role-scoped, admin-managed, a RESTRICTION
    on the grandfathered default-open world) in both principal and direction:
    this row is created by the dashboard's AUTHOR, names one user, and OPENS
    access that publishing alone never gives -- publish makes a dashboard
    viewable, only a grant makes it editable. A grant also makes an
    UNPUBLISHED draft visible to that one user (share a draft for review
    without publishing it to the whole org).

    Levels reuse the capability vocabulary: 'view' (see a draft), 'edit'
    (design: move widgets, add pages), 'data' (edit plus dataset authoring).
    """
    __tablename__ = "report_user_grants"
    id         = Column(Integer, primary_key=True)
    report_id  = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    level      = Column(String(5), nullable=False, default="edit")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("report_id", "user_id", name="uq_report_user_grant"),
    )


class ReportCapability(Base):
    """A role's capability level on one report -- SAS's three additive viewer
    levels, per report per principal.

    Levels, low to high: 'view' (read + interact only), 'edit' (change the
    report's structure -- widgets, pages, layout, rules), 'data' (edit PLUS the
    dataset's calculated columns, measures and prep pipeline). No row for a
    (report, role) pair = the org default of 'data' (full), so this is an
    opt-in RESTRICTION layered onto today's everyone-can-edit behaviour rather
    than a gate that breaks it. Org admins are always 'data' and cannot be
    locked out of administering the report. Enforced server-side on the
    report-mutation and data-authoring endpoints; the client mirrors it to hide
    what the server would refuse.
    """
    __tablename__ = "report_capability"
    id        = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id   = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    level     = Column(String(10), nullable=False, default="data")


class ColumnSecurityRule(Base):
    """Columns a role must not see on a dataset.

    The import path DROPS the denied columns before shaping, so a widget referencing
    one behaves as if the column does not exist. The DirectQuery path FAILS CLOSED
    instead: its SQL is built from column names, and silently rewriting a query is
    worse than refusing it. Org admins are exempt, as with row-level security.
    """
    __tablename__ = "column_security_rules"
    id             = Column(Integer, primary_key=True)
    role_id        = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    dataset_id     = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    denied_columns = Column(JSON, nullable=False, default=list)


class DataView(Base):
    """A reusable semantic bundle: one dataset's authored layer -- classifications,
    default aggregations, formats, calculated columns, measures, filter, prep steps
    and hierarchy -- snapshotted by name, applicable to any compatible dataset.

    The payload matches by COLUMN NAME on apply, and anything referencing a column
    the target lacks is skipped and reported rather than failing the whole apply:
    a bundle built on last quarter's extract should land cleanly on this quarter's.
    Reserved __keys are never bundled -- export policy and a dataset's own prep
    governance don't travel with a semantic layer.
    """
    __tablename__ = "data_views"
    id              = Column(Integer, primary_key=True)
    org_id          = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name            = Column(String(255), nullable=False)
    payload         = Column(JSON, nullable=False, default=dict)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)
    creator_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    #: SAS's "admin default": the view applied to every dataset uploaded into
    #: this org from now on. At most one per org -- two defaults would be a coin
    #: toss dressed up as a setting -- enforced by the endpoint that sets it
    #: rather than by a partial index, which not every supported database has.
    is_default      = Column(Boolean, nullable=False, default=False,
                             server_default=text("false"))


class ReportClassification(Base):
    """A sensitivity label on one report (Public / Internal / Confidential /
    Restricted). Stored in its own table because Report predates this and
    create_all never ALTERs a live table to add a column. One row per report
    (unique report_id); absence means unclassified.
    """
    __tablename__ = "report_classifications"
    id         = Column(Integer, primary_key=True)
    report_id  = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    org_id     = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    label      = Column(String(40), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class ApiKey(Base):
    """A long-lived credential for machine/agent access (e.g. the MCP server), issued
    by a user and acting AS that user — so it inherits their org, role, RLS and report
    capabilities exactly. Only the SHA-256 of the full key is stored; the key itself is
    shown once at creation and never again. Lookup is by the non-secret `prefix`, then
    the hash is checked. Revoking is deleting the row. New table, so create_all makes it
    without a migration.
    """
    __tablename__ = "api_keys"
    id           = Column(Integer, primary_key=True)
    org_id       = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id      = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name         = Column(String(120), nullable=False)
    prefix       = Column(String(16), nullable=False, unique=True, index=True)
    key_hash     = Column(String(64), nullable=False)
    created_at   = Column(DateTime(timezone=True), default=datetime.utcnow)
    last_used_at = Column(DateTime(timezone=True), nullable=True)


class OrgIdp(Base):
    """A single organization's SSO identity provider. Its own table (create_all-made,
    no migration); one IdP per org, resolved at login by the user's email domain. v1 is
    OIDC (protocol='oidc'); the SAML columns live in `config` for a later phase. The
    client secret is stored ENCRYPTED (services/secrets.py) like any other credential.
    SSO authenticates users an admin already created — a successful login whose email
    has no user in the org is refused, not provisioned.
    """
    __tablename__ = "org_idps"
    id            = Column(Integer, primary_key=True)
    org_id        = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    protocol      = Column(String(10), nullable=False, default="oidc")   # oidc | saml
    enabled       = Column(Boolean, nullable=False, default=True)
    email_domain  = Column(String(255), nullable=False, index=True)      # e.g. "acme.com" → this org
    issuer        = Column(String(500))       # OIDC issuer (…/.well-known/openid-configuration base)
    client_id     = Column(String(255))
    client_secret = Column(String(1000))      # encrypted at rest
    config        = Column(JSON, default=dict)  # protocol extras (SAML metadata/cert later)
    created_at    = Column(DateTime(timezone=True), default=datetime.utcnow)


class SamlAuthnRequest(Base):
    """A pending SP-initiated SAML AuthnRequest, tracked so the assertion that comes back
    can be bound to it (InResponseTo) and used exactly once. The SAML ACS is a cross-site
    POST from the IdP, where a SameSite=lax cookie would not be sent — so this transient
    state lives in the DB, not a cookie. Rows are deleted on consumption and swept by age.
    """
    __tablename__ = "saml_authn_requests"
    id         = Column(String(64), primary_key=True)   # the AuthnRequest ID == InResponseTo
    org_id     = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    acs_url    = Column(String(1000), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class OrgMcpAccess(Base):
    """Per-organization switch for MCP / machine (API-key) access, controlled by a
    platform super-admin. Its own table (create_all-made, no migration); one row per
    org. Absence means enabled — the default — so turning MCP off is an explicit act
    and existing access is never silently withdrawn.
    """
    __tablename__ = "org_mcp_access"
    id      = Column(Integer, primary_key=True)
    org_id  = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    enabled = Column(Boolean, nullable=False, default=True)


class OrgParent(Base):
    """One edge of the organization hierarchy: an org's parent. Its own table because
    Organization predates it and create_all never ALTERs a live table to add a column.
    One row per org (unique org_id); absence means a top-level org. Structural only for
    now — it does NOT grant a parent org's users access to a child's data (per-org
    isolation is unchanged); rolling data up the tree is a deliberate later decision.
    """
    __tablename__ = "org_parents"
    id            = Column(Integer, primary_key=True)
    org_id        = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    parent_org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)


class CommonFilter(Base):
    """A report-level filter applied to every widget on the report — defined once,
    edited in one place, and it propagates everywhere (SAS's shared common filter,
    Power BI's "filters on all pages"). Its own table because Report predates it and
    create_all never ALTERs a live table. A widget whose dataset lacks the column is
    unaffected: the shaper's _apply_filters skips columns it does not have.
    """
    __tablename__ = "common_filters"
    id         = Column(Integer, primary_key=True)
    report_id  = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    column     = Column(String(255), nullable=False)
    op         = Column(String(10), nullable=False, default="eq")
    value      = Column(JSON)                       # scalar, or a list for op="in"
    position   = Column(Integer, nullable=False, default=0)


class WidgetTemplate(Base):
    """A configured widget saved by name for reuse: its type plus its whole config
    (roles, formatting, rules, filters, ranks, sorting). Org-wide, so a formatted
    object built once can be dropped onto any report -- the object-level analogue of
    a DataView. Apply is a client-side insert of a new widget carrying this config,
    so a template never binds to a particular dataset's ids; matching is by the same
    column-name convention the rest of the builder uses.
    """
    __tablename__ = "widget_templates"
    id              = Column(Integer, primary_key=True)
    org_id          = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name            = Column(String(255), nullable=False)
    widget_type     = Column(String(50), nullable=False)
    config          = Column(JSON, nullable=False, default=dict)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)
    creator_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class Notification(Base):
    """An in-app notification for one user: an alert fired, a scheduled delivery
    failed, a refresh broke. Produced by the background loop AND readable in the
    UI bell -- email may be unconfigured or ignored, and a failure only an SMTP
    log knows about is a failure nobody knows about.
    """
    __tablename__ = "notifications"
    id         = Column(Integer, primary_key=True)
    org_id     = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind       = Column(String(40), nullable=False)           # alert | schedule | refresh | comment
    text       = Column(String(500), nullable=False)
    link       = Column(String(500), nullable=True)           # in-app path, e.g. /reports/7
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    read_at    = Column(DateTime(timezone=True), nullable=True)


class ReportComment(Base):
    """Discussion on a report: flat, newest-last, optionally pinned to a page.
    Commenting notifies every prior participant on that report except the author
    -- the report has no owner field, so the thread's participants ARE the
    audience."""
    __tablename__ = "report_comments"
    id         = Column(Integer, primary_key=True)
    org_id     = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id  = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id    = Column(Integer, ForeignKey("report_pages.id", ondelete="SET NULL"), nullable=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    text       = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ShareLink(Base):
    """A signed guest link to one report: anyone holding the URL sees the report
    read-only, resolved AS THE LINK'S CREATOR (same identity rule as schedules --
    "no viewer" must never mean "no RLS", and here it means the sharer knowingly
    exposes exactly their own slice). Only the token's sha256 is stored: a leaked
    database row cannot be turned back into a working URL.
    """
    __tablename__ = "share_links"
    id              = Column(Integer, primary_key=True)
    org_id          = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id       = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    creator_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash      = Column(String(64), nullable=False, unique=True, index=True)
    expires_at      = Column(DateTime(timezone=True), nullable=False)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)
    revoked_at      = Column(DateTime(timezone=True), nullable=True)
    # T12: an optional frozen copy of the report's render-definition (pages +
    # widgets, in the same shape GET /reports/{id} returns) taken at link-mint
    # time. `pinned` is what the sharer asked for; `snapshot` is only ever
    # non-null when it is true. The PIN covers layout/config only -- widget
    # DATA is still resolved live against the current dataset, so a pinned
    # link's numbers keep moving even though its pages/widgets do not.
    snapshot        = Column(JSON, nullable=True)
    pinned          = Column(Boolean, nullable=False, default=False)


class ShareLinkAccess(Base):
    """S4: one row per rendering of a guest link (`GET /shared/{token}`),
    fire-and-forget via the query_log pattern -- never on the request's own
    transaction, never able to fail or slow the render it describes. `ip_hash`
    is a salted hash, never the raw address: this is an access log for the
    link's owner, not a durable store of visitor IPs. `viewer_user_id` is set
    only when the render resolved as an authenticated in-org viewer (S3);
    NULL means truly anonymous or creator-fallback."""
    __tablename__ = "share_link_access"
    id             = Column(Integer, primary_key=True)
    share_link_id  = Column(Integer, ForeignKey("share_links.id", ondelete="CASCADE"), nullable=False, index=True)
    viewer_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ts             = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    ip_hash        = Column(String(64), nullable=True)
    user_agent     = Column(String(200), nullable=True)


class EmbedConfig(Base):
    """Task E1: a host-signed embed credential for one report. Like ShareLink,
    an embed has a CREATOR (`created_by`, the admin who minted it) -- the host
    application signs its own JWTs with this config's secret
    (`secret_encrypted`, enc:v2 at rest, shown to that admin exactly once and
    never again), but the DATA an embed exposes still resolves row-level
    security and denied columns as the creator's own identity, exactly as a
    ShareLink guest does (see routers/shared.py `_resolve_identity` and
    routers/embed.py) -- an embed can never expose more than its creator's own
    slice, no matter what the host's JWT claims. `viewer_email`/`viewer_org`
    in the token only override USEREMAIL()/ORGID() expansion inside a
    dataset's OWN author expressions; they never substitute for the creator's
    role in RLS/column-security resolution, and the JWT's own `filters` claim
    still composes ON TOP of that creator-scoped result, narrowing further.
    `allowed_origins` is an optional Origin/Referer allowlist for
    browser-embedded iframes; an empty list means no origin restriction
    (documented tradeoff, not a bug: some hosts embed from Referer-less
    contexts). `enabled=False` (revoked) and disabled configs 404 identically
    to a config that never existed."""
    __tablename__ = "embed_configs"
    id               = Column(Integer, primary_key=True)
    org_id           = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id        = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by       = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name             = Column(String(255), nullable=False)
    secret_encrypted = Column(Text, nullable=False)
    allowed_origins  = Column(JSON, default=list)
    enabled          = Column(Boolean, nullable=False, default=True)
    created_at       = Column(DateTime(timezone=True), default=datetime.utcnow)
    last_used_at     = Column(DateTime(timezone=True), nullable=True)
    __table_args__   = (UniqueConstraint("report_id", "name", name="uq_embed_config_name"),)


class Quota(Base):
    """Task E2: per-tenant usage ceilings. One row per org, all four limits
    nullable -- NULL means unlimited, which is the default (byte-preserved)
    behavior for every org that has no row here at all. Enforced in
    services/quotas.py: `max_queries_per_day`/`max_agent_asks_per_day` count
    query_runs/agent_runs since midnight UTC; `max_storage_mb` sums
    Dataset.file_size for the org's current (non-deleted -- deletes are hard
    in this schema) datasets; `max_concurrent_asks` is an in-process counter,
    not a DB count. Managed by a platform super-admin only (see
    dependencies.require_super_admin), same tier as routers/platform.py's
    org CRUD -- there is no separate "org admin can quota their own org"
    concept in this codebase."""
    __tablename__ = "quotas"
    id                   = Column(Integer, primary_key=True)
    org_id               = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True)
    max_queries_per_day   = Column(Integer, nullable=True)
    max_agent_asks_per_day = Column(Integer, nullable=True)
    max_storage_mb        = Column(Integer, nullable=True)
    max_concurrent_asks    = Column(Integer, nullable=True)
    created_at           = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at           = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class ReportTranslation(Base):
    """Per-locale text overrides for one report: widget titles and text-widget
    content, keyed "w<id>" / "c<id>". Applied at VIEW time by browser locale;
    the authored strings stay the single source the builder edits."""
    __tablename__ = "report_translations"
    id         = Column(Integer, primary_key=True)
    report_id  = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    locale     = Column(String(10), nullable=False)
    payload    = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 — Connectors & Ingestion (metadata plane)
#
# See docs/superpowers/specs/2026-08-24-layer1-connectors-ingestion-design.md.
# These four tables are the METADATA plane: cheap, cached, derived, and rebuilt
# by a sync run. They are never on a user's query path — widget_data and
# direct_query do not read them. That separation is the point: the agent
# iterates over metadata without touching a customer's production database.
# ─────────────────────────────────────────────────────────────────────────────


class ColumnStats(Base):
    """Per-column statistics, read from the engine's own catalog where possible
    (pg_stats in milliseconds) rather than computed by scanning (minutes).

    `exact` records which path produced the row: False means these are the
    engine's estimates, True means we aggregated the real values. Callers that
    care about correctness rather than shape MUST check it — an estimated
    distinct_count is fine for deciding dimension-vs-measure, and wrong for
    anything a user is shown as fact.

    `top_k` is the highest-value column here: knowing status is
    ('active','churned') and not ('A','C') is what stops a generated query
    inventing WHERE values. Populated whenever distinct_count < 100.
    """
    __tablename__ = "column_stats"
    id                = Column(Integer, primary_key=True)
    # Exactly one of these is set. Statistics are computed for a column of the
    # SOURCE catalog (every column of every table the connection can see) or for
    # a column of a user-created dataset. Both are real, and neither subsumes
    # the other: the catalog describes the database, the dataset describes what
    # someone chose to work with.
    dataset_column_id = Column(Integer, ForeignKey("dataset_columns.id", ondelete="CASCADE"),
                               nullable=True, unique=True, index=True)
    source_column_id  = Column(Integer, ForeignKey("source_columns.id", ondelete="CASCADE"),
                               nullable=True, unique=True, index=True)
    null_ratio        = Column(Float, nullable=True)
    distinct_count    = Column(BigInteger, nullable=True)
    # [{"value": "active", "count": 812, "ratio": 0.81}, ...] — ordered, most common first.
    top_k             = Column(JSON, nullable=True)
    min_value         = Column(Text, nullable=True)
    max_value         = Column(Text, nullable=True)
    avg_width         = Column(Integer, nullable=True)
    exact             = Column(Boolean, nullable=False, default=False, server_default="0")
    computed_at       = Column(DateTime(timezone=True), default=datetime.utcnow)


class SchemaVersion(Base):
    """One row per detected schema change on a data source.

    The fingerprint is a SHA-256 over the sorted (schema, table, column, dtype,
    nullable) tuples for the whole source, so an identical schema always hashes
    identically regardless of catalog ordering. A new row is written only when
    the hash differs from the newest existing row.

    Drift emits an event and does NOT silently resync: a confirmed annotation on
    a column that has disappeared is flagged as orphaned in `diff`, never
    deleted. Silently dropping a human's confirmation is the one thing this
    layer must never do.
    """
    __tablename__ = "schema_versions"
    id             = Column(Integer, primary_key=True)
    data_source_id = Column(Integer, ForeignKey("data_sources.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    org_id         = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    fingerprint    = Column(String(64), nullable=False)
    # {"added": [...], "removed": [...], "changed": [...], "orphaned_annotations": [...]}
    diff           = Column(JSON, nullable=True)
    detected_at    = Column(DateTime(timezone=True), default=datetime.utcnow)


class SyncRun(Base):
    """One execution of the six-stage metadata pipeline against a data source.

    `stages` is the per-stage record — [{"name": "profile", "status": "ok",
    "ms": 412, "detail": {...}}, ...]. Stages are independently guarded: one
    failing is recorded and the run continues wherever the next stage does not
    depend on it, so a source that blocks TABLESAMPLE still gets its statistics
    and its drift check. A run is `failed` only when a stage that everything
    downstream needs could not complete.
    """
    __tablename__ = "sync_runs"
    id             = Column(Integer, primary_key=True)
    data_source_id = Column(Integer, ForeignKey("data_sources.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    org_id         = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    trigger        = Column(String(20), nullable=False)   # manual | scheduled | drift
    status         = Column(String(20), nullable=False)   # running | ok | failed | cancelled
    stages         = Column(JSON, nullable=False, default=list)
    error          = Column(Text, nullable=True)
    started_at     = Column(DateTime(timezone=True), default=datetime.utcnow)
    finished_at    = Column(DateTime(timezone=True), nullable=True)


class Watermark(Base):
    """Incremental-sync cursor for one dataset.

    `strategy='full'` means re-read everything each sync; `'incremental'` means
    resume from cursor_value on cursor_column. Stored as text because the cursor
    may be a timestamp, a bigint id, or an opaque token depending on the source —
    the column that produced it knows how to compare it.
    """
    __tablename__ = "watermarks"
    id            = Column(Integer, primary_key=True)
    dataset_id    = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"),
                           nullable=False, unique=True, index=True)
    strategy      = Column(String(20), nullable=False, default="full")
    cursor_column = Column(String(255), nullable=True)
    cursor_value  = Column(Text, nullable=True)
    updated_at    = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class Materialization(Base):
    """O3: the refresh-authoritative parquet manifest for one dataset.

    Distinct from the frame_cache sidecar (write_parquet_sidecar in
    services/frame_cache.py), which this table deliberately REUSES rather than
    duplicates: `path` is the exact same "<csv>.parquet" file the sidecar
    already writes and the loader (frame_cache._parse) already prefers over a
    CSV re-parse whenever it is present and not older than the CSV (mtime
    check). This table does not add a second parquet write per refresh -- it
    adds the metadata a sidecar has no room for: which refresh produced the
    file (full|incremental), how many rows it has, its column list, and the
    watermark cursor value active at write time, all queryable without
    touching the filesystem (see the lineage graph's `materialized`/
    `row_count` fields).

    One row per dataset is the contract: services/dataset_refresh.py's
    write_materialization() supersedes (deletes) any prior row for the
    dataset on every refresh, unlinking that prior row's file ONLY when no
    surviving row still points at the same path -- in practice the path never
    changes (it is always the current CSV's sidecar), so pruning here is
    manifest bookkeeping, not a real file churn.
    """
    __tablename__ = "materializations"
    id              = Column(Integer, primary_key=True)
    dataset_id      = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"),
                             nullable=False, unique=True, index=True)
    path            = Column(String(1000), nullable=False)
    kind            = Column(String(20), nullable=False)  # full | incremental
    row_count       = Column(Integer, nullable=False, default=0)
    columns         = Column(JSON, nullable=False, default=list)
    watermark_value = Column(Text, nullable=True)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# The source catalog — what is actually IN a connected database.
#
# Distinct from `datasets` on purpose. A Dataset is a slice a PERSON chose to
# import or query; the catalog below is everything the connection can see,
# whether or not anyone has made a dataset from it. That difference is the whole
# point: a description built only from datasets describes the part of the
# database someone already knew about, which is the opposite of what a person
# connecting a new source needs.
#
# Populated by stage 1 (discover) from the live connection via SQLAlchemy's
# Inspector, and refreshed on every sync.
# ─────────────────────────────────────────────────────────────────────────────


class SourceObject(Base):
    """One table, view or materialized view in a connected database."""
    __tablename__ = "source_objects"
    id             = Column(Integer, primary_key=True)
    data_source_id = Column(Integer, ForeignKey("data_sources.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    org_id         = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    schema_name    = Column(String(255), nullable=True)
    name           = Column(String(500), nullable=False)
    kind           = Column(String(20), nullable=False, default="table")  # table | view
    row_count_estimate = Column(BigInteger, nullable=True)
    # Read from the database's own catalog (COMMENT ON TABLE). A comment someone
    # wrote in the schema outranks anything inferred — it is documentation, not
    # a guess, so it is stored separately from `description` rather than
    # overwriting it.
    comment        = Column(Text, nullable=True)
    description        = Column(Text, nullable=True)
    description_source = Column(String(20), nullable=True)   # inferred | confirmed
    # An admin's assertion that THIS object is the source of truth for what its
    # description says it holds -- e.g. a curated summary table that already IS
    # the answer to a recurring question, so the agent should read it directly
    # rather than recomputing the same fact from the raw tables underneath it.
    # Purely advisory (agent/nodes/generate.py's prompt), never enforced by V3.
    is_canonical   = Column(Boolean, nullable=False, default=False, server_default="0")
    is_deprecated  = Column(Boolean, nullable=False, default=False, server_default="0")
    last_profiled_at = Column(DateTime(timezone=True), nullable=True)
    # When sampling this object last hit its statement-timeout deadline.
    # Remembered rather than merely counted: a view too expensive to sample
    # today is still too expensive tomorrow, and on the measured source the
    # SAME eight views timed out on every run -- 160 seconds of deterministically
    # repeated failure against the customer's database, every sync. Non-null
    # means "skip on the next sync"; a human clears it from the review page once
    # the view has been fixed. stage_discover deletes objects that vanish
    # upstream, so a view dropped and recreated gets a fresh row and a clean
    # slate for free.
    sample_timed_out_at = Column(DateTime(timezone=True), nullable=True)
    created_at     = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("data_source_id", "schema_name", "name",
                                       name="uq_source_object"),)

    columns = relationship("SourceColumn", back_populates="object",
                           cascade="all, delete-orphan")


class SourceColumn(Base):
    """One column of a source object, as the database itself declares it."""
    __tablename__ = "source_columns"
    id               = Column(Integer, primary_key=True)
    source_object_id = Column(Integer, ForeignKey("source_objects.id", ondelete="CASCADE"),
                              nullable=False, index=True)
    name             = Column(String(500), nullable=False)
    position         = Column(Integer, nullable=False, default=0)
    # Both kept: the native type is what the database said (numeric(10,2)), the
    # normalized one is what this platform reasons about. Collapsing them would
    # lose the precision information that decides whether a column is money.
    native_type      = Column(String(255), nullable=True)
    dtype            = Column(String(50), nullable=True)
    nullable         = Column(Boolean, nullable=False, default=True)
    is_primary_key   = Column(Boolean, nullable=False, default=False, server_default="0")
    comment          = Column(Text, nullable=True)          # COMMENT ON COLUMN
    semantic_type    = Column(String(40), nullable=True)
    description        = Column(Text, nullable=True)
    description_source = Column(String(20), nullable=True)
    # {raw value (stringified): label} -- what a coded/enumerated value MEANS,
    # e.g. {"1": "new", "2": "paid", "3": "cancelled"} for a status column.
    # `enum_labels_source` mirrors description_source's ladder: a human edit
    # sets 'confirmed' and is never overwritten by a later sync; the describe
    # stage's draft pass sets 'inferred' and skips any column already confirmed.
    enum_labels        = Column(JSON, nullable=True)
    enum_labels_source = Column(String(20), nullable=True)
    # How strongly this column is an OUTCOME worth explaining -- higher first,
    # NULL means "not a target". What lets `key_influencers`, `decision_tree`
    # and `automated_prediction` run unattended: the alternative is a heuristic
    # over flag-shaped columns, and a heuristic cannot know that
    # `readmitted_30d` is the question this hospital cares about while
    # `is_active` is a housekeeping bit nobody has ever asked about.
    #
    # Here rather than on the dataset for the same reason descriptions are:
    # a column that came from a connected table is the same outcome in every
    # dataset built from it. `datasets.column_meta` still overrides per dataset.
    target_candidate_priority = Column(Integer, nullable=True)

    __table_args__ = (UniqueConstraint("source_object_id", "name",
                                       name="uq_source_column"),)

    object = relationship("SourceObject", back_populates="columns")


class SourceRelationship(Base):
    """A join between two source objects.

    Separate from `relationships`, which joins user-created Datasets. This one
    describes the DATABASE's own shape — including foreign keys the database
    actually declares, which are facts rather than inferences and are seeded
    with source='declared'.
    """
    __tablename__ = "source_relationships"
    id             = Column(Integer, primary_key=True)
    data_source_id = Column(Integer, ForeignKey("data_sources.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    org_id         = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    from_object_id = Column(Integer, ForeignKey("source_objects.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    from_column    = Column(String(500), nullable=False)
    to_object_id   = Column(Integer, ForeignKey("source_objects.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    to_column      = Column(String(500), nullable=False)
    confidence     = Column(Float, nullable=False, default=1.0, server_default="1.0")
    source         = Column(String(20), nullable=False, default="declared",
                            server_default="declared")
    evidence       = Column(JSON, nullable=True)
    cardinality    = Column(String(20), nullable=True)
    created_at     = Column(DateTime(timezone=True), default=datetime.utcnow)
class Conversation(Base):
    """One chat thread in the report builder. Messages cascade with it."""
    __tablename__ = "conversations"
    id             = Column(Integer, primary_key=True)
    org_id         = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id        = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    data_source_id = Column(Integer, ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True)
    # Multi-mode amendment: a conversation targets EITHER a DataSource
    # (DirectQuery, data_source_id) OR a fixed set of Dataset ids (import /
    # multi-file). Exactly one of the two is set — enforced by the router,
    # not here, since the DB layer has no cross-column CHECK in this schema.
    dataset_ids    = Column(JSON, nullable=True)
    title          = Column(String(200), nullable=True)
    created_at     = Column(DateTime(timezone=True), default=datetime.utcnow)

    messages       = relationship("AgentMessage", cascade="all, delete-orphan")


class AgentMessage(Base):
    """`messages` in the spec — prefixed to avoid colliding with notification
    models. role: user | assistant | system."""
    __tablename__ = "agent_messages"
    id              = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role            = Column(String(20), nullable=False)
    content         = Column(Text, nullable=False)
    agent_run_id    = Column(Integer, ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)


class AgentRun(Base):
    """One question's journey through the graph. status: ok | failed |
    needs_clarification."""
    __tablename__ = "agent_runs"
    id              = Column(Integer, primary_key=True)
    org_id          = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    question        = Column(Text, nullable=False)
    status          = Column(String(30), nullable=False, default="running")
    intent          = Column(String(30), nullable=True)
    plan            = Column(JSON, nullable=True)
    answer          = Column(Text, nullable=True)
    error           = Column(Text, nullable=True)
    ms              = Column(Integer, nullable=True)
    # The retrieval-ranked object names the schema context put first for
    # this question ("tables considered") -- a debugging aid the chat shows
    # beside the SQL, so a wrong table choice is visible without a log dive.
    context_objects = Column(JSON, nullable=True)
    # `{format, limit}` when the run only re-shows an earlier result ("as a
    # table", "as a bar chart") instead of querying; NULL for a data run.
    # Migration 0017 / main._migrate.
    presentation    = Column(JSON, nullable=True)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)


class AgentStep(Base):
    """Per-node evidence. Without this neither the eval gate nor a support
    conversation has anything to work from."""
    __tablename__ = "agent_steps"
    id                  = Column(Integer, primary_key=True)
    agent_run_id        = Column(Integer, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    node                = Column(String(80), nullable=False)
    status              = Column(String(30), nullable=False)
    sql                 = Column(Text, nullable=True)
    rows_returned       = Column(Integer, nullable=True)
    # A capped snapshot of a SINK step's rows, `{columns, rows, total,
    # truncated}`, so the chat can draw the result and reload it with the
    # conversation. Intermediate steps stay NULL -- their rows exist only to
    # feed a later step's SQL. `rows_returned` stays the true count.
    result_rows         = Column(JSON, nullable=True)
    validation_failures = Column(JSON, nullable=True)
    repair_attempts     = Column(Integer, nullable=False, default=0)
    ms                  = Column(Integer, nullable=True)


class AgentFeedback(Base):
    """T4: a 👍/👎 on one agent answer, from the chat pane. `run_id` is
    nullable so a rating can target the conversation generally (no single
    run to point at); when it IS set, `router.agent.submit_feedback` upserts
    on (run_id, user_id) rather than inserting a new row every time someone
    re-rates the same answer. Only the conversation's OWNER may write here
    -- enforced in the router, same as every other conversation-scoped
    write (see Conversation.user_id)."""
    __tablename__ = "agent_feedback"
    id              = Column(Integer, primary_key=True)
    org_id          = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    run_id          = Column(Integer, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True)
    rating          = Column(String(10), nullable=False)   # up | down
    comment         = Column(Text, nullable=True)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)


class EvalRun(Base):
    """T4: one row per run of the SCHEDULED eval gate (services/eval_schedule.py).
    This is a nightly in-process stand-in for a real CI gate, not CI itself --
    see that module's docstring. `detail` carries evals.run_gate's own scored
    summary + operational counts, so a regression can be diagnosed from this
    row alone without re-running anything."""
    __tablename__ = "eval_runs"
    id          = Column(Integer, primary_key=True)
    started_at  = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    accuracy    = Column(Float, nullable=True)
    passed      = Column(Boolean, nullable=True)
    detail      = Column(JSON, nullable=True)


class QueryExample(Base):
    """Verified question→SQL memory (spec: memory.py reads and writes this)."""
    __tablename__ = "query_examples"
    id             = Column(Integer, primary_key=True)
    org_id         = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    data_source_id = Column(Integer, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=True)
    # Dataset-mode scoping: sorted dataset ids joined with commas (e.g.
    # "3,17"), NULL for source-mode rows. recall/remember key on this
    # instead of data_source_id when there is no DataSource to scope to —
    # see memory.py.
    dataset_key    = Column(String(120), nullable=True)
    question       = Column(Text, nullable=False)
    sql            = Column(Text, nullable=False)
    confirmed_by   = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at     = Column(DateTime(timezone=True), default=datetime.utcnow)


class GlossaryTerm(Base):
    """A business term and its synonyms (spec L3 gap #3 — "'إجمالي المبيعات'
    and 'GMV' cannot resolve to the same metric"). Synonyms are stored as a
    JSON list so multilingual aliases (Arabic included) live alongside the
    canonical term rather than requiring a second table.

    `data_source_id` NULL means an ORG-WIDE term, visible to every source in
    the org rather than one connection's catalog — a term like "GMV" usually
    means the same thing everywhere in a company. New table, so create_all
    makes it without a migration.
    """
    __tablename__ = "glossary_terms"
    id             = Column(Integer, primary_key=True)
    org_id         = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    data_source_id = Column(Integer, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=True, index=True)
    term           = Column(String(200), nullable=False)
    definition     = Column(Text, nullable=True)
    synonyms       = Column(JSON, nullable=False, default=list)   # ["GMV", "إجمالي المبيعات"]
    maps_to_object = Column(String(255), nullable=True)
    maps_to_column = Column(String(255), nullable=True)
    created_at     = Column(DateTime(timezone=True), default=datetime.utcnow)


class QueryRun(Base):
    """T5: one row per query actually executed against real data -- the
    training signal ARCHITECTURE.md calls for layer 4 (which queries get run,
    how they're executed, whether they hit cache, how long they take).

    Run records must not become a place values live: `sql_hash` is a sha256
    hex digest of the SQL text, NEVER the SQL itself -- a widget/agent query
    can carry filter values (customer names, amounts) that don't belong in a
    long-lived telemetry table alongside org_id. New table, so create_all
    makes it without a migration.
    """
    __tablename__ = "query_runs"
    id              = Column(Integer, primary_key=True)
    org_id          = Column(Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    source_kind     = Column(String(20), nullable=False)   # directquery | import | agent
    data_source_id  = Column(Integer, ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True, index=True)
    dataset_id      = Column(Integer, ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True, index=True)
    sql_hash        = Column(String(64), nullable=True)    # sha256 hex of the SQL text -- never the SQL itself
    rows_returned   = Column(Integer, nullable=True)
    duration_ms     = Column(Integer, nullable=False)
    executor        = Column(String(20), nullable=False)   # pushdown | pandas | duckdb
    cache_hit       = Column(Boolean, nullable=False, default=False, server_default="0")
    # The SHAPE of the query, for index advice (services/index_advice.py):
    # the table, the columns its filters and its RLS rule read, the grouped
    # column. Names only -- never a value, never SQL. Null on the import path.
    source_table    = Column(String(255), nullable=True)
    filter_columns  = Column(JSON, nullable=True)
    group_column    = Column(String(255), nullable=True)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)


class ObjectRowPolicy(Base):
    """Row policy keyed to a SOURCE OBJECT, not a dataset (spec F3).

    `RowSecurityRule` above cannot bind to agent SQL: the agent queries the
    catalog with arbitrary joins, and no dataset exists for that. The
    predicate is a SQL boolean expression injected into the parsed AST by
    agent/policy.py — never concatenated, never post-filtered (spec F4).
    """
    __tablename__ = "object_row_policies"
    id               = Column(Integer, primary_key=True)
    org_id           = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    source_object_id = Column(Integer, ForeignKey("source_objects.id", ondelete="CASCADE"), nullable=False)
    role_id          = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    predicate        = Column(Text, nullable=False)
    created_at       = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__   = (UniqueConstraint("source_object_id", "role_id",
                                         name="uq_object_role_policy"),)


class AdminAudit(Base):
    """S5: append-only trail of admin-plane security mutations -- RLS/row and
    column security rules, share-link create/revoke, export policy, API keys.
    Distinct from `AuditLogEntry` (general activity log): this one exists
    specifically so an org's admins can see what changed in the security
    surface itself, on its own read-only page, following the same "an audit
    log that can be edited by the actions it audits is theatre" principle --
    nothing in this app ever updates or deletes a row here.

    `detail` is hash-safe by construction: callers pass a short human-readable
    summary (a filter expression, a dataset name, a key prefix), never a raw
    secret -- there is nothing here an admin reading the trail shouldn't see.
    """
    __tablename__ = "admin_audit"
    id         = Column(Integer, primary_key=True)
    org_id     = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id   = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_email = Column(String(255))          # denormalised: the trail must outlive the user row
    action     = Column(String(50), nullable=False)    # e.g. "row_security_rule.create"
    target     = Column(String(255))                   # what was acted on, e.g. "dataset:12"
    detail     = Column(String(500))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class RetrievalEmbedding(Base):
    """Tier 2 retrieval (spec §1B): a cached Backend-B embedding vector for
    one piece of retrievable text (an object, glossary term, query example,
    ...), keyed by a hash of the text so an unchanged document is never
    re-embedded.

    Read and written by `services/retrieval.py` (Task M2) despite its
    public API (`rank_objects`/`rank_documents`) taking no `db` argument by
    design (R2 calls it from the sync `SchemaContext.render`): that module
    owns its own module-level sync engine (`_get_persist_engine`, mirroring
    `services.query_log._get_engine`) to read/write this table without a
    request-scoped session, wrapped so any DB failure degrades to
    "embed everything" rather than blocking or breaking ranking. The
    in-process LRU (`_EMBED_CACHE`) still sits in front of this table for
    the lifetime of one worker process; this table is what survives a
    restart.
    """
    __tablename__ = "retrieval_embeddings"
    id         = Column(Integer, primary_key=True)
    kind       = Column(String(30), nullable=False)    # object | glossary | example | entity
    ref        = Column(String(500), nullable=False)   # the document's id (e.g. object name)
    text_hash  = Column(String(64), nullable=False, index=True)  # sha256 hex of the embedded text
    vector     = Column(JSON, nullable=False)           # list[float]
    model      = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("text_hash", "model", name="uq_retrieval_embedding_text_model"),)


class Entity(Base):
    """Tier 2 retrieval (spec section 5, task R3): a named BUSINESS OBJECT this
    source models -- "customer", "order" -- as distinct from a SourceObject,
    which is a raw table or view. `grain` states what one row of the entity
    IS ("One row per completed order"), the fact a model most needs to avoid
    double-counting or picking the wrong table to aggregate.

    Drafted by the sync's LLM pass (`catalog_sync.stage_entities`, same
    complete_json pattern and same never-overwrite-a-confirmation ladder as
    `SourceColumn.enum_labels`): `source` starts 'inferred' and flips to
    'confirmed' the moment a human edits or confirms it through the review
    surface, after which no later sync draft may touch the row.

    `primary_object` names the SourceObject that is this entity's main table
    (by SourceObject.name) -- advisory text, not a foreign key, since the
    named object can be renamed or dropped independently and a dangling
    reference here is far less harmful than a database-level constraint
    error mid-sync.

    Unique per (data_source_id, name) so a resync updates the same row
    instead of duplicating it every run.
    """
    __tablename__ = "entities"
    id             = Column(Integer, primary_key=True)
    org_id         = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    data_source_id = Column(Integer, ForeignKey("data_sources.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    name           = Column(String(255), nullable=False)
    business_name  = Column(String(255), nullable=True)
    grain          = Column(Text, nullable=True)
    description    = Column(Text, nullable=True)
    primary_object = Column(String(500), nullable=True)
    # inferred | confirmed -- mirrors SourceColumn.enum_labels_source exactly.
    source         = Column(String(20), nullable=False, default="inferred",
                            server_default="inferred")
    created_at     = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at     = Column(DateTime(timezone=True), default=datetime.utcnow,
                            onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("data_source_id", "name", name="uq_entity_name"),)


class WorkspaceNode(Base):
    """One node of an org's report-navigation tree: a folder, or a filed report.

    Reports are otherwise FLAT -- a Report row carries `org_id` and nothing
    positional -- so this is what turns "every report in the org" into a menu
    somebody can navigate.

    Its own table rather than a `folder_id` column on `reports`, for the reason
    OrgParent states above: `create_all` never ALTERs a live table, so a new
    column would exist on fresh installs and be missing on every database that
    already has data.

    ONE table for both kinds, not folders-and-a-join. Folders and reports share
    a single `position` sequence among their siblings, so an author can put an
    important report above a folder. Two tables would force reports to sort
    after (or before) every folder, which is not the menu anyone draws.

    PAGES ARE NOT STORED HERE. The tree renders folders -> reports -> pages, but
    ReportPage rows already exist with their own ordering; the tree endpoint
    joins them in when it serializes. Persisting page nodes would mean every
    page added in the builder leaves the menu stale until something re-syncs it.

    Deleting a node NEVER deletes a report. `parent_id` cascades, so removing a
    folder row would take its subtree with it -- the router therefore re-parents
    children to the deleted node's parent first, exactly as
    `routers/hierarchy.py::delete_node` does (its comment records the bug that
    taught it). A `report` node's removal unfiles the report; the report itself
    is untouched and reappears at root.
    """
    __tablename__ = "workspace_nodes"
    id        = Column(Integer, primary_key=True)
    org_id    = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    # Self-referential: NULL parent means a root-level node.
    parent_id = Column(Integer, ForeignKey("workspace_nodes.id", ondelete="CASCADE"),
                       nullable=True, index=True)
    node_type = Column(String(20), nullable=False, default="folder")   # folder | report
    # Folder label. A report node reads its name through the report, so this is
    # nullable -- storing a copy would drift the moment somebody renames it.
    name      = Column(String(255))
    # Unique: a report is filed in at most one place. Deleting the report drops
    # its node with it, which is why this cascade points at reports.
    report_id = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"),
                       nullable=True, unique=True, index=True)
    # Who made this node. Nullable because rows predating this column (and
    # anything the demo seeder creates) have no author -- and SET NULL rather
    # than CASCADE, because losing a folder when its creator leaves the company
    # would be the same class of bug as deleting a folder deleting its reports.
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                        nullable=True, index=True)
    position  = Column(Integer, nullable=False, default=0)
    # Folder-level publish (0014): a published FOLDER publishes every authored
    # dashboard filed anywhere under it -- "publish the whole workspace" as one
    # act instead of N. Meaningful on folders only; a report node's own
    # publication lives on the Report row.
    published = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class WorkspaceFolderRole(Base):
    """Restricts one workspace folder to specific roles.

    NO ROWS FOR A FOLDER = EVERYONE IN THE ORG SEES IT. That default is the
    whole migration story: every folder that exists today, and every folder a
    user made yesterday, keeps working. Grants RESTRICT; they are not a licence
    somebody must first be issued. The same stance `PageRoleVisibility` and
    `ReportCapability` take, and for the same reason -- a deny-by-default switch
    empties every non-admin's menu the moment it ships.

    Any rows = those roles, plus org admins, plus the folder's creator. An admin
    locked out of a folder could not administer the restriction that locked them
    out, and an author who cannot see what they filed would simply make another.

    Restriction is subtree-effective: a folder nobody may see hides everything
    beneath it, including reports, which then appear nowhere in that user's tree
    -- not under `unfiled` either. "Show me only my workspaces" means the menu
    stops mentioning the rest.

    WHAT THIS IS NOT
    ----------------
    This governs the NAVIGATION MENU, not access. `GET /reports/{id}` returns a
    report to any member of the org regardless of where it is filed, so a user
    who knows (or guesses) a report id can still open it. Report ACCESS is
    `ReportCapability`; row and column access are the RLS rules. Hiding a menu
    entry is tidiness and least-astonishment, and treating it as a security
    boundary would be a mistake -- which is why it says so here rather than
    leaving the next reader to assume.
    """
    __tablename__ = "workspace_folder_roles"
    id      = Column(Integer, primary_key=True)
    node_id = Column(Integer, ForeignKey("workspace_nodes.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"),
                     nullable=False)
    __table_args__ = (UniqueConstraint("node_id", "role_id",
                                       name="uq_workspace_folder_role"),)


class ScheduleFailure(Base):
    """One scheduled item's failure streak, and when it may be tried again.

    The scheduler used to have no memory of failure. Its docstring said a
    broken source is "retried on its schedule rather than on every tick",
    which was true only because `last_refreshed_at` advanced even on failure
    -- the failure itself was logged and forgotten. A source that has been
    unreachable for a week was tried exactly as eagerly as one that failed
    once, nothing recorded WHY, and nothing anywhere counted attempts.

    A NEW TABLE rather than four sets of columns on datasets, dataflows,
    report_schedules and data_alerts: `create_all` provisions a new table on
    every running install, while a new column on a live table needs an
    explicit ALTER (see `main.py::_migrate`). It also keeps the four
    schedulable kinds answering to one backoff rule instead of four copies.

    A row EXISTS only while something is failing. Success deletes it, so the
    healthy path carries no rows and "is anything broken?" is one small
    SELECT rather than a scan.
    """
    __tablename__ = "schedule_failures"
    __table_args__ = (UniqueConstraint("kind", "item_id",
                                       name="uq_schedule_failure_item"),)
    id       = Column(Integer, primary_key=True)
    #: dataset | dataflow | schedule | alert -- the scheduler's four categories.
    kind     = Column(String(20), nullable=False)
    item_id  = Column(Integer, nullable=False)
    #: Consecutive failures. Drives the backoff step; reset by deleting the row.
    attempts = Column(Integer, nullable=False, default=1)
    #: Before this, the scheduler skips the item. NULL means "try next tick".
    next_attempt_at = Column(DateTime(timezone=True), nullable=True, index=True)
    #: The most recent error, truncated. What an operator actually needs.
    last_error = Column(Text, nullable=True)
    first_failed_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow,
                        onupdate=datetime.utcnow)


class WorkspaceFolderGrant(Base):
    """Shares one workspace folder — live and interactive — with a person, a
    role, or a team (org unit), at a capability level.

    THE OPPOSITE INSTRUMENT to `WorkspaceFolderRole` above, deliberately a
    separate table: that one RESTRICTS the navigation menu and touches no
    access; this one OPENS access. `core.capability` resolves a grant on any
    ancestor folder into report capability, so sharing a workspace IS the
    publish act for its subtree — an unpublished draft filed under a granted
    folder opens for the grantee at the granted level, against live data,
    with the GRANTEE's own row/column security applied by the data pipeline.

    Exactly ONE of user_id | role_id | org_unit_id is set — router-enforced
    (like Conversation's dataset/source either-or) rather than a CHECK
    constraint, so the error is an explanation instead of an IntegrityError.

    `level` is 'view' or 'edit' — never 'data': dataset authoring is the
    dataset's own grant to give, not something a folder share should smuggle.
    """
    __tablename__ = "workspace_folder_grants"
    id          = Column(Integer, primary_key=True)
    org_id      = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    node_id     = Column(Integer, ForeignKey("workspace_nodes.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    user_id     = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                         nullable=True, index=True)
    role_id     = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"),
                         nullable=True)
    org_unit_id = Column(Integer, ForeignKey("org_units.id", ondelete="CASCADE"),
                         nullable=True)
    level       = Column(String(10), nullable=False, default="view")  # view | edit
    # SET NULL, not CASCADE: the share outlives the sharer — revoking a
    # departed manager's account must not silently unshare their team's work.
    created_by  = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                         nullable=True)
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Dataflows — a transformation as a FIRST-CLASS object, not a dataset's tail.
#
# A prep pipeline lives inside one dataset's `column_meta.__prep_steps__`, and a
# materialized result records its recipe in `__derived_from__`. Both are owned by
# a dataset. That is the limit this table lifts: a Dataflow owns the recipe, can
# produce SEVERAL output datasets, carries its own schedule, and -- the point --
# has its own permissions rather than inheriting whatever the reports that happen
# to use its output allow.
#
# The inheritance being replaced has a real hole. `max_dataset_capability` ends
# with "a dataset no report uses is unrestricted", so a freshly materialized
# result -- which by definition no report uses yet -- is authorable by every
# member of the org. A dataflow is exactly the object that should not work that
# way.
# ─────────────────────────────────────────────────────────────────────────────


class Dataflow(Base):
    """A named, reusable, independently scheduled transformation.

    `steps` is the recipe in the same shape `services/prep.py` already applies,
    stored verbatim so a run replays THIS, not whatever a source dataset's own
    pipeline says today. That snapshot discipline is what keeps an output stable
    when somebody edits the dataset it was built from.

    Outputs are not a table. A produced Dataset records `dataflow_id` inside its
    existing `__derived_from__` JSON, so "the outputs of this dataflow" is a
    query over data datasets already carry -- and every derived dataset that
    exists today keeps working untouched, simply with no dataflow_id, which
    reads as "not owned by a dataflow".
    """
    __tablename__ = "dataflows"
    id          = Column(Integer, primary_key=True)
    org_id      = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    name        = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    steps             = Column(JSON, nullable=False, default=list)
    source_dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="SET NULL"),
                               nullable=True)
    join_dataset_ids  = Column(JSON, nullable=False, default=list)

    # Its OWN schedule. One interval drives every output, so the set refreshes
    # together rather than each output drifting to its own cadence.
    refresh_interval_minutes = Column(Integer, nullable=True)

    # A scheduled run has nobody at the keyboard, so it resolves row-level
    # security as this user -- the same stance ReportSchedule takes with its
    # creator. Reading with no identity would be an unfiltered read.
    created_by      = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                             nullable=True)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)
    last_run_at     = Column(DateTime(timezone=True), nullable=True)
    last_run_status = Column(String(20), nullable=True)   # ok | failed | skipped
    last_run_rows   = Column(Integer, nullable=True)
    last_run_error  = Column(Text, nullable=True)


class DataflowCapability(Base):
    """Restricts AUTHORING one dataflow to specific roles.

    NO ROWS FOR A DATAFLOW = EVERY ROLE HAS FULL ('data') ACCESS, the same
    default `ReportCapability`, `PageRoleVisibility` and `WorkspaceFolderRole`
    all take, and for the same reason: a deny-by-default switch breaks every
    existing workflow the moment it ships. Grants RESTRICT; they are not a
    licence somebody must first be issued. Org admins are always 'data' -- an
    admin locked out could not administer the restriction that locked them out.

    But ONCE ANY ROW EXISTS, a role without one falls to 'view', not 'data'.
    This differs from ReportCapability, deliberately: there, a row is assigned
    per (report, role) as a restriction on that role. Here, granting one team
    'edit' is meant to say "this team owns this pipeline" -- and if unlisted
    roles kept full access, that grant would restrict nobody and mean nothing.
    The absence of ALL rows means "not governed"; the absence of YOUR row among
    others means "not you".

    Levels reuse the existing vocabulary rather than inventing a parallel one:

      view  see the dataflow and its run history
      edit  change the recipe or schedule, and run it
      data  the above, plus delete it and grant capabilities

    WHAT THIS IS NOT
    ----------------
    This governs AUTHORING THE RECIPE, not reading the data it produces. An
    output dataset is an ordinary dataset: readable by any org member, with RLS
    narrowing rows as their own identity. That is deliberate -- `DatasetShare`
    records that org-wide dataset read is the platform's model, and gating reads
    here would contradict every other read path rather than extend it. Someone
    restricted to 'view' on a dataflow still sees its output data in full.
    """
    __tablename__ = "dataflow_capabilities"
    id          = Column(Integer, primary_key=True)
    dataflow_id = Column(Integer, ForeignKey("dataflows.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    role_id     = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"),
                         nullable=False)
    level       = Column(String(10), nullable=False, default="data")
    __table_args__ = (UniqueConstraint("dataflow_id", "role_id",
                                       name="uq_dataflow_capability"),)


class AutomationRun(Base):
    """One end-to-end Power Pi automation: profile a subject, then build and
    deliver a dashboard from it without anyone clicking through the steps.

    The run row is the durable part. Everything interesting -- what happened,
    what failed, where to resume -- lives in its `AutomationStep` children, so
    this table stays a small header that a list view can scan.

    WHY `created_by` IS LOAD-BEARING, NOT BOOKKEEPING
    ------------------------------------------------
    Row security in this product is per-user: `core/rls.resolve_rls_expr`
    answers a different predicate for every role, and `resolve_denied_columns`
    a different column set. A step that ran with no identity would read the
    unfiltered frame and compose a dashboard from rows the creator may not
    see -- and it would look like a success, because nobody is watching an
    automated run. The runner therefore refuses to execute a step whose
    creator can no longer be resolved, rather than falling back to "no RLS".

    The column is nullable and `SET NULL` on delete, matching `Report.created_by`
    (a person's work outlives their account); the refusal is enforced in
    `services/automation_runner.tick`, not by the schema.

    STATUS
    ------
      pending       created, no step has run yet
      running       at least one step is ok, more remain
      needs_review  a step wants a human before the chain continues
      done          every step is ok
      failed        a step failed; NOT terminal -- the run resumes at that
                    step once its backoff elapses, which is why `tick` treats
                    `failed` as eligible
    """
    __tablename__ = "automation_runs"
    id          = Column(Integer, primary_key=True)
    org_id      = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    #: The identity every step runs as. See the class docstring.
    created_by  = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                         nullable=True, index=True)
    #: What started it -- manual | schedule | api. Free text on purpose: the
    #: set of triggers will grow and a CHECK constraint would need a migration
    #: each time.
    trigger     = Column(String(30), nullable=False, default="manual")
    #: What the run is about: dataset | connection | report. Paired with
    #: subject_id rather than a real FK because the three targets live in
    #: three tables -- the same polymorphic shape ScheduleFailure uses.
    subject_type = Column(String(30), nullable=True)
    subject_id   = Column(Integer, nullable=True)
    status      = Column(String(20), nullable=False, default="pending", index=True)
    #: Set when `compose` produces a dashboard. SET NULL so deleting the
    #: report leaves the run's history readable.
    result_report_id = Column(Integer, ForeignKey("reports.id", ondelete="SET NULL"),
                              nullable=True, index=True)
    #: The structured record of what this run produced -- TYPED, because Home
    #: filters and orders on it, and a stored sentence supports neither. The
    #: run's artifacts are deleted at done, so these columns are the only
    #: copy that survives. raw_proposals is stored whole: model output is not
    #: reproducible, and an uncaptured proposal set is gone for good.
    result_report_name = Column(String(255), nullable=True)
    proposal_path      = Column(String(20), nullable=True, index=True)   # model | insights
    widgets_accepted   = Column(Integer, nullable=True)
    widgets_rejected   = Column(Integer, nullable=True)
    rejection_reasons  = Column(JSON, nullable=True)   # [{title, widget_type, reason}]
    raw_proposals      = Column(JSON, nullable=True)
    #: Why a run stopped: the needs_review reason, or the rejection reason. Was
    #: assigned in three places and persisted in none until migration 0032.
    error              = Column(Text, nullable=True)
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    steps = relationship("AutomationStep", back_populates="run",
                         cascade="all, delete-orphan",
                         order_by="AutomationStep.order")


class AutomationStep(Base):
    """One step of one run: its result, its failure, and when to try again.

    `output_ref` IS THE RESUME MARKER, not `status`. A worker killed between
    writing the ref and committing the status would otherwise redo work it had
    already paid for -- re-profiling a large dataset, or worse, re-composing a
    report and leaving two. `tick` skips any step that already has a ref,
    whatever its status says.

    The backoff columns mirror `ScheduleFailure` exactly (`attempts`,
    `next_attempt_at`) and are driven by the same
    `refresh_scheduler.backoff_minutes` ladder, so the platform has one
    retry rule rather than two that drift.

    Unlike `ScheduleFailure`, the row is NOT deleted on success: a completed
    run's step history is the audit trail for a dashboard nobody watched being
    built. `error` is cleared on a successful retry so a recovered step does
    not keep advertising a failure that no longer applies.
    """
    __tablename__ = "automation_steps"
    __table_args__ = (UniqueConstraint("run_id", "name",
                                       name="uq_automation_step_run_name"),)
    id       = Column(Integer, primary_key=True)
    run_id   = Column(Integer, ForeignKey("automation_runs.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    #: profile | describe | scan | propose | review | compose | notify --
    #: the names in services/automation_runner.STEPS, which is the source of
    #: truth for both the list and its order.
    name     = Column(String(40), nullable=False)
    #: 1-based position in the chain. Quoted by SQLAlchemy on every dialect
    #: this runs on; `order` is a reserved word and is spelled that way here
    #: because the chain's vocabulary should read as the spec wrote it.
    order    = Column(Integer, nullable=False)
    #: pending | running | ok | failed | skipped
    status   = Column(String(20), nullable=False, default="pending", index=True)
    #: Whatever the step produced, addressed rather than embedded: an
    #: artifact URI, a row id, a cache key. Its presence means "done".
    output_ref = Column(Text, nullable=True)
    #: Truncated to 2000 chars, as record_failure does. Never NULL after a
    #: failure -- a step that failed silently is the one thing this design
    #: exists to prevent.
    error    = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True, index=True)
    started_at  = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    run = relationship("AutomationRun", back_populates="steps")
