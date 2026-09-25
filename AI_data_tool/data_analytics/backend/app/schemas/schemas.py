from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class DatasetColumnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    dtype: str
    missing_pct: float = 0
    stats: dict = {}
    # Layer 1 inference (email | phone | url | ip | iban | national_id | ...). Exposed
    # so codeless authoring surfaces (S0b's RLS builder) can pre-suggest user/owner
    # columns without a separate round trip through the review endpoints.
    semantic_type: Optional[str] = None


class CalcColumnFormat(BaseModel):
    type: str = 'none'          # none|number|integer|currency|percent|bar|badge|trend
    decimals: Optional[int] = None
    symbol: Optional[str] = None
    prefix: Optional[str] = None
    suffix: Optional[str] = None
    min: Optional[float] = None
    max: Optional[float] = None
    color: Optional[str] = None
    thresholds: Optional[list[float]] = None


class CalcColumnDef(BaseModel):
    name: str
    expression: str
    dtype: Optional[str] = None
    format: Optional[CalcColumnFormat] = None


class SuggestDashboardsRequest(BaseModel):
    """`goal` is the person's own description of their job, in their own words.

    Free text rather than a role picker: "I am an instructor who wants to spot
    students falling behind" says more than any dropdown, and it is the part of
    the prompt that makes the answer theirs rather than generic. Capped because
    it is passed to a model, not because a shorter answer is better.
    """
    goal: Optional[str] = Field(default=None, max_length=2000)
    count: int = Field(default=3, ge=1, le=5)


class CalcColumnPreviewRequest(BaseModel):
    expression: str


class MeasureDef(BaseModel):
    """A post-aggregation measure. Unlike CalcColumnDef the expression evaluates at
    the requesting widget's grouping grain, so aggregations inside it are per-group."""
    name: str
    expression: str
    default_aggregation: Optional[str] = "sum"
    format: Optional[CalcColumnFormat] = None


class CustomFunctionDef(BaseModel):
    """A named, parameterized expression template — see
    services/custom_functions.py for the safety model."""
    name: str
    params: list[str] = []
    expression: str


class CustomFunctionPreviewRequest(BaseModel):
    """Test-drives a function definition against literal sample values for
    each parameter, since there is no row context for a function in
    isolation (unlike calc-column preview, which runs against real
    sample rows)."""
    params: list[str] = []
    expression: str
    sample_values: dict[str, Any] = {}


class RefreshScheduleUpdate(BaseModel):
    interval_minutes: Optional[int] = None


class DatasetRefreshRequest(BaseModel):
    """F3: manual refresh trigger. `mode` picks full reload vs. watermark-driven
    incremental append; `cursor_column` is optional — when omitted, an already
    configured watermark column (if any) carries over."""
    mode: str = "full"                      # full | incremental
    cursor_column: Optional[str] = None
    # E05: a full load that drops a column something uses answers 409 with the
    # missing names and likely matches. `column_map` renames incoming columns
    # (new name -> the old name everything uses); `force` refreshes anyway.
    column_map: Optional[dict[str, str]] = None
    force: bool = False


class ColumnMeta(BaseModel):
    """Author overrides for one column. Every field optional — an empty object is a
    valid entry meaning "no overrides"."""
    #: What this column IS, overriding what detection guessed:
    #: 'measure' | 'category' | 'temporal' | 'geography' | 'freetext' |
    #: 'identifier'. Aliases are accepted on write and stored canonically --
    #: 'dimension'/'categorical' → category, 'timestamp'/'datetime' → temporal,
    #: 'geo' → geography, 'numeric' → measure, 'text' → freetext.
    #:
    #: `freetext` and `identifier` are the two that change what ANALYSES do:
    #: an identifier is counted rather than summed, and free text leaves the
    #: dimension pickers entirely instead of being charted as 3,000 bars.
    role: Optional[str] = None
    #: Which uploaded boundary set draws this column on a map. Only meaningful
    #: alongside role='geography'; carried here so an author classifies a column
    #: once instead of choosing the same shapes on every map built from it.
    boundary_set_id: Optional[int] = None
    aggregation: Optional[str] = None   # default aggregation when used as a measure
    hidden: Optional[bool] = None       # hide from field pickers without deleting
    label: Optional[str] = None         # display name
    #: Whether the suggestion engines may VOLUNTEER this column. Distinct from
    #: `hidden`, and the distinction is the point: hidden removes a column from
    #: the pickers and from the analysis entirely, while this leaves it fully
    #: usable by anyone who asks for it and only stops the platform offering it
    #: unprompted. An internal sequence number a person occasionally needs to
    #: filter on should be ineligible, not hidden.
    #: None means eligible -- absence is not a restriction.
    eligible_for_suggestion: Optional[bool] = None
    #: How strongly this column is an OUTCOME worth explaining. Higher first;
    #: None means "not a target". It is what lets `key_influencers`,
    #: `decision_tree` and `automated_prediction` run unattended: without it the
    #: only way to pick what to explain is a heuristic over flag columns, and a
    #: heuristic cannot know that `readmitted_30d` is the question this hospital
    #: actually cares about.
    target_candidate_priority: Optional[int] = None


class DataViewDefault(BaseModel):
    """Whether this view is the one applied to newly uploaded datasets."""
    default: bool


class ColumnMetaUpdate(BaseModel):
    """The whole map, replaced wholesale — that is what makes a bulk edit across many
    columns one request, and lets a property be cleared by omission."""
    meta: dict[str, ColumnMeta] = {}


class MeasurePreviewRequest(BaseModel):
    expression: str
    group_by: Optional[str] = None   # simulates a visual's grain; None = single scalar


class DataPreviewRequest(BaseModel):
    filters: list[dict] = []
    calculated_columns: list[Any] = []
    sort_by: Optional[str] = None
    sort_dir: str = 'asc'
    search: Optional[str] = None
    limit: int = 100
    offset: int = 0


class ColumnFormatRequest(BaseModel):
    column: str
    format: Optional[CalcColumnFormat] = None


class FilterExprUpdate(BaseModel):
    expression: Optional[str] = None


class FilterPreviewRequest(BaseModel):
    expression: str
    calculated_columns: list[Any] = []


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str] = None
    filename: Optional[str] = None
    row_count: int = 0
    col_count: int = 0
    file_size: int = 0
    created_at: datetime
    updated_at: datetime
    columns: list[DatasetColumnOut] = []
    calculated_columns: list[Any] = []
    column_formats: dict = {}
    column_meta: dict = {}
    default_filter_expr: Optional[str] = None
    data_source_id:      Optional[int] = None
    source_table:        Optional[str] = None
    source_query:        Optional[str] = None
    query_model:         Optional[dict] = None
    mode:                str = "import"
    refresh_interval_minutes: Optional[int] = None
    last_refreshed_at:        Optional[datetime] = None
    aggregate_of_dataset_id: int | None = None
    aggregate_spec: dict | None = None
    # F3: transient — set on the response of a manual refresh when the requested
    # mode fell back (e.g. incremental with no/invalid watermark column). Never
    # persisted; absent on every other read of a dataset.
    refresh_warning:          Optional[str] = None
    # SH1: transient, computed per-request from DatasetShare -- true when THIS
    # viewer has an explicit share grant (never persisted on Dataset itself).
    shared:                   bool = False
    # Transient, resolved per-request by `services/knowledge.py` from the source
    # catalog through each column's provenance. Never persisted here: the
    # descriptions live on `source_columns`, one copy shared by every dataset
    # built from the same table, and copying them onto the dataset is the drift
    # that module exists to avoid.
    #
    # Resolved ONCE per dataset read rather than per widget request -- widget
    # data is the hottest path in the application and this is metadata that
    # changes when somebody edits a description, not when somebody clicks a bar.
    #
    # {column: what it means}. Shown beside the field in the builder, so the
    # person choosing a column sees the same sentence the model does.
    column_descriptions:      dict[str, str] = {}
    # {column: {raw value: label}} -- so an axis of 1/2/3 can read new/paid/
    # cancelled. Presentation only: the raw value stays on the row, because a
    # cross-filter click sends the value back as a filter and "paid" matches no
    # stored 2.
    value_labels:             dict[str, dict[str, str]] = {}
    # What one row IS ("one row per completed order") and what the business
    # calls it. Both come from the catalog's entity, when it named one.
    grain:                    Optional[str] = None
    business_name:            Optional[str] = None
    #: {column: priority} for the columns recorded as OUTCOMES worth explaining,
    #: resolved the same way descriptions are -- this dataset's `column_meta`
    #: over the source catalog. Absent columns are not targets, which is almost
    #: all of them.
    column_targets:           dict[str, int] = {}
    #: Columns the author marked not-to-be-volunteered. Distinct from hidden:
    #: these stay fully usable, the platform just stops offering charts of them.
    ineligible_columns:       list[str] = []


class MaterializeRequest(BaseModel):
    """Save a dataset's prep pipeline result as a new dataset.

    `steps` mirrors what `prep-preview` accepts: the editor sends the CANDIDATE
    steps so the author saves exactly the result on screen, whether or not the
    pipeline has been saved. Omit it to use the dataset's saved pipeline.
    """
    name: str
    description: Optional[str] = None
    steps: Optional[list[dict]] = None


class AggregateMeasure(BaseModel):
    column: str
    agg: str
    name: str | None = None


class AggregateCreateRequest(BaseModel):
    """Create a scheduled aggregate of a DirectQuery dataset. `grain` must
    contain every column any row-level security rule on the source reads;
    the endpoint refuses otherwise and names the role and column."""
    name: str
    grain: list[str]
    measures: list[AggregateMeasure]
    refresh_interval_minutes: int | None = None


class AggregateUpdateRequest(BaseModel):
    """Edit or rebuild an aggregate. Every field is optional; an omitted field
    keeps the stored value. An empty body is a rebuild: recompile the stored
    spec against the source as it is NOW and rewrite the file."""
    grain: list[str] | None = None
    measures: list[AggregateMeasure] | None = None
    refresh_interval_minutes: int | None = None


class BatchUploadItem(BaseModel):
    """What became of one file in a multi-file upload.

    Per-file rather than one verdict for the request, because partial success is
    the normal case: one malformed CSV in a folder of ten must not discard the
    nine that parsed. `dataset` is null when `status == "error"`, and in append
    mode every successful row carries the SAME dataset -- the items list then
    reports which files were merged into it.
    """
    source_filename: str
    status: str                      # "created" | "error"
    dataset: Optional[DatasetOut] = None
    error: Optional[str] = None


class BatchUploadOut(BaseModel):
    items: list[BatchUploadItem] = []
    created: int = 0
    failed: int = 0
    mode: str = "separate"           # "separate" | "append"


class AnalysisRequest(BaseModel):
    analysis_type: str = "full"


class AssociationRulesRequest(BaseModel):
    # Categorical columns to mine; omitted/empty means "every usable
    # categorical column in the SECURED frame".
    columns: Optional[list[str]] = None


class SegmentRequest(BaseModel):
    # Numeric columns to cluster on; omitted/empty means "every usable
    # numeric column in the RLS-filtered frame".
    columns: Optional[list[str]] = None
    # Per-row cluster labels are opt-in and capped (see segment.py's
    # ROWS_RESPONSE_CAP) -- the default response carries only the per-cluster
    # centroid summary in meta, which is what the UI renders.
    include_rows: bool = False


class KeyInfluencersRequest(BaseModel):
    """Which outcome to explain, and what may explain it."""
    target: str
    # For a categorical target, the outcome of interest. Omitted means the
    # RAREST value: "what drives churn" is asked far more often than "what
    # drives staying", and a lift is only informative about the minority class.
    target_value: Optional[str] = None
    # Columns to consider; omitted means every usable column but the target.
    factors: Optional[list[str]] = None


class WidgetCreate(BaseModel):
    widget_type: str
    title: Optional[str] = None
    config: dict = {}
    layout: dict = {"x": 0, "y": 0, "w": 6, "h": 4}


class WidgetUpdate(BaseModel):
    widget_type: Optional[str] = None
    title: Optional[str] = None
    config: Optional[dict] = None
    layout: Optional[dict] = None


class WidgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    page_id: int
    widget_type: str
    title: Optional[str] = None
    config: dict = {}
    layout: dict = {}
    created_at: datetime


class PageCreate(BaseModel):
    name: str = "Page 1"
    position: int = 0
    title: Optional[str] = None
    page_type: str = "normal"
    prompt_column: Optional[str] = None
    prompt_label: Optional[str] = None
    page_size: str = "16:9"
    custom_width: Optional[int] = None
    custom_height: Optional[int] = None
    mobile_layout: Optional[dict] = None
    layout_mode: Optional[str] = "packed"
    layout_template: Optional[str] = "executive"


class PageUpdate(BaseModel):
    name: Optional[str] = None
    #: Empty string clears it, which `exclude_none` lets through while a None
    #: (the field simply not sent) leaves it untouched.
    background_url: Optional[str] = None
    position: Optional[int] = None
    title: Optional[str] = None
    page_type: Optional[str] = None
    prompt_column: Optional[str] = None
    prompt_label: Optional[str] = None
    page_size: Optional[str] = None
    custom_width: Optional[int] = None
    custom_height: Optional[int] = None
    mobile_layout: Optional[dict] = None
    layout_mode: Optional[str] = None
    layout_template: Optional[str] = None


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    report_id: int
    name: str
    title: Optional[str] = None
    page_type: str = "normal"
    prompt_column: Optional[str] = None
    prompt_label: Optional[str] = None
    position: int
    widgets: list[WidgetOut] = []
    created_at: datetime
    page_size: str = "16:9"
    custom_width: Optional[int] = None
    custom_height: Optional[int] = None
    mobile_layout: Optional[dict] = None
    background_url: Optional[str] = None
    layout_mode: Optional[str] = None
    layout_template: Optional[str] = None


class ReportCreate(BaseModel):
    name: str
    description: Optional[str] = None
    dataset_id: Optional[int] = None


class ReportUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    dataset_id: Optional[int] = None
    additional_dataset_ids: Optional[list[int]] = None
    theme: Optional[str] = None
    display_rules: Optional[list[dict]] = None


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str] = None
    dataset_id: Optional[int] = None
    additional_dataset_ids: list[int] = []
    theme: str = "default"
    display_rules: list[dict] = []
    # Bumped by every mutation to this report or anything nested under it, so a
    # client can tell that another session changed the report underneath it.
    revision: int = 0
    pages: list[PageOut] = []
    created_at: datetime
    updated_at: datetime
    # The requesting viewer's capability on this report: 'view' | 'edit' | 'data'.
    # Set by the read endpoint (not a stored column), so the client can hide what
    # the server would refuse. Defaults to 'data' (full) for backwards behaviour.
    # The LIST endpoint also populates it now (batch query) -- the default is a
    # fallback for older callers, not the list's answer.
    my_capability: str = "data"
    # Authorship (reports.created_by == the requesting user). Drives the
    # "My workspaces / Granted" grouping only -- an admin's can-do-everything
    # never makes another author's report "mine".
    is_mine: bool = False
    # The author's user id, NULL for pre-authorship rows. Exposed so a client
    # can tell "legacy, regime does not apply" (created_by null) from "someone
    # else's authored dashboard" -- an admin's publish button on a legacy row
    # would be a control the server 400s.
    created_by: Optional[int] = None
    # Direct publication flag (stored column). False on an authored dashboard
    # means DRAFT -- but the dashboard may still be effectively published
    # through a published FOLDER, which this flag does not reflect; the
    # authoritative answer for "can others see it" is my_capability on their
    # side. Unowned legacy rows carry False and ignore the regime entirely.
    published: bool = False
    # Sensitivity label (Public/Internal/Confidential/Restricted) or None. Lives in
    # its own table; the read endpoint sets it as a transient attribute, like above.
    classification: Optional[str] = None
    # Report-level filters applied to every widget. Own table, set transiently by the
    # read endpoint. Each: {id, column, op, value}.
    common_filters: list[dict] = []


class BookmarkCreate(BaseModel):
    name: str
    position: int = 0
    state: dict


class BookmarkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    report_id: int
    name: str
    position: int
    state: dict
    created_at: datetime


class HierarchyNodeCreate(BaseModel):
    parent_id: Optional[int] = None
    name: str
    node_type: str = "folder"
    column_name: Optional[str] = None
    aggregation: Optional[str] = None
    format: Optional[str] = None
    position: int = 0


class HierarchyNodeUpdate(BaseModel):
    name: Optional[str] = None
    node_type: Optional[str] = None
    column_name: Optional[str] = None
    aggregation: Optional[str] = None
    format: Optional[str] = None
    position: Optional[int] = None
    parent_id: Optional[int] = None


class HierarchyNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    dataset_id: int
    parent_id: Optional[int] = None
    name: str
    node_type: str
    column_name: Optional[str] = None
    aggregation: Optional[str] = None
    format: Optional[str] = None
    position: int
    created_at: datetime


class WidgetDataRequest(BaseModel):
    config: dict
    calculated_columns: list[Any] = []
    widget_type: str = "bar"
    # Report parameters: the report whose definitions apply, and this viewer's values.
    # Substitution happens server-side against the DECLARED types -- the client never
    # builds expressions out of parameter values.
    report_id: int | None = None
    parameters: dict[str, Any] = {}


class WidgetDataResponse(BaseModel):
    type: str
    rows: list[Any] = []
    total: int = 0
    columns: Optional[list[str]] = None
    dimension: Optional[str] = None
    measure: Optional[str] = None
    aggregation: Optional[str] = None


class DataSourceCreate(BaseModel):
    name: str
    type: str
    config: dict = {}
    custom_connector_id: Optional[int] = None

class DataSourceUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    config: Optional[dict] = None
    cache_ttl_seconds: Optional[int] = None
    custom_connector_id: Optional[int] = None

class DataSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: str
    config: dict = {}
    cache_ttl_seconds: int = 60
    created_at: datetime
    custom_connector_id: Optional[int] = None
    custom_connector_label: Optional[str] = None    # Transient, set only on the response to a CREATE: the metadata sync that
    # started for this connection, so the client can send the user straight to
    # the review page with progress already running instead of announcing a
    # connection and leaving them to find the sync themselves. None when there
    # was nothing to start.
    sync_run_id: Optional[int] = None


class CustomConnectorCreate(BaseModel):
    key: str
    label: str
    base_type: str
    base_config: dict = {}
    locked_fields: list[str] = []

class CustomConnectorUpdate(BaseModel):
    key: Optional[str] = None
    label: Optional[str] = None
    base_type: Optional[str] = None
    base_config: Optional[dict] = None
    locked_fields: Optional[list[str]] = None

class CustomConnectorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    key: str
    label: str
    base_type: str
    base_config: dict = {}
    locked_fields: list[str] = []
    created_at: datetime

class TablePreviewRequest(BaseModel):
    table: Optional[str] = None
    query: Optional[str] = None
    limit: int = 200

class ImportRequest(BaseModel):
    dataset_name: str
    table: Optional[str] = None
    query: Optional[str] = None
    mode: str = "import"
    # The visual query-builder's graph behind `query`, stored so the dataset can
    # be reopened in the builder later. None for hand-SQL/table imports and for
    # script-mode builder saves (hand-edited SQL is one-way -- never re-parsed).
    query_model: Optional[dict] = None
    # When set, this import replaces an existing builder-created dataset's data
    # and model in place (full reload) instead of creating a new dataset.
    dataset_id: Optional[int] = None


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_org_admin: bool


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    is_active: bool
    organization: OrganizationOut
    role: RoleOut
    # Platform super-admin (config allowlist), set transiently by the read endpoint so
    # the client can reveal the cross-org management surface. Not a stored column.
    is_super_admin: bool = False


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RoleCreate(BaseModel):
    name: str
    is_org_admin: bool = False


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    is_org_admin: Optional[bool] = None


class UserCreate(BaseModel):
    email: str
    password: str
    role_id: int


class UserUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    role_id: Optional[int] = None
    is_active: Optional[bool] = None


class BulkUserRow(BaseModel):
    email: str
    password: str
    # Role by NAME, resolved within the admin's org — CSV-friendly, no id lookup.
    role: str


class BulkUserCreate(BaseModel):
    users: list[BulkUserRow]


class RowSecurityRuleCreate(BaseModel):
    role_id: int
    dataset_id: int
    filter_expr: str


class RowSecurityRuleUpdate(BaseModel):
    filter_expr: str


class RowSecurityRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role_id: int
    dataset_id: int
    filter_expr: str
    auto_generated: bool = False
    created_at: datetime


class RlsAutoGenerateRequest(BaseModel):
    dataset_id: int
    # Required only to apply (a rule needs a role); proposals are role-agnostic
    # since USEREMAIL()/ORGID()/ORGNAME() expand per-viewer at query time.
    role_id: Optional[int] = None
    apply: bool = False
    # Column names to apply, restricting the full proposal set; None applies all.
    columns: Optional[list[str]] = None


class DatasetShareCreate(BaseModel):
    user_id: int


class DatasetShareOut(BaseModel):
    id: int
    user_id: int
    email: str
    created_at: datetime


class RelationshipCreate(BaseModel):
    from_dataset_id: int
    from_column: str
    to_dataset_id: int
    to_column: str


class RelationshipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    org_id: int
    from_dataset_id: int
    from_column: str
    to_dataset_id: int
    to_column: str
    created_at: datetime
    #: Provenance. The model has carried these since Layer 1 and inference fills
    #: them in, but they were not on the wire, so a caller could not tell a
    #: human-approved link from a guess. The join editor ranks its suggestions
    #: on `source` (confirmed > declared > inferred) then `confidence`, which
    #: needs both. `evidence` is deliberately NOT exposed: it is review material
    #: for SourceReview, and nothing that consumes a suggestion reads it.
    source: str = "declared"
    confidence: float = 1.0
    cardinality: Optional[str] = None


# ── Workspace tree ────────────────────────────────────────────────────────────

class WorkspaceNodeCreate(BaseModel):
    """Create a folder, or file an existing report.

    `node_type="folder"` needs a name; `node_type="report"` needs a report_id and
    ignores the name (a report node reads its label through the report, so a
    stored copy would drift on rename).
    """
    parent_id: Optional[int] = None
    node_type: str = "folder"
    name: Optional[str] = None
    report_id: Optional[int] = None
    position: int = 0


class WorkspaceNodeUpdate(BaseModel):
    """Rename, move, or reorder. `parent_id` moves the node; the router rejects a
    move that would place a node inside its own subtree. `published` (folders
    only) publishes the whole workspace: every authored dashboard in the
    subtree becomes org-viewable."""
    name: Optional[str] = None
    parent_id: Optional[int] = None
    position: Optional[int] = None
    published: Optional[bool] = None


class WorkspacePageOut(BaseModel):
    """A report's page, as a leaf of the tree. Derived from ReportPage at read
    time -- never stored as a node, so adding a page in the builder cannot leave
    the menu stale."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    position: int


class WorkspaceNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    parent_id: Optional[int] = None
    node_type: str
    name: Optional[str] = None
    report_id: Optional[int] = None
    position: int
    #: Whether THIS viewer may rename/move/delete this node. Computed server-
    #: side so the UI does not re-implement the ownership rule -- the same
    #: stance the cycle guard takes.
    can_manage: bool = False
    #: Whether THIS viewer created it. Deliberately separate from can_manage,
    #: which is true for an admin on every node in the org and so cannot answer
    #: "is this mine?". The menu groups on this; permissions use the other.
    #: For a FOLDER this is the node's creator; for a REPORT node (filed or
    #: unfiled) it is the REPORT's author -- who filed a report into a folder
    #: says nothing about whose work it is.
    is_mine: bool = False
    #: The viewer's capability on the report ('view'|'edit'|'data'); only
    #: meaningful on report nodes. Lets the menu mark a granted report as
    #: view-only without a per-report fetch. Nodes resolving to 'none' are
    #: never serialized at all.
    my_capability: str = "data"
    #: Folder-level publish: this folder publishes its whole subtree's
    #: authored dashboards. Meaningful on folders only.
    published: bool = False
    #: Roles this folder is restricted to. Empty means everyone in the org sees
    #: it; only sent to viewers who may manage the node.
    role_ids: list[int] = []
    #: Workspace sharing: true when a WorkspaceFolderGrant on this node or an
    #: ancestor reaches THIS viewer and the node is not their own. The menu
    #: groups granted roots under "Shared with me" on it; a granted folder
    #: deeper inside a visible tree wears it as a badge instead.
    shared_with_me: bool = False
    #: Present only on report nodes, and only when the report has pages.
    pages: list[WorkspacePageOut] = []
    children: list["WorkspaceNodeOut"] = []


class WorkspaceGrantIn(BaseModel):
    """One share row: exactly ONE of user_email/user_id, role_id, org_unit_id.

    Members are addressed by EMAIL, not picked from a user list: a non-admin
    folder author may share, and handing every member a browsable directory
    of the org just for that would leak more than it helps. The router
    resolves the email inside the caller's org and refuses unknowns.
    """
    user_id: Optional[int] = None
    user_email: Optional[str] = None
    role_id: Optional[int] = None
    org_unit_id: Optional[int] = None
    level: str = "view"          # view | edit — never 'data' via a folder


class WorkspaceGrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    level: str
    user_id: Optional[int] = None
    #: Resolved server-side so the share dialog can render names without
    #: admin-only lookups.
    user_email: Optional[str] = None
    role_id: Optional[int] = None
    role_name: Optional[str] = None
    org_unit_id: Optional[int] = None
    org_unit_name: Optional[str] = None


class WorkspaceTreeOut(BaseModel):
    """The whole org tree in one response.

    `unfiled` carries reports with no node. Every report in the org must be
    reachable from the menu -- the tree is navigation, not an optional tag, and
    a report that exists but cannot be found is worse than a flat list.
    """
    roots: list[WorkspaceNodeOut] = []
    unfiled: list[WorkspaceNodeOut] = []


# ── Inferential statistics (routers/analysis.py) ─────────────────────────
class CompareGroupsRequest(BaseModel):
    value_col: str
    group_col: str


class IndependenceRequest(BaseModel):
    col_a: str
    col_b: str


class CorrelationTestRequest(BaseModel):
    col_a: str
    col_b: str
    method: str = "pearson"


class RegressionRequest(BaseModel):
    target: str
    predictors: list[str]


class GlmLogisticRequest(BaseModel):
    target: str
    predictors: list[str]
    target_value: str | None = None


class MixedModelRequest(BaseModel):
    target: str
    predictors: list[str]
    group_col: str


class SurvivalRequest(BaseModel):
    duration_col: str
    event_col: str
    predictors: list[str]


class PairwiseRequest(BaseModel):
    value_col: str
    group_col: str
    method: str = "holm"
