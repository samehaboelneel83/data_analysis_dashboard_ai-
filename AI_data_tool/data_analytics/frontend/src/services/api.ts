import axios from 'axios'
import { sanitizeErrorDetail } from '../lib/friendlyError'
import { canceledRequest } from '../lib/canceledRequest'
import type { Report, ReportRelease, ReportPage, Widget, HierarchyNode, Bookmark, BookmarkState, WorkspaceTree, WorkspaceNode } from '../types/report'
import type { DisplayRule } from '../lib/displayRules'
import type { SaidI18n } from '../lib/readbackText'

/**
 * Where the API lives, in three cases:
 *
 *   VITE_API_URL set      use it. A split deployment (app and API on
 *                         different hosts), or the dev override below.
 *   'same-origin'         relative `/api/v1/...` in dev too; the Vite dev
 *                         server proxies it to the backend (docker compose
 *                         does this), so a browser on ANOTHER machine that
 *                         opened http://<host-ip>:3001 reaches the API instead
 *                         of calling its own localhost:8000.
 *   production, unset     SAME ORIGIN -- the bundle calls `/api/v1/...`
 *                         relative to wherever nginx served it, so one built
 *                         image runs on any hostname with no rebuild and no
 *                         CORS preflight.
 *   dev / tests, unset    the Vite dev server is on :3000/:3001 while the
 *                         backend is on :8000, so they need the absolute one.
 */
const CONFIGURED_ORIGIN = (import.meta.env.VITE_API_URL ?? '').trim()
const API_ORIGIN = CONFIGURED_ORIGIN === 'same-origin'
  ? ''
  : CONFIGURED_ORIGIN || (import.meta.env.PROD ? '' : 'http://localhost:8000')
const BASE = API_ORIGIN + '/api/v1'
// T6: the session is an httpOnly cookie the server sets at login -- no script
// can read it, which is the point. `withCredentials` sends it (dev is
// cross-origin: :3000 -> :8000); X-Requested-With is the CSRF proof the server
// demands on a cookie-authenticated write, which a cross-site form cannot add.
export const api = axios.create({
  baseURL: BASE, withCredentials: true,
  headers: { 'X-Requested-With': 'XMLHttpRequest' },
})

/** The API's origin as an ABSOLUTE url, for the few places a human copies one
 *  out of the UI (the SSO callback and SAML ACS urls an admin pastes into
 *  their identity provider). Same-origin resolves to the browser's own
 *  address -- a relative path would be useless in an IdP's config field. */
export function apiOrigin(): string {
  return API_ORIGIN || (typeof window !== 'undefined' ? window.location.origin : '')
}

/** Where builds before T6 kept the login JWT -- readable by any script on the
 *  page. Read once, only to move that session into the cookie, then deleted. */
const LEGACY_TOKEN_KEY = 'datalytics_token'
let onUnauthorized: (() => void) | null = null

/** Returns and forgets a token an older build left in localStorage. */
export function takeLegacyToken(): string | null {
  try {
    const token = localStorage.getItem(LEGACY_TOKEN_KEY)
    localStorage.removeItem(LEGACY_TOKEN_KEY)
    return token
  } catch { return null }
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler
}

export function handleResponseError(error: any) {
  // Driver exceptions become sentences before any page toasts them.
  sanitizeErrorDetail(error)
  // `quiet401`: the start-up "am I logged in?" check. Every visitor makes it
  // now -- the session is a cookie script cannot see -- and a 401 there just
  // means "not logged in"; redirecting would bounce a share-link or embed
  // viewer to the login page.
  if (error?.response?.status === 401 && !error?.config?.quiet401) {
    onUnauthorized?.()
  }
  return Promise.reject(error)
}

api.interceptors.response.use(r => r, handleResponseError)

/** The person's LLM pick from the top bar (an endpoint id, or 'auto'). Kept in
 *  this browser and sent with every request as X-LLM-Endpoint, which the
 *  server's middleware hands to every AI call. Nothing stored = the platform
 *  default. */
export const LLM_CHOICE_KEY = 'datalytics.llmEndpoint'
export const LLM_CHOICE_EVENT = 'datalytics:llm-choice'
let memoryLlmChoice: string | null = null
export function getLlmChoice(): string | null {
  try { return localStorage.getItem(LLM_CHOICE_KEY) ?? memoryLlmChoice } catch { return memoryLlmChoice }
}
export function setLlmChoice(choice: string | null): void {
  try {
    if (choice) localStorage.setItem(LLM_CHOICE_KEY, choice)
    else localStorage.removeItem(LLM_CHOICE_KEY)
  } catch { /* private window: the pick lasts this page only */ }
  memoryLlmChoice = choice
  window.dispatchEvent(new CustomEvent(LLM_CHOICE_EVENT, { detail: choice }))
}
api.interceptors.request.use(config => {
  const choice = getLlmChoice()
  if (choice) config.headers.set('X-LLM-Endpoint', choice)
  return config
})

/** Which models answered a request: the server lists them in X-LLM-Used as
 *  `id=weight` pairs, in call order. The top bar listens for this event to
 *  show the model Auto really used, step by step. */
export const LLM_USED_EVENT = 'datalytics:llm-used'
export interface LlmUsedStep { id: string; weight: string }
export function parseLlmUsed(header: unknown): LlmUsedStep[] {
  if (typeof header !== 'string' || !header.trim()) return []
  return header.split(',').map(part => {
    const [id, weight] = part.trim().split('=')
    return { id: id ?? '', weight: weight ?? 'normal' }
  }).filter(u => u.id)
}
function announceLlmUsed(headers: unknown) {
  const raw = (headers as { get?: (k: string) => unknown; [k: string]: unknown } | undefined)
  const value = typeof raw?.get === 'function' ? raw.get('x-llm-used') : raw?.['x-llm-used']
  const used = parseLlmUsed(value)
  if (used.length && typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent<LlmUsedStep[]>(LLM_USED_EVENT, { detail: used }))
  }
}
api.interceptors.response.use(r => { announceLlmUsed(r.headers); return r })

export interface DatasetColumn {
  id: number
  name: string
  dtype: string
  missing_pct: number
  /**
   * ALWAYS EMPTY. Not a placeholder for data that arrives later — the column
   * rows are created with `stats={}` written literally at all three creation
   * sites (`routers/datasets.py:189`, `dataflows.py:352`, `:384`), and nothing
   * anywhere populates it. 0 of 506 columns in the dev database carry a key.
   *
   * Typed `Record<string, never>` so reading a property off it is a COMPILE
   * error rather than a silent `undefined`. Three separate features had already
   * been built on it and were dead in production while their tests passed —
   * Group & Bin's interval binning (bin edges from `stats.min/max`, so every
   * attempt answered "Pick at least two bin edges"), the widget suggester's
   * pie-vs-bar rule (`stats.unique`, so it had never once suggested a pie), and
   * a documented-as-optional path in `isIdLikeColumn`. Each test passed because
   * its fixture invented the field.
   *
   * Real per-column statistics come from the analysis profile
   * (`POST /datasets/{id}/analysis` -> `numeric.columns` / `categorical.columns`,
   * the latter carrying `n_unique`), or from a `widgetDataApi` query when a
   * single number is wanted — both of which apply row and column security, which
   * a stored blob would not.
   */
  stats: Record<string, never>
  /** Layer 1 inference (email | phone | url | ip | iban | national_id | ...), null
   *  when not yet classified. Used by the codeless RLS rule builder to pre-suggest
   *  user/owner columns. */
  semantic_type?: string | null
}

export interface CalcColumnFormat {
  type: 'none' | 'number' | 'integer' | 'currency' | 'percent' | 'bar' | 'badge' | 'trend' | 'colorscale' | 'icon'
  decimals?: number
  symbol?: string       // currency symbol e.g. '$', 'SAR', '€', 'ر.س'
  /** Where the symbol sits. Default: after an Arabic-script symbol, before any other. */
  symbol_position?: 'before' | 'after'
  prefix?: string
  suffix?: string
  min?: number          // bar / colorscale scale min
  max?: number          // bar / colorscale scale max
  color?: string        // bar fill color
  thresholds?: [number, number]  // [low, high] for badge/icon coloring
  scaleMinColor?: string  // colorscale low-end color
  scaleMidColor?: string  // colorscale mid-point color
  scaleMaxColor?: string  // colorscale high-end color
  /** Display units. Divides the value so an axis reads "1.2" rather than
   *  "1,200,000", the way a SAS axis titled "Profit (millions)" does.
   *  'auto' picks the unit from the size of each number. */
  scale?: 'none' | 'auto' | 'thousands' | 'millions' | 'billions'
  /** Whether the unit is named ON the value (`1.2M`). Default true: a tooltip,
   *  a data label and a table cell all carry the number away from the axis that
   *  titled the unit, and a bare "1.2" there is a wrong number rather than a
   *  compact one. Turn it off to reproduce SAS exactly, naming the unit in the
   *  axis title instead. */
  scale_suffix?: boolean
}

export interface CalcColumn {
  name: string
  expression: string
  dtype?: string
  format?: CalcColumnFormat
}

export interface CustomFunction {
  name: string
  params: string[]
  expression: string
}

export interface DatasetCatalog {
  kind: 'upload' | 'connection' | 'live' | 'derived' | 'aggregate'
  freshness: 'live' | 'on_schedule' | 'due' | 'overdue' | 'manual' | 'fixed'
  as_of: string | null
  next_due: string | null
  refresh_every_minutes: number | null
  source?: string
  built_from?: string[]
}

export interface Dataset {
  id: number
  name: string
  /** 4.7: who made it -- the "Mine" filter on dataset pickers. */
  created_by?: number | null
  description?: string
  filename?: string
  row_count: number
  col_count: number
  file_size: number
  created_at: string
  updated_at: string
  columns: DatasetColumn[]
  calculated_columns: CalcColumn[]
  measures: MeasureDef[]
  column_meta: Record<string, ColumnMeta>
  column_formats: Record<string, CalcColumnFormat>
  default_filter_expr?: string | null
  data_source_id?:     number | null
  source_table?:       string | null
  source_query?:       string | null
  query_model?:        Record<string, unknown> | null
  mode:                'import' | 'directquery'
  refresh_interval_minutes?: number | null
  last_refreshed_at?:        string | null
  // F3: transient -- present only on the response of a manual refresh whose
  // requested mode fell back (e.g. incremental with no usable watermark column).
  refresh_warning?:          string | null
  // E07: transient -- on an upload's response only: a dataset the uploader
  // can read that already holds the same bytes. Advisory; the upload happened.
  duplicate_of?:             { id: number; name: string } | null
  // SH1: transient, computed per-viewer -- true when the CURRENT user has an
  // explicit share grant on this dataset (never true for org-wide default read).
  shared?:                   boolean
  /** E06: on the list only -- what the dataset is and how current. */
  catalog?:                  DatasetCatalog | null
  /** Transient, resolved per read from the SOURCE catalog through each column's
   *  provenance -- never stored on the dataset, so describing a column once
   *  improves every dataset built from the same table.
   *  {column: what it means}. Present only on a single-dataset read; the list
   *  leaves it empty so a shelf of datasets stays cheap to draw. */
  column_descriptions?:      Record<string, string>
  /** {column: {raw value: label}} -- what a coded value MEANS, so an axis can
   *  read new/paid/cancelled instead of 1/2/3. PRESENTATION ONLY: the raw value
   *  stays on every row, because a cross-filter click sends it back as a filter
   *  and "paid" matches no stored 2. */
  value_labels?:             Record<string, Record<string, string>>
  /** What one row IS ("one row per completed order"), and what the business
   *  calls it. From the catalog's entity, when it named one. */
  grain?:                    string | null
  business_name?:            string | null
  /** {column: priority} for columns recorded as outcomes worth explaining,
   *  resolved like descriptions — this dataset's override over the catalog. */
  column_targets?:           Record<string, number>
  /** Columns the author marked not-to-be-volunteered. */
  ineligible_columns?:       string[]
  // Aggregate datasets: set when this dataset IS a saved GROUP BY of another.
  aggregate_of_dataset_id?:  number | null
  aggregate_spec?:           AggregateSpec | null
}

export interface DemoSeedResult { datasets: number; reports: number; widgets: number }

export interface OrgTheme { id: number; name: string; colors: string[] }

export const themesApi = {
  list:   () => api.get<OrgTheme[]>('/reports/themes/custom').then(r => r.data),
  create: (name: string, colors: string[]) =>
    api.post<OrgTheme>('/reports/themes/custom', { name, colors }).then(r => r.data),
  delete: (id: number) => api.delete(`/reports/themes/custom/${id}`),
}

export const columnsApi = {
  duplicate: (datasetId: number, column: string) =>
    api.post<{ name: string; expression: string }>(
      `/datasets/${datasetId}/columns/${encodeURIComponent(column)}/duplicate`).then(r => r.data),
}

export const demoApi = {
  seed:   () => api.post<DemoSeedResult>('/demo/seed').then(r => r.data),
  unseed: () => api.delete<{ datasets: number; reports: number; data_sources: number }>('/demo/seed').then(r => r.data),
}

/**
 * A dataflow is a transformation that owns itself: its own recipe, its own
 * schedule, and its own permissions rather than whatever the reports using its
 * output happen to allow.
 *
 * `your_capability` comes back on every read so the UI can hide controls the
 * server would only refuse -- showing a button that always 403s is worse than
 * showing nothing.
 */
export interface DataflowOutput {
  id: number
  name: string
  row_count?: number | null
  last_refreshed_at?: string | null
}

export interface Dataflow {
  id: number
  name: string
  description?: string | null
  source_dataset_id: number | null
  join_dataset_ids: number[]
  steps: Record<string, unknown>[]
  refresh_interval_minutes: number | null
  /** Pipeline phase 4: runs when its source dataset refreshes, not on a timer. */
  run_after_source?: boolean
  /** 4.6: a snapshot dataflow appends a row per period (and group). */
  snapshot?: DataflowSnapshot | null
  created_by: number | null
  created_at: string | null
  last_run_at: string | null
  last_run_status: string | null
  last_run_rows: number | null
  last_run_error: string | null
  outputs: DataflowOutput[]
  your_capability: 'view' | 'edit' | 'data' | null
}

export interface DataflowGrant { role_id: number; level: string }

export interface DataflowSnapshot {
  every: 'month' | 'week' | 'day'
  group_by?: string[]
  measure?: string | null
  agg?: 'count' | 'nunique' | 'sum' | 'avg'
  as?: string
  backfill?: { from_column: string; to_column: string; start: string } | null
}

export const dataflowsApi = {
  list:   ()           => api.get<Dataflow[]>('/dataflows').then(r => r.data),
  get:    (id: number) => api.get<Dataflow>(`/dataflows/${id}`).then(r => r.data),
  create: (body: { name: string; source_dataset_id: number; description?: string
                   steps?: Record<string, unknown>[]
                   refresh_interval_minutes?: number | null
                   snapshot?: DataflowSnapshot | null }) =>
    api.post<Dataflow>('/dataflows', body).then(r => r.data),
  update: (id: number, body: Partial<{ name: string; description: string
                                       steps: Record<string, unknown>[]
                                       refresh_interval_minutes: number | null
                                       /** Phase 4: run when the source dataset refreshes. */
                                       run_after_source: boolean }>) =>
    api.put<Dataflow>(`/dataflows/${id}`, body).then(r => r.data),
  remove: (id: number) => api.delete(`/dataflows/${id}`),
  run:    (id: number, output_name?: string) =>
    api.post<{ rows: number; outputs: DataflowOutput[] }>(
      `/dataflows/${id}/run`, output_name ? { output_name } : {}).then(r => r.data),
  capabilities: (id: number) =>
    api.get<{ grants: DataflowGrant[]; your_capability: string }>(
      `/dataflows/${id}/capabilities`).then(r => r.data),
  setCapabilities: (id: number, grants: DataflowGrant[]) =>
    api.put<{ grants: DataflowGrant[] }>(`/dataflows/${id}/capabilities`,
                                         { grants }).then(r => r.data),
}

export interface ProfiledColumn {
  name: string
  role: string
  distinct: number
  missing_pct: number
  is_identifier: boolean
  is_personal: boolean
  top_values: { value: string; count: number }[]
  min: number | string | null
  max: number | string | null
}

/** What the server understood about a dataset before proposing anything. Shown
 *  to the person, because a suggestion you cannot check is one you cannot trust. */
export interface DatasetProfile {
  row_count: number
  columns: ProfiledColumn[]
  other_columns: { name: string; role: string }[]
  structure: {
    coordinate_pairs: string[][]
    parent_child: string[][]
    hierarchies: string[][]
    date_range: { column: string; from: string; to: string; days: number
                  granularity: string } | null
  }
}

export interface SuggestedWidget {
  widget_type: string
  title: string
  why?: string
  /** What the widget actually drew, read from its result (services/readback.py). */
  takeaway?: string
  /** The same sentence as a key and its pieces, for the reader's language. */
  takeaway_i18n?: SaidI18n | null
  config: Record<string, unknown>
  /** How many rows it returned when the server ran it. Every widget offered has
   *  been executed; this is the evidence. */
  row_count: number
  /** Panel mode: the question it answers, the proposer's 1-5 value, and how
   *  strongly the drawn result shows something (0-1). */
  question?: string
  value?: number
  evidence?: number
  /** Panel mode: its place on the section's page, decided on the server. */
  layout?: { x: number; y: number; w: number; h: number }
  /** Panel mode: double-clicking a value opens the drill-through page. */
  drill_to?: 'drill'
}

/** Which widgets can filter which others, and on what column. Indices into the
 *  proposal's own `widgets`; the real widget ids do not exist until the
 *  dashboard is built. */
export interface WidgetRelation {
  from: number
  to: number
  via: string
  mode: 'filter' | 'highlight'
  note: string
}

export interface DashboardSuggestion {
  title: string
  rationale: string
  widgets: SuggestedWidget[]
  relations?: WidgetRelation[]
  /** `insights` when the statistics engine chose these charts and no model was
   *  involved; `model` when the person's own words were tailored to. */
  source?: 'insights' | 'model' | 'panel'
  /** Panel mode: which lens section this proposal is. */
  section?: string
  /** Panel mode: a drill-through page, filtered to the value clicked
   *  elsewhere (`prompt_column`). */
  page_type?: 'drillthrough'
  prompt_column?: string
  prompt_label?: string
}

/** What the analyst panel did: how many ideas each source gave, how many drew,
 *  how many were merged as the same question, how many were kept. */
export interface PanelStats {
  lenses: string[]
  candidates: number
  from_model: number
  from_statistics: number
  drawn: number
  rejected: number
  duplicates_merged: number
  selected: number
  size: number
  /** Refused ideas by kind (units, promise, identifier, axis, empty, error, invalid). */
  left_out?: Record<string, number>
  /** Drew fine but lost to stronger ideas for the space. */
  not_picked?: number
}

/** One idea the panel left out, and why (the reason is the server's English). */
export interface PanelRefusal {
  title: string | null
  widget_type: string | null
  why: string | null
  code?: string
  source?: string
}

/** What "suggest dashboards" answers. A panel asked for in the background
 *  answers with `job_id` only; the same shape then arrives as the job's
 *  `result`. */
export interface SuggestDashboardsAnswer {
  proposals: DashboardSuggestion[]
  reason: string
  profile: DatasetProfile
  source?: 'insights' | 'model' | 'panel'
  panel?: PanelStats
  facts?: string[]
  refused?: PanelRefusal[]
  /** One short question asked back when nothing could be designed.
   *  A reason is a dead end; a question is a next step. Null when
   *  the model is unavailable or declines -- an invented question
   *  would be worse than the plain refusal it replaced. */
  question?: string | null
  job_id?: number
  state?: string
  /** Fields the proposals draw that the dataset does not have yet -- a rate
   *  of totals, a duration (services/derived_fields.py). Created on the
   *  dataset when the person creates the dashboard, not before. */
  derived?: { measures: MeasureDef[]; calculated_columns: CalcColumn[] }
}

export interface LiveCount { row_count: number | null; counted_at: string | null; live: boolean; error?: string }

export const datasetsApi = {
  /** 4.5: a live dataset's cached row count, recounted when over an hour old. */
  /** 4.7: mark (or unmark) the dataset to use. Admin only. */
  certify: (id: number, certified = true, note?: string) =>
    api.post<{ certified: boolean }>(`/datasets/${id}/certify`, { certified, note }).then(r => r.data),
  liveCount: (id: number, force = false) =>
    api.post<LiveCount>(`/datasets/${id}/live-count`, null, { params: force ? { force: true } : {} }).then(r => r.data),
  list:    ()         => api.get<Dataset[]>('/datasets').then(r => r.data),
  /** Ask the model what dashboards would suit this dataset and this person.
   *  `goal` is their own description of their job, free text. Slow by nature —
   *  it profiles the data, asks a model, then runs every widget it proposes. */
  /** Describe a column. Writes to the SOURCE catalog when the column came from
   *  one, so the sentence is written once and read by every dataset built from
   *  that table -- the reason descriptions are resolved rather than copied. */
  setColumnDescription: (id: number, column: string, description: string) =>
    api.patch<ColumnDescriptionResult>(
      `/datasets/${id}/columns/${encodeURIComponent(column)}/description`,
      { description }).then(r => r.data),
  /** `mode: 'panel'` asks several analyst lenses, draws every idea and keeps
   *  the `size` best by what the data shows: minutes rather than seconds, so
   *  its timeout is longer. */
  suggestDashboards: (id: number, body: { goal?: string; count?: number; mode?: 'quick' | 'panel'; size?: number;
                                          background?: boolean; fresh?: boolean },
                      signal?: AbortSignal) =>
    api.post<SuggestDashboardsAnswer>(
      `/datasets/${id}/suggest-dashboards`, body,
      { timeout: body.mode === 'panel' && !body.background ? 600000 : 300000, signal }).then(r => r.data),
  get:     (id: number) => api.get<Dataset>(`/datasets/${id}`).then(r => r.data),
  delete:  (id: number) => api.delete(`/datasets/${id}`),
  // E05: a full refresh that drops a column in use answers 409 `schema_break`
  // (see SchemaBreakDialog); resend with column_map (new -> old) or force.
  refresh: (id: number, body?: { mode?: 'full' | 'incremental'; cursor_column?: string | null;
                                 column_map?: Record<string, string>; force?: boolean }) =>
    api.post<Dataset>(`/datasets/${id}/refresh`, body ?? { mode: 'full' }).then(r => r.data),
  /** Queue the same refresh as a durable job (E12) and return at once; follow
   *  it with `jobsApi.get`. A schema break fails the job with error_code
   *  `schema_break` and the mapping details as its `result`. If one is already
   *  queued or running for this dataset, its owner gets that job back. */
  queueRefresh: (id: number, body: { mode?: 'full' | 'incremental'; cursor_column?: string | null;
                                     column_map?: Record<string, string>; force?: boolean
                                     /** Phase 3: publish although a blocking data check failed. */
                                     publish_anyway?: boolean },
                 idempotencyKey?: string) =>
    api.post<Job>(`/datasets/${id}/refresh-jobs`, body,
      idempotencyKey ? { headers: { 'Idempotency-Key': idempotencyKey } } : undefined).then(r => r.data),
  /** The refresh of this dataset queued or running now: the job (yours, or
   *  any as an admin), `{state, by_someone_else}` for a colleague's, or null. */
  activeRefresh: (id: number) =>
    api.get<Job | { state: JobState; by_someone_else: true } | null>(
      `/datasets/${id}/refresh-jobs/active`).then(r => r.data),
  /** The data-quality report over the rows this viewer's charts use; `rules`
   *  are expressions a good row satisfies ("amount >= 0"). */
  quality: (id: number, rules: string[] = []) =>
    api.post<QualityReport>(`/datasets/${id}/quality`, { rules }).then(r => r.data),
  /** One dataset from tables in several database connections: each is
   *  imported, then appended (how='append') or joined on `on`. Admin only. */
  combine: (body: { name: string; how: string; on?: string[];
                    sources: { data_source_id: number; table: string; label?: string }[] }) =>
    api.post<Dataset>('/datasets/combine', body).then(r => r.data),
  /** Phase 3: the dataset's saved quality checks. */
  checks: (id: number) => api.get<DataCheck[]>(`/datasets/${id}/checks`).then(r => r.data),
  addCheck: (id: number, body: DataCheckInput) =>
    api.post<DataCheck>(`/datasets/${id}/checks`, body).then(r => r.data),
  updateCheck: (id: number, checkId: number, body: DataCheckInput) =>
    api.patch<DataCheck>(`/datasets/${id}/checks/${checkId}`, body).then(r => r.data),
  deleteCheck: (id: number, checkId: number) => api.delete(`/datasets/${id}/checks/${checkId}`),
  /** Every saved check on the data the dataset holds now. */
  tryChecks: (id: number) =>
    api.post<{ rows: number; results: CheckResult[] }>(`/datasets/${id}/checks/try`).then(r => r.data),
  /** This dataset's recent refreshes with their check results (editors). */
  refreshRuns: (id: number, limit = 30) =>
    api.get<DatasetRefreshRun[]>(`/datasets/${id}/refresh-runs`, { params: { limit } }).then(r => r.data),
  /** Pipeline phase 2: is this dataset's refresh working, and its freshness target. */
  pipelineHealth: (id: number) =>
    api.get<PipelineHealth>(`/datasets/${id}/pipeline-health`).then(r => r.data),
  /** Freshness target (hours, or null for none) and extra alert recipients. */
  setPipelineWatch: (id: number, body: { freshness_hours?: number | null; recipients?: string[] }) =>
    api.patch<PipelineHealth>(`/datasets/${id}/pipeline-watch`, body).then(r => r.data),
  /** Set the automatic refresh interval, or null to clear it. Minimum 5 minutes;
   *  the server refuses DirectQuery (nothing is cached to refresh). */
  setSchedule: (id: number, interval_minutes: number | null) =>
    api.patch<Dataset>(`/datasets/${id}/refresh-schedule`,
                       { interval_minutes }).then(r => r.data),
  /** Phase 4: a dataset rebuilt from another runs when that source refreshes. */
  setAfterSource: (id: number, after_source: boolean) =>
    api.patch<Dataset>(`/datasets/${id}/refresh-schedule`, { after_source }).then(r => r.data),
  /** Phase 4: how scheduled refreshes load this dataset. */
  incremental: (id: number) =>
    api.get<IncrementalSettings>(`/datasets/${id}/incremental`).then(r => r.data),
  setIncremental: (id: number, body: IncrementalSettingsInput) =>
    api.put<IncrementalSettings>(`/datasets/${id}/incremental`, body).then(r => r.data),
  // `sheet`: which sheet of a workbook becomes the dataset (E07). Needed only
  // when the server refused a workbook with data on several sheets.
  upload: (file: File, name: string, desc = '', sheet?: string) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('name', name)
    fd.append('description', desc)
    if (sheet) fd.append('sheet', sheet)
    return api.post<Dataset>('/datasets', fd).then(r => r.data)
  },
  // Separate endpoint rather than a wider `upload`: the server cannot have one
  // parameter be both a single file and a list, and every existing caller of
  // upload() depends on getting exactly one Dataset back.
  uploadBatch: (files: File[], name: string, desc = '',
                mode: BatchUploadMode = 'separate') => {
    const fd = new FormData()
    // Repeated key, which is what FastAPI reads as list[UploadFile].
    files.forEach(f => fd.append('files', f))
    fd.append('name', name)
    fd.append('description', desc)
    fd.append('mode', mode)
    return api.post<BatchUploadResult>('/datasets/batch', fd).then(r => r.data)
  },
}

export type BatchUploadMode = 'separate' | 'append'

export interface BatchUploadItem {
  source_filename: string
  status: 'created' | 'error'
  dataset: Dataset | null
  /** Why this file was rejected; null when it succeeded. */
  error: string | null
}

export interface BatchUploadResult {
  items: BatchUploadItem[]
  created: number
  failed: number
  mode: BatchUploadMode
}

export interface DatasetShare {
  id: number
  /** Who the share is for. Older servers send only user shares. */
  kind?: 'user' | 'role' | 'org_unit'
  user_id?: number | null
  email?: string | null
  role_id?: number | null
  org_unit_id?: number | null
  /** The grantee's display name: an email, a role or an org unit. */
  name?: string | null
  /** 'view' reads only; 'edit' may also re-model the data. */
  level?: 'view' | 'edit'
  created_at: string
}

/** SH1: dataset sharing is org-admin-managed (a dataset has no owner concept) --
 *  mirrors the report guest-link shape, but grants an in-org user, not a token. */
export const datasetSharesApi = {
  list:   (datasetId: number) => api.get<DatasetShare[]>(`/datasets/${datasetId}/shares`).then(r => r.data),
  create: (datasetId: number, userId: number, level: 'view' | 'edit' = 'view') =>
    api.post<DatasetShare>(`/datasets/${datasetId}/shares`, { user_id: userId, level }).then(r => r.data),
  /** Share with a whole role, or an org unit and everyone placed under it. */
  createGroup: (datasetId: number, body: { role_id?: number; org_unit_id?: number; level: 'view' | 'edit' }) =>
    api.post<DatasetShare>(`/datasets/${datasetId}/shares`, body).then(r => r.data),
  delete: (datasetId: number, shareId: number) => api.delete(`/datasets/${datasetId}/shares/${shareId}`),
  deleteGroup: (datasetId: number, shareId: number) => api.delete(`/datasets/${datasetId}/group-shares/${shareId}`),
}

export interface SegmentResult {
  kind: string
  columns: { name: string; dtype: string }[]
  rows: { row_index: number; cluster: number }[]
  meta: {
    method: string
    params: { k: number; k_range: [number, number]; columns: string[]; random_state: number }
    silhouette: number
    centroids: Record<string, number | string>[]
    n_rows_used: number
    n_rows_total: number
  }
  warnings: string[]
}

/**
 * Inferential statistics: the eight registry analyses whose `result_kind` is
 * `statistical_test`.
 *
 * They shipped with working endpoints and NO frontend entry point at all — half
 * the analysis registry was reachable only by the agent, which can mention them
 * but not invoke them.
 *
 * All eight share one call shape and return one envelope, which is why a single
 * screen drives them rather than eight bespoke ones.
 */
export interface StatisticalTestResult {
  kind: string
  statistic: number | null
  p_value: number | null
  effect_size: number | null
  effect_name: string
  effect_label: 'negligible' | 'small' | 'medium' | 'large'
  significant: boolean
  alpha: number
  n: number
  detail: Record<string, unknown>
  interpretation: string
  caveats: string[]
}

export interface AnalysisSpec {
  name: string
  description: string
  params_schema: {
    type: string
    required?: string[]
    properties: Record<string, {
      type: string | string[]
      description?: string
      enum?: string[]
      items?: { type: string }
      /** `"column"` means the value is a column name in this dataset. Without
       *  it a generic form cannot tell a column reference from a number the
       *  user has to type -- goal seek's target value rendered as a column
       *  dropdown, with no way to enter a number at all. */
      format?: string
    }>
  }
  result_kind: string
  /** Whether the catalogue can actually invoke it. An entry with no handler is
   *  documented but not yet reachable generically, and offering it in a picker
   *  could only ever produce a 400. */
  runnable: boolean
}

/** What `POST /datasets/{id}/analysis/run` answers with. `result` is whatever
 *  the analysis returns, so it is typed open: the renderer chooses its view
 *  from `result_kind` rather than from the request it sent. */
export interface AnalysisRunResponse {
  analysis: string
  result_kind: string
  params: Record<string, unknown>
  result: unknown
}

/**
 * The analysis catalogue, and one way to run anything in it.
 *
 * This used to be `statisticsApi`, with a hand-written `STATISTICS_ROUTES` map
 * from registry name to URL slug, because each analysis had its own typed
 * endpoint. Those endpoints still exist and are still the better API for a
 * hand-written caller -- a wrong field is a 422 that names it. But this client
 * is not hand-written: it builds its request from `params_schema`, so the
 * typed 422 buys it nothing, and the slug map cost a frontend edit for every
 * analysis added. Eight analyses were reachable; eleven more were not.
 *
 * `run` posts to the one dispatch route, so a newly registered runnable
 * analysis appears in the UI with no frontend change at all.
 */
export const analysisCatalogueApi = {
  /** Every registered analysis, runnable or not. */
  registry: () =>
    api.get<{ analyses: AnalysisSpec[] }>('/analysis/registry').then(r => r.data.analyses),
  run: (datasetId: number, name: string, params: Record<string, unknown>) =>
    api.post<AnalysisRunResponse>(
      `/datasets/${datasetId}/analysis/run`, { name, params }).then(r => r.data),
}

/**
 * Data alerts: watch a condition on a dataset and email someone when it becomes
 * true.
 *
 * The evaluator has been running on every scheduler tick for months --
 * `refresh_scheduler.py` calls `check_alert`, which resolves RLS as the alert's
 * CREATOR (an alert has no viewer, and no viewer must never mean no RLS) and
 * fires only on the rising edge. Three endpoints served it and nothing in the
 * product called them, so the platform had alerts that nobody could create.
 */
export interface DataAlert {
  id: number
  name: string
  expression: string
  interval_minutes: number
  recipients: string[]
  /** 'firing' | 'clear' at the last check (older servers: a boolean) -- the
   *  rising edge is measured against this, so 'firing' means the email went. */
  last_state: 'firing' | 'clear' | boolean | null
  last_value?: number | null
  change_pct?: number | null
  change_direction?: 'up' | 'down' | 'any' | null
  webhook_url?: string | null
  /** "ok", or the evaluation error. Null means it has never run. */
  last_status: string | null
  last_checked_at: string | null
}

export interface DataAlertInput {
  name: string
  expression: string
  interval_minutes: number
  recipients: string[]
  /** A CHANGE alert: `expression` is a metric and it fires on this % move. */
  change_pct?: number | null
  change_direction?: 'up' | 'down' | 'any' | null
  /** Teams / Slack / generic incoming webhook (https). */
  webhook_url?: string | null
}

export interface AlertTestResult { firing: boolean; value: number | null; message: string }

export const alertsApi = {
  list: (datasetId: number) =>
    api.get<DataAlert[]>(`/datasets/${datasetId}/alerts`).then(r => r.data),
  create: (datasetId: number, body: DataAlertInput) =>
    api.post<{ id: number; name: string }>(
      `/datasets/${datasetId}/alerts`, body).then(r => r.data),
  remove: (datasetId: number, alertId: number) =>
    api.delete(`/datasets/${datasetId}/alerts/${alertId}`).then(() => undefined),
  /** Evaluate now, as the caller, without saving. */
  test: (datasetId: number, body: { expression: string; change_pct?: number | null
                                    change_direction?: string | null; alert_id?: number }) =>
    api.post<AlertTestResult>(`/datasets/${datasetId}/alerts/test`, body).then(r => r.data),
}

/**
 * Customer-supplied map boundaries: governorates, states, districts.
 *
 * The bundled atlas is countries only, and admin-1 for every country is tens of
 * megabytes, so sub-national geometry cannot ship with the app. An org uploads
 * the file it already has, once, and every map can draw against it — the
 * capability SAS calls "custom boundaries from a geographic data provider".
 *
 * `list` never carries the geometry: a picker that needed every file's polygons
 * to draw a dropdown would download megabytes to show three words. `get` is the
 * one that returns shapes, and only the map that needs them calls it.
 */
export interface BoundarySetSummary {
  id: number
  name: string
  feature_count: number
  /** The per-feature properties a data column can be matched against, detected
   *  at upload. A file carrying both `name` and `name_ar` matches either. */
  key_properties: string[]
  /** A few region names, so an author can see whether their column will match
   *  before building a widget and finding out it will not. */
  sample_names: string[]
  created_by: number | null
  created_at: string | null
}

export interface BoundarySetDetail extends BoundarySetSummary {
  geometry: { type: string; features: unknown[] }
}

export const boundarySetsApi = {
  list: () => api.get<BoundarySetSummary[]>('/boundary-sets').then(r => r.data),
  get: (id: number) =>
    api.get<BoundarySetDetail>(`/boundary-sets/${id}`).then(r => r.data),
  create: (name: string, geometry: unknown) =>
    api.post<BoundarySetSummary>('/boundary-sets', { name, geometry }).then(r => r.data),
  remove: (id: number) => api.delete(`/boundary-sets/${id}`).then(() => undefined),
  /** Pin data values to regions (value -> feature index); replaces all pins. */
  setPins: (id: number, pins: Record<string, number>) =>
    api.put<{ id: number; pins: Record<string, number> }>(`/boundary-sets/${id}/pins`, { pins }).then(r => r.data),
  /** Starter packs shipped with this deployment (Egypt governorates, US states...). */
  packs: () => api.get<BoundaryPack[]>('/boundary-sets/packs').then(r => r.data),
  /** Install a pack as an ordinary boundary set of the org. */
  installPack: (packId: string, acceptTerms = false) =>
    api.post<BoundarySetSummary>(
      `/boundary-sets/packs/${encodeURIComponent(packId)}/install`,
      acceptTerms ? { accept_terms: true } : undefined,
    ).then(r => r.data),
}

/** The org's basemap tile server; null tile_url = no basemap (the default). */
export interface MapSettings {
  tile_url: string | null
  attribution: string | null
  contrast_tile_url: string | null
}

export interface CalendarSettings { fiscal_year_start_month: number }

/** The org's fiscal year (E10): the month it starts in. */
export const calendarSettingsApi = {
  get: () => api.get<CalendarSettings>('/calendar-settings').then(r => r.data),
  set: (body: CalendarSettings) => api.put<CalendarSettings>('/calendar-settings', body).then(r => r.data),
}

export const mapSettingsApi = {
  get: () => api.get<MapSettings>('/map-settings').then(r => r.data),
  set: (body: MapSettings) => api.put<MapSettings>('/map-settings', body).then(r => r.data),
}

/** One install-wide setting, as Admin -> Settings shows it. A secret's value
 *  is never sent: `value` is null and `is_set` says whether it has one. */
export interface PlatformSetting {
  key: string
  label: string
  help: string
  type: 'bool' | 'int' | 'float' | 'str'
  bounds: { ge?: number; gt?: number; le?: number; lt?: number }
  editable: boolean
  secret: boolean
  restart: boolean
  options: string[]
  value: string | number | boolean | null
  is_set: boolean
  default: string | number | boolean | null
  source: 'saved' | 'environment'
  updated_by: string | null
  updated_at: string | null
}
export interface PlatformSettingsCategory { id: string; label: string; settings: PlatformSetting[] }
export interface PlatformSettingsOut { categories: PlatformSettingsCategory[]; restart_required?: string[] }
export interface LlmTestResult { ok: boolean; latency_ms: number; model: string; detail: string }

export const platformSettingsApi = {
  get: () => api.get<PlatformSettingsOut>('/platform/settings').then(r => r.data),
  /** null for a key removes its saved value (back to the environment). */
  save: (values: Record<string, string | number | boolean | null>) =>
    api.put<PlatformSettingsOut>('/platform/settings', { values }).then(r => r.data),
  testLlm: (body: { llm_base_url?: string; llm_model?: string; llm_api_key?: string; endpoint_id?: string }) =>
    api.post<LlmTestResult>('/platform/settings/test-llm', body).then(r => r.data),
  getLlmEndpoints: () => api.get<LlmEndpointsOut>('/platform/settings/llm-endpoints').then(r => r.data),
  saveLlmEndpoints: (endpoints: LlmEndpointIn[], defaultChoice: string) =>
    api.put<LlmEndpointsOut>('/platform/settings/llm-endpoints', { endpoints, default: defaultChoice }).then(r => r.data),
  resetLlmEndpoints: () => api.delete<LlmEndpointsOut>('/platform/settings/llm-endpoints').then(r => r.data),
}

/** One endpoint's light: from the background probe or the last real call. */
export interface LlmStatus { ok: boolean; latency_ms: number | null; checked_at: string; error: string | null }
export interface LlmEndpoint {
  id: string; name: string; model: string; enabled: boolean; is_default: boolean
  status: LlmStatus | null
  /** 1-10 rank Auto routes by (set by the admin, or guessed from the name). */
  strength: number
  /** Context window in tokens (set, or read from the endpoint); null = unknown. */
  context: number | null
  /** Admin view only. */
  base_url?: string; has_api_key?: boolean
  strength_set?: number | null; context_set?: number | null; max_model_len?: number | null
}
export interface LlmEndpointsOut {
  llm_enabled: boolean
  /** An endpoint id, or 'auto'. */
  default: string
  /** The endpoint Auto would use now; null when none is up. */
  auto_pick: string | null
  source: 'saved' | 'deployment' | 'environment'
  endpoints: LlmEndpoint[]
  /** This person's most recent answered calls, oldest first. */
  last_used?: LlmUse[]
}
export interface LlmUse {
  id: string; name: string; model: string; weight: string; auto: boolean
  feature: string | null; at: string
}
export interface LlmEndpointIn {
  id?: string; name: string; base_url: string; model: string
  /** undefined/null keeps the stored key; '' removes it. */
  api_key?: string | null
  enabled: boolean
  /** 0/empty = guess from the model name. */
  strength?: number
  /** 0/empty = read from the endpoint. */
  context?: number
}

export const llmApi = {
  endpoints: (refresh = false) =>
    api.get<LlmEndpointsOut>('/llm/endpoints', { params: refresh ? { refresh: true } : undefined }).then(r => r.data),
}

export interface BoundaryPack {
  id: string
  name: string
  country: string | null
  level: string | null
  feature_count: number
  description: string | null
  source: string
  license: string
  license_url: string | null
  /** Credit every map drawn from this pack must show. */
  attribution?: string | null
  /** Terms an admin must accept before installing (requires_acceptance). */
  terms?: string | null
  requires_acceptance?: boolean
}

export interface PredictionModelSummary {
  id: number
  name: string
  dataset_id: number
  target: string
  features: string[]
  task: 'classification' | 'regression'
  model_family: string
  score: number | null
  score_name: string | null
  created_at: string | null
  /** E13: training under an existing name makes its next version; one per
   *  name is the champion ("use the current champion" means it). */
  version?: number
  status?: 'champion' | 'candidate'
  promoted_at?: string | null
  card?: ModelCard | null
  has_training_profile?: boolean
  /** E13: the latest kept drift check, as a level. */
  last_drift?: { at: string; overall: ModelDrift['overall'] } | null
}

/** The dataset as it is now, beside the state a model card recorded. */
export interface DatasetSummaryForCard {
  row_count: number | null
  content_sha256?: string | null
  last_refreshed_at?: string | null
}

/** E13: how a saved model was chosen and on what. */
export interface ModelCard {
  target?: string
  task?: string
  model_family?: string
  score?: number | null
  score_name?: string
  candidates?: { model: string; score: number | null }[]
  baseline_score?: number | null
  lift_over_baseline?: number | null
  beats_baseline?: boolean | null
  predictors_used?: string[]
  predictors_skipped?: ({ column?: string; reason?: string } | string)[]
  n_train?: number | null
  n_test?: number | null
  n_fitted?: number | null
  split?: { kind: string; column?: string; test_share?: number } | null
  partition?: string | null
  row_scope?: string
  caveats?: string[]
  dataset?: { id: number; name: string; row_count: number | null; content_sha256: string | null;
              last_refreshed_at: string | null }
  trained_by?: string
  trained_at?: string
}

export interface ScoreResult {
  predictions: (string | number)[]
  n_scored: number
  /** Values a categorical feature never held during training, per column. The
   *  model encodes them as "none of the above" and has no opinion, so scoring
   *  data it recognises none of would otherwise look confident. */
  unseen_values: Record<string, string[]>
  target: string
  task: string
  model_family: string
  /** The version that made these predictions (E13). */
  model?: { id: number; name: string; version: number; status: string }
}

/** Fitted models kept so they can score rows they have never seen — the one
 *  thing every other analysis here cannot do, because they all refit and
 *  discard. The artifact never crosses this boundary: it is a pickle and the
 *  browser has no use for it. */
export const predictionModelsApi = {
  list: (datasetId: number) =>
    api.get<PredictionModelSummary[]>(`/datasets/${datasetId}/prediction-models`).then(r => r.data),
  train: (datasetId: number, body: { name: string; target: string; predictors?: string[]; partition?: string }) =>
    api.post<PredictionModelSummary>(`/datasets/${datasetId}/prediction-models`, body).then(r => r.data),
  score: (datasetId: number, modelId: number,
          body: { rows?: Record<string, unknown>[]; from_dataset?: boolean; limit?: number }) =>
    api.post<ScoreResult>(`/datasets/${datasetId}/prediction-models/${modelId}/score`, body).then(r => r.data),
  remove: (datasetId: number, modelId: number) =>
    api.delete(`/datasets/${datasetId}/prediction-models/${modelId}`).then(() => undefined),
  promote: (datasetId: number, modelId: number) =>
    api.post<PredictionModelSummary>(`/datasets/${datasetId}/prediction-models/${modelId}/promote`).then(r => r.data),
  /** E13: how far today's rows have moved from this version's training rows. */
  drift: (datasetId: number, modelId: number) =>
    api.get<ModelDrift>(`/datasets/${datasetId}/prediction-models/${modelId}/drift`).then(r => r.data),
  /** E13: check drift now and keep the check in the version's history. */
  checkDrift: (datasetId: number, modelId: number) =>
    api.post<ModelDrift & { history: DriftSnapshot[] }>(
      `/datasets/${datasetId}/prediction-models/${modelId}/drift-checks`).then(r => r.data),
  driftHistory: (datasetId: number, modelId: number) =>
    api.get<{ history: DriftSnapshot[] }>(
      `/datasets/${datasetId}/prediction-models/${modelId}/drift-history`).then(r => r.data.history),
  /** E13: score every row into a new dataset, as a durable job. */
  scoreJob: (datasetId: number, modelId: number) =>
    api.post<{ id: number; state: string; kind: string; subject: string | null }>(
      `/datasets/${datasetId}/prediction-models/${modelId}/score-jobs`).then(r => r.data),
}

/** E13: one kept drift check (the scheduler's daily one, or one asked for). */
export interface DriftSnapshot {
  at: string
  overall: ModelDrift['overall']
  rows: number | null
  max_psi: number | null
  features: Record<string, number | null>
}

export interface ModelDrift {
  overall: 'stable' | 'moderate' | 'major' | 'missing'
  rows: number
  trained_rows?: number | null
  model: { id: number; name: string; version: number }
  features: { feature: string; psi: number | null; level: 'stable' | 'moderate' | 'major' | 'missing';
              rows: number; new_values?: string[] }[]
}

export interface AggregatePreflight {
  /** Columns every row-level security rule on the source reads: the grain must include them. */
  rls_columns: string[]
  grain_candidates: string[]
  measure_candidates: string[]
}
export interface AggregateSpec {
  grain: string[]
  measures: { column: string; agg: 'sum' | 'count' | 'min' | 'max'; name: string }[]
}
export interface AggregateListItem {
  dataset: Dataset & { aggregate_spec?: AggregateSpec | null; refresh_interval_minutes?: number | null }
  last_error: string | null
  attempts: number
}
export const aggregatesApi = {
  preflight: (datasetId: number) =>
    api.get<AggregatePreflight>(`/datasets/${datasetId}/aggregate-preflight`).then(r => r.data),
  list: (datasetId: number) =>
    api.get<AggregateListItem[]>(`/datasets/${datasetId}/aggregates`).then(r => r.data),
  create: (datasetId: number, body: { name: string; grain: string[];
    measures: { column: string; agg: string; name?: string }[]; refresh_interval_minutes: number | null }) =>
    api.post<Dataset>(`/datasets/${datasetId}/aggregates`, body).then(r => r.data),
  update: (datasetId: number, aggId: number, body: { grain?: string[];
    measures?: { column: string; agg: string; name?: string }[]; refresh_interval_minutes?: number | null }) =>
    api.put<Dataset>(`/datasets/${datasetId}/aggregates/${aggId}`, body).then(r => r.data),
}

export const analysisApi = {
  run: (id: number, type = 'full') =>
    api.post(`/datasets/${id}/analysis`, { analysis_type: type }).then(r => r.data),
  get: (id: number) =>
    api.get(`/datasets/${id}/analysis`).then(r => r.data),
  // A2: KMeans segmentation over selected (or all usable) numeric columns.
  segment: (id: number, columns?: string[]) =>
    api.post<SegmentResult>(`/datasets/${id}/segment`, { columns: columns ?? null }).then(r => r.data),
  /** Which factors move an outcome, ranked by lift against the baseline.
   *  `targetValue` picks the outcome of interest for a categorical target;
   *  omitted means the rarest value, which is nearly always the one being
   *  asked about (churn, fraud, failure). */
  keyInfluencers: (id: number, target: string, targetValue?: string, factors?: string[]) =>
    api.post<KeyInfluencersResult>(`/datasets/${id}/key-influencers`, {
      target, target_value: targetValue ?? null, factors: factors ?? null,
    }).then(r => r.data),
  /** Which values co-occur more than chance predicts. Ranked by lift, with the
   *  base rate beside it -- a 90%-confident rule means nothing if the outcome
   *  happens 90% of the time anyway. */
  associationRules: (id: number, columns?: string[]) =>
    api.post<AssociationRulesResult>(`/datasets/${id}/association-rules`,
      { columns: columns ?? null }).then(r => r.data),
}

export interface AssociationRule {
  if: string
  then: string
  lift: number
  confidence: number
  /** How often the conclusion holds anyway — what `confidence` must be read against. */
  base_rate: number
  support_rows: number
  support_pct: number
}

export interface AssociationRulesResult {
  kind: string
  columns: { name: string; type: string }[]
  rows: AssociationRule[]
  meta: Record<string, unknown>
  warnings: string[]
}

export interface KeyInfluencer {
  factor: string
  group: string
  grouped_by: 'value' | 'quantile'
  /** Present for a categorical target. */
  rate?: number
  /** Present for a numeric target. */
  mean?: number
  baseline: number
  /** The group's rate (or mean) divided by the baseline. Above 1 means the
   *  outcome is more common in this group; below 1 means less. */
  lift: number
  rows: number
  share_of_rows: number
}

export interface KeyInfluencersResult {
  kind: 'key_influencers'
  columns: { name: string; dtype: string }[]
  rows: KeyInfluencer[]
  meta: {
    method: string
    target: string
    target_value: string | null
    measure: 'rate' | 'mean'
    baseline: number
    n_rows_used: number
    n_rows_total: number
    sampled: boolean
    groups_considered: number
    /** Influence is not causation, and the server says so in the payload so a
     *  UI cannot render "top driver" without the caveat available. */
    caveat: string
  }
  warnings: string[]
}

// The list endpoints return the full shapes; these aliases exist because two
// pages imported summary-named types that were never declared, and the noise
// buried real typecheck failures all session.
export type DatasetSummary = Dataset
export type ReportSummary = Report

/**
 * Self-serve subscriptions: a viewer signs THEMSELVES up for a recurring copy.
 *
 * Needs only 'view' on the report. The schedule is owned by the subscriber,
 * because a schedule resolves row-level security as its creator -- joining
 * someone else's would deliver THEIR slice of the data.
 */
export interface Subscription {
  subscribed: boolean
  id?: number
  calendar?: { kind: string; hour: number; minute: number; weekday?: number; monthday?: number }
  interval_minutes?: number
  format?: 'xlsx' | 'pdf'
  last_run_at?: string | null
  last_status?: string | null
}

export interface SubscribeBody {
  cadence?: 'daily' | 'weekly' | 'monthly'
  hour?: number
  minute?: number
  weekday?: number
  monthday?: number
  format?: 'xlsx' | 'pdf'
  timezone?: string | null
}

export const subscriptionApi = {
  get: (reportId: number) =>
    api.get<Subscription>(`/reports/${reportId}/subscription`).then(r => r.data),
  subscribe: (reportId: number, body: SubscribeBody) =>
    api.post<Subscription>(`/reports/${reportId}/subscribe`, body).then(r => r.data),
  unsubscribe: (reportId: number) => api.delete(`/reports/${reportId}/subscribe`),
}

export interface ReportGrant {
  id: number
  user_id: number
  email: string
  level: 'view' | 'edit' | 'data'
}

/** "Share to": per-user grants on one authored dashboard. Distinct from
 *  publishing (audience at view strength) -- a grant gives one named person
 *  capability, including seeing an unpublished draft. Author or admin only;
 *  grantees are addressed by email, deliberately not by a user picker, so
 *  sharing never doubles as an org-directory listing. */
export const reportGrantsApi = {
  list: (reportId: number) =>
    api.get<ReportGrant[]>(`/reports/${reportId}/grants`).then(r => r.data),
  create: (reportId: number, body: { email: string; level: 'view' | 'edit' | 'data' }) =>
    api.post<ReportGrant>(`/reports/${reportId}/grants`, body).then(r => r.data),
  remove: (reportId: number, grantId: number) =>
    api.delete(`/reports/${reportId}/grants/${grantId}`).then(() => undefined),
}

/** One entry of the signed-in user's recently opened dashboards. */
export interface RecentReport {
  id: number
  name: string
  viewed_at: string
  published: boolean
  created_by: number | null
  is_mine: boolean
  my_capability: 'view' | 'edit' | 'data'
}

/** One thing a saved version or a release names that no longer exists (E09). */
export interface MissingDependency {
  page: string | null
  widget: string
  kind: 'dataset' | 'field' | 'parameter' | 'hierarchy'
  name: string
}

/** "Margin by region" uses the field "Margin", … — for a confirm or a toast. */
export function describeMissing(missing: MissingDependency[], max = 4): string {
  const what = { dataset: 'dataset', field: 'field', parameter: 'parameter', hierarchy: 'hierarchy' }
  const lines = missing.slice(0, max).map(m => `"${m.widget}" uses the ${what[m.kind]} "${m.name}"`)
  const more = missing.length > max ? `, and ${missing.length - max} more` : ''
  return lines.join('; ') + more
}

export const reportsApi = {
  /** This user's recently OPENED dashboards, newest first. Distinct from
   *  ordering the list by `updated_at`, which reports what changed rather than
   *  what this person looked at. */
  recent: (limit = 8) =>
    api.get<RecentReport[]>('/reports/recent', { params: { limit } }).then(r => r.data),
  list:   ()                                       => api.get<Report[]>('/reports').then(r => r.data),
  get:    (id: number)                             => api.get<Report>(`/reports/${id}`).then(r => r.data),
  create: (data: { name: string; description?: string; dataset_id?: number }) =>
    api.post<Report>('/reports', data).then(r => r.data),
  update: (id: number, data: Partial<{ name: string; description: string; dataset_id: number; additional_dataset_ids: number[]; theme: string; display_rules: DisplayRule[] }>) =>
    api.patch<Report>(`/reports/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/reports/${id}`),
  /** Publish/unpublish an authored dashboard: published = the whole org may
   *  OPEN it, view-only. Author or admin only; legacy unowned reports 400. */
  setPublished: (id: number, published: boolean) =>
    api.post<{ published: boolean }>(`/reports/${id}/publish`, { published }).then(r => r.data),
  /** E09: make the draft what viewers see. Editors only. */
  release: (id: number, note?: string) =>
    api.post<{ release: ReportRelease; unreleased_changes: boolean; missing?: MissingDependency[] }>(`/reports/${id}/release`, note ? { note } : {}).then(r => r.data),
  /** The page copilot: one chat message about the OPEN page, answered by the
   *  same LLM endpoint the agent uses, with any page edits already applied
   *  server-side by the time the reply returns. `history` is the panel's own
   *  recent turns — the chat is a command surface, not a stored thread. */
  /** Version history (R2): restorable content snapshots, newest first. The
   *  list is metadata only — the snapshot content travels on restore. */
  versions: (reportId: number) =>
    api.get<{ id: number; revision: number; created_at: string | null
              created_by: string | null; pages: number; widgets: number
              via?: string | null; note?: string | null }[]>(
      `/reports/${reportId}/versions`).then(r => r.data),
  restoreVersion: (reportId: number, versionId: number) =>
    api.post<{ restored_version_id: number; restored_revision: number; note: string
               saved_current_as_version_id?: number | null; missing?: MissingDependency[] }>(
      `/reports/${reportId}/versions/${versionId}/restore`, {}).then(r => r.data),
  /** E09: what a version's widgets use that no longer exists. */
  versionDependencies: (reportId: number, versionId: number) =>
    api.get<{ missing: MissingDependency[] }>(
      `/reports/${reportId}/versions/${versionId}/dependencies`).then(r => r.data),
  copilot: (reportId: number, pageId: number,
            body: { message: string
                    history?: { role: 'user' | 'assistant'; content: string }[]
                    selected_widget_id?: number | null }) =>
    api.post<{ reply: string
               applied: { op: 'create' | 'update' | 'delete' | 'add_calculated_column'; widget_id: number | null; title: string | null }[]
               notes: string[]
               /** Present when the message was a DATA question: the copilot
                *  delegated to the agent and these are the result rows. */
               results: AgentResult[]
               /** The reply's numbers traced to those rows (E11); null when
                *  nothing was queried. */
               evidence?: AnswerEvidence | null
               /** The version captured BEFORE the copilot's change (restoring it undoes the change). */
               before_version_id?: number | null
               summary?: string | null }>(
      `/reports/${reportId}/pages/${pageId}/copilot`, body).then(r => r.data),
  // Cheap poll target: just the counter, none of the page/widget eager loading
  // GET /reports/{id} does.
  getRevision: (id: number) =>
    api.get<{ revision: number }>(`/reports/${id}/revision`).then(r => r.data.revision),
  /** Sensitivity labels: the current label + the allowed set. */
  getClassification: (id: number) =>
    api.get<{ label: string | null; options: string[]
              /** Phase 7.3: the lowest label the report's data allows, and the label in force. */
              floor?: string | null; floor_reasons?: string[]
              effective?: string | null; effective_reasons?: string[] }>(`/reports/${id}/classification`).then(r => r.data),
  setClassification: (id: number, label: string) =>
    api.put<Report>(`/reports/${id}/classification`, { label }).then(r => r.data),
  /** Report-level common filters, applied to every widget. */
  addCommonFilter: (id: number, body: { column: string; op: string; value: unknown }) =>
    api.post<{ id: number; column: string; op: string; value: unknown }>(`/reports/${id}/common-filters`, body).then(r => r.data),
  deleteCommonFilter: (id: number, filterId: number) =>
    api.delete(`/reports/${id}/common-filters/${filterId}`),

  addPage:    (rid: number, data: Partial<ReportPage> & { name: string; position: number }) =>
    api.post<ReportPage>(`/reports/${rid}/pages`, data).then(r => r.data),
  updatePage: (rid: number, pid: number, data: Partial<ReportPage>) =>
    api.patch<ReportPage>(`/reports/${rid}/pages/${pid}`, data).then(r => r.data),
  deletePage: (rid: number, pid: number) => api.delete(`/reports/${rid}/pages/${pid}`),

  addWidget:    (rid: number, pid: number, data: Partial<Widget>) =>
    api.post<Widget>(`/reports/${rid}/pages/${pid}/widgets`, data).then(r => r.data),
  /** `base_revision` (E09): the report revision this copy of the widget came
   *  from. A change by someone else since then is a 409 `edit_conflict`. */
  updateWidget: (rid: number, pid: number, wid: number, data: Partial<Widget> & { base_revision?: number }) =>
    api.patch<Widget>(`/reports/${rid}/pages/${pid}/widgets/${wid}`, data).then(r => r.data),
  deleteWidget: (rid: number, pid: number, wid: number) =>
    api.delete(`/reports/${rid}/pages/${pid}/widgets/${wid}`),

  listBookmarks:  (rid: number) => api.get<Bookmark[]>(`/reports/${rid}/bookmarks`).then(r => r.data),
  addBookmark:    (rid: number, data: { name: string; position: number; state: BookmarkState }) =>
    api.post<Bookmark>(`/reports/${rid}/bookmarks`, data).then(r => r.data),
  deleteBookmark: (rid: number, bid: number) => api.delete(`/reports/${rid}/bookmarks/${bid}`),

  /** Download the server-rendered PDF. Blob response; the browser saves it. */
  downloadPdf: async (rid: number, name: string,
                      opts?: { paper?: string; orientation?: string; contents?: boolean; pages?: number[] }) => {
    const params: Record<string, string> = {}
    if (opts?.paper) params.paper = opts.paper
    if (opts?.orientation) params.orientation = opts.orientation
    if (opts?.contents === false) params.contents = 'false'
    if (opts?.pages?.length) params.pages = opts.pages.join(',')
    const r = await api.get(`/reports/${rid}/pdf`, { responseType: 'blob', params })
    const url = URL.createObjectURL(r.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${(name || 'report').replace(/[^a-z0-9 _-]/gi, '').trim() || 'report'}.pdf`
    document.body.appendChild(a); a.click(); a.remove()
    URL.revokeObjectURL(url)
  },
  /** One self-contained HTML file: visible pages, results frozen as the
   *  caller sees them, opens offline from file://. */
  downloadPackage: async (rid: number, name: string) => {
    const r = await api.get(`/reports/${rid}/package`, { responseType: 'blob' })
    const url = URL.createObjectURL(r.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${(name || 'report').replace(/[^a-z0-9 _-]/gi, '').trim() || 'report'}.html`
    document.body.appendChild(a); a.click(); a.remove()
    URL.revokeObjectURL(url)
  },
  /** The dashboard's data as Excel, one sheet per chart, as the caller sees it.
   *  Resolves to how many sheets were written and how many datasets were
   *  withheld by their export policy. */
  downloadXlsx: async (rid: number, name: string) => {
    const r = await api.get(`/reports/${rid}/xlsx`, { responseType: 'blob' })
    const url = URL.createObjectURL(r.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${(name || 'dashboard').replace(/[^a-z0-9 _-]/gi, '').trim() || 'dashboard'}.xlsx`
    document.body.appendChild(a); a.click(); a.remove()
    URL.revokeObjectURL(url)
    return { sheets: Number(r.headers?.['x-sheet-count'] ?? 0), withheld: Number(r.headers?.['x-withheld-datasets'] ?? 0) }
  },
}

export interface WidgetTemplate {
  id: number
  name: string
  widget_type: string
  config: Record<string, unknown>
  created_at?: string
}

export const widgetTemplatesApi = {
  list:   ()                                                     => api.get<WidgetTemplate[]>('/widget-templates').then(r => r.data),
  create: (data: { name: string; widget_type: string; config: Record<string, unknown> }) =>
    api.post<WidgetTemplate>('/widget-templates', data).then(r => r.data),
  delete: (id: number)                                          => api.delete(`/widget-templates/${id}`),
}

export const hierarchyApi = {
  get:          (dsId: number)                              => api.get<HierarchyNode[]>(`/datasets/${dsId}/hierarchy`).then(r => r.data),
  create:       (dsId: number, data: Partial<HierarchyNode>) => api.post<HierarchyNode>(`/datasets/${dsId}/hierarchy`, data).then(r => r.data),
  update:       (dsId: number, nid: number, data: Partial<HierarchyNode>) => api.patch<HierarchyNode>(`/datasets/${dsId}/hierarchy/${nid}`, data).then(r => r.data),
  delete:       (dsId: number, nid: number)                 => api.delete(`/datasets/${dsId}/hierarchy/${nid}`),
  autoGenerate: (dsId: number)                              => api.post<HierarchyNode[]>(`/datasets/${dsId}/hierarchy/auto-generate`).then(r => r.data),
  /** A drill chain's levels in a new order, outermost first -- one step. */
  reorder:      (dsId: number, ids: number[])               => api.put<HierarchyNode[]>(`/datasets/${dsId}/hierarchy/order`, { ids }).then(r => r.data),
}

export const columnFormatsApi = {
  get: (dsId: number) =>
    api.get<Record<string, CalcColumnFormat>>(`/datasets/${dsId}/column-formats`).then(r => r.data),
  set: (dsId: number, column: string, format: CalcColumnFormat | null) =>
    api.put<Record<string, CalcColumnFormat>>(`/datasets/${dsId}/column-formats`, { column, format }).then(r => r.data),
}

export interface DataPreviewFilter {
  column: string
  op: 'eq' | 'ne' | 'gt' | 'lt' | 'gte' | 'lte' | 'contains' | 'startswith'
  value: string
}

export const dataPreviewApi = {
  query: (
    dsId: number,
    filters: DataPreviewFilter[],
    calculatedColumns: CalcColumn[],
    limit: number,
    offset: number,
    sortBy?: string,
    sortDir?: 'asc' | 'desc',
    search?: string,
  ) =>
    api.post<{ columns: string[]; rows: unknown[][]; total: number }>(
      `/datasets/${dsId}/data-preview`,
      { filters, calculated_columns: calculatedColumns, limit, offset,
        sort_by: sortBy ?? null, sort_dir: sortDir ?? 'asc', search: search ?? null }
    ).then(r => r.data),
}

export const filterExprApi = {
  update:  (dsId: number, expression: string | null) =>
    api.patch<Dataset>(`/datasets/${dsId}/filter`, { expression }).then(r => r.data),
  preview: (dsId: number, expression: string, calculatedColumns: CalcColumn[] = []) =>
    api.post<{ ok: boolean; passing?: number; total: number; error?: string }>(
      `/datasets/${dsId}/filter-preview`,
      { expression, calculated_columns: calculatedColumns }
    ).then(r => r.data),
}

export interface Relationship {
  id: number
  org_id: number
  from_dataset_id: number
  from_column: string
  to_dataset_id: number
  to_column: string
  created_at: string
  /** How this link came to be, most authoritative first:
   *  `confirmed` (a human approved it) > `declared` (a real FK read from the
   *  source catalog) > `inferred` (this platform's guess). */
  source: 'confirmed' | 'declared' | 'inferred'
  /** 0..1. Meaningful for `inferred`; 1.0 for the other two. */
  confidence: number
  cardinality?: 'one_to_many' | 'many_to_one' | 'one_to_one' | null
}

export const relationshipsApi = {
  list:   ()                                                                          => api.get<Relationship[]>('/relationships').then(r => r.data),
  create: (body: { from_dataset_id: number; from_column: string; to_dataset_id: number; to_column: string }) =>
    api.post<Relationship>('/relationships', body).then(r => r.data),
  delete: (id: number)                                                                => api.delete(`/relationships/${id}`),
  /** How a candidate mapping will carry a filter value (read as the caller). */
  check: (body: { from_dataset_id: number; from_column: string; to_dataset_id: number; to_column: string }) =>
    api.post<MappingCheck>('/relationships/check', body).then(r => r.data),
}

export interface MappingCheck {
  source_values: number; matched_values: number; pct_values: number
  target_values: number; pct_target_covered: number
  unmatched: { value: string; rows: number }[]; unmatched_count: number
  near_matches: { source: string; target: string }[]
  type_mismatch: string | null
}

export const calcColumnsApi = {
  list:    (dsId: number)                            => api.get<CalcColumn[]>(`/datasets/${dsId}/calculated-columns`).then(r => r.data),
  save:    (dsId: number, col: CalcColumn)           => api.put<CalcColumn[]>(`/datasets/${dsId}/calculated-columns`, col).then(r => r.data),
  // `force`: delete even though something names it (the server answers 409 otherwise).
  delete:  (dsId: number, name: string, force?: boolean) => api.delete<CalcColumn[]>(`/datasets/${dsId}/calculated-columns/${encodeURIComponent(name)}`, force ? { params: { force: true } } : undefined).then(r => r.data),
  preview: (dsId: number, expression: string)        => api.post<{ok:boolean;dtype?:string;sample?:unknown[];error?:string}>(`/datasets/${dsId}/calculated-columns/preview`, { expression }).then(r => r.data),
}

export const customFunctionsApi = {
  list:    (dsId: number)                => api.get<CustomFunction[]>(`/datasets/${dsId}/custom-functions`).then(r => r.data),
  save:    (dsId: number, fn: CustomFunction) => api.put<CustomFunction[]>(`/datasets/${dsId}/custom-functions`, fn).then(r => r.data),
  delete:  (dsId: number, name: string)  => api.delete<CustomFunction[]>(`/datasets/${dsId}/custom-functions/${encodeURIComponent(name)}`).then(r => r.data),
  preview: (dsId: number, params: string[], expression: string, sampleValues: Record<string, unknown>) =>
    api.post<{ok:boolean; result?: unknown; error?: string}>(
      `/datasets/${dsId}/custom-functions/preview`, { params, expression, sample_values: sampleValues }
    ).then(r => r.data),
}

export interface ColumnMeta {
  /** Overrides the detected dtype for grouping purposes — a numeric ZIP is a
   *  category. `geography` IS a category; it additionally says what the column
   *  is a category of, so a map built on it inherits its boundary set instead
   *  of asking the author again on every widget. */
  role?: 'measure' | 'category' | 'temporal' | 'geography' | 'freetext' | 'identifier'
  /** Which uploaded boundary set draws this column. Only meaningful alongside
   *  role='geography'. */
  boundary_set_id?: number
  /** Applied when the column is assigned to a measure role. */
  aggregation?: string
  /** Hidden from field pickers without deleting anything. */
  hidden?: boolean
  /** Whether the suggestion engines may VOLUNTEER this column. Distinct from
   *  `hidden`, and the distinction is the point: hidden removes the column from
   *  the pickers and the analysis entirely, this leaves it fully usable by
   *  anyone who asks and only stops the platform offering it unprompted.
   *  Undefined means eligible — absence is not a restriction. */
  eligible_for_suggestion?: boolean
  /** How strongly this column is an OUTCOME worth explaining; higher first,
   *  undefined means "not a target". What lets the "what drives X" analyses
   *  run unattended instead of guessing from flag-shaped columns. */
  target_candidate_priority?: number
  label?: string
}

export interface PrepStep { kind: string; [k: string]: unknown }

export interface JoinCheck {
  rows: number
  matched_rows: number
  pct_rows: number
  blank_keys: number
  unmatched: { key: string; rows: number }[]
  unmatched_values: number
  duplicate_right_keys: number
  duplicate_examples: { key: string; count: number }[]
  rows_after: number | null
  /** rows_after / rows (E06 fan-out); null when it cannot be computed. */
  multiplier?: number | null
  /** The joined side: its size, and rows whose key finds no partner here. */
  right_rows?: number
  right_unmatched_rows?: number
  type_mismatch: string[]
  error?: string
}

export const prepApi = {
  /** How a candidate join (steps[index]) will land, before it is saved. */
  joinCheck: (dsId: number, steps: PrepStep[], index: number) =>
    api.post<JoinCheck>(`/datasets/${dsId}/join-check`, { steps, index }).then(r => r.data),
  get: (dsId: number) =>
    api.get<PrepStep[]>(`/datasets/${dsId}/prep-steps`).then(r => r.data),
  /** Replaces the whole pipeline — same contract as column-meta. */
  set: (dsId: number, steps: PrepStep[]) =>
    api.put<PrepStep[]>(`/datasets/${dsId}/prep-steps`, steps).then(r => r.data),
  preview: (dsId: number, steps: PrepStep[]) =>
    api.post<{ before: { rows: number; columns: string[] }
               after: { rows: number; columns: string[] }
               /** Per-step row counts, in step order — lets the editor show
                   "N in → M out" per card without a separate call per step. */
               steps: { rows_in: number; rows_out: number; columns: string[]; skipped?: boolean }[]
               sample: { columns: string[]; rows: unknown[][] } }>(
      `/datasets/${dsId}/prep-preview`, steps).then(r => r.data),
  /** Run the pipeline once and keep the result as a new dataset.
   *
   *  Sends the CANDIDATE steps, so what gets saved is the result on screen —
   *  saved pipeline or not. The new dataset is a snapshot: it does not follow
   *  its sources, and `rebuild` is the deliberate way to catch it up. */
  materialize: (dsId: number, body: { name: string; description?: string; steps: PrepStep[] }) =>
    api.post<Dataset>(`/datasets/${dsId}/materialize`, body).then(r => r.data),
  rebuild: (dsId: number) =>
    api.post<Dataset>(`/datasets/${dsId}/rebuild`).then(r => r.data),
}

export const outlierApi = {
  details: (dsId: number, column: string, detector?: string) =>
    api.post(`/datasets/${dsId}/outlier-details`, null, { params: { column, detector } }).then(r => r.data),
}

export interface AppNotification {
  id: number; kind: string; text: string; link: string | null; created_at: string; read: boolean
}

export const notificationsApi = {
  list: () => api.get<{ unread: number; notifications: AppNotification[] }>('/notifications').then(r => r.data),
  markRead: () => api.post<{ marked: number }>('/notifications/mark-read').then(r => r.data),
}

export interface IncrementalSettingsInput {
  strategy: 'full' | 'incremental'
  cursor_column?: string | null
  key_column?: string | null
  lookback_hours?: number | null
  full_reload_days?: number | null
}

export interface IncrementalSettings extends IncrementalSettingsInput {
  /** The newest cursor value loaded (editors only). */
  cursor_value: string | null
  last_full_at: string | null
  /** A rebuilt dataset set to run after its source refreshes. */
  after_source: boolean
}

export type DataCheckKind = 'not_null' | 'unique' | 'accepted_values' | 'row_count' | 'row_drop' | 'rule'

export interface DataCheckInput {
  kind: DataCheckKind
  column?: string | null
  params?: { values?: string[]; min?: number | null; max?: number | null; max_drop_pct?: number; expression?: string }
  severity: 'warn' | 'block'
  enabled?: boolean
}

export interface DataCheck extends DataCheckInput {
  id: number
  enabled: boolean
  created_at: string | null
}

/** One check's outcome on one load (`kind: 'schema'` for column-change notes). */
export interface CheckResult {
  id?: number | null
  kind: DataCheckKind | 'schema'
  column: string | null
  severity: 'warn' | 'block'
  passed: boolean
  failing?: number
  detail: string | null
}

export interface DatasetRefreshRun {
  id: number
  trigger: 'schedule' | 'manual'
  status: 'running' | 'ok' | 'failed' | 'skipped' | 'blocked'
  started_at: string | null
  rows: number | null
  duration_ms: number | null
  error: string | null
  error_code: string | null
  checks: CheckResult[]
}

export interface PipelineHealth {
  state: 'ok' | 'failing' | 'stale' | 'unknown'
  last_refreshed_at: string | null
  freshness_hours: number | null
  /** Emails and https:// webhooks told as well as the owner (editors only). */
  recipients: string[]
  last_run: { status: string; trigger: string; started_at: string | null; rows: number | null
              duration_ms: number | null; error: string | null } | null
  next_retry_at: string | null
  can_edit: boolean
  /** Who the in-app notices go to (the creator, or the org admins): editors only. */
  owners?: string[]
  freshness_choices: number[]
}

export interface LineageGraph {
  sources: { id: number; name: string; type: string }[]
  datasets: {
    id: number; name: string; mode: string; source_id: number | null; joins: number[]
    extraction_kind: string
    transform: { count: number; kinds: string[] }
    load: { last_refreshed_at: string | null; strategy: string | null; cursor_column: string | null; staleness: 'fresh' | 'stale' | 'never' }
    /** A materialized dataset's sources (snapshot edges). */
    derived_from?: number[]
    /** Pipeline phase 2: the refresh is failing, or the data is past its freshness target. */
    health?: 'ok' | 'failing' | 'stale' | null
  }[]
  reports: { id: number; name: string; dataset_ids: number[] }[]
}

export const lineageApi = {
  graph: () => api.get<LineageGraph>('/datasets/lineage/graph').then(r => r.data),
}

export interface ReportComment {
  id: number; page_id: number | null; text: string; created_at: string; author: string; mine: boolean
}

export const commentsApi = {
  list: (reportId: number) => api.get<ReportComment[]>(`/reports/${reportId}/comments`).then(r => r.data),
  add: (reportId: number, text: string, pageId?: number) =>
    api.post<{ id: number }>(`/reports/${reportId}/comments`, { text, page_id: pageId ?? null }).then(r => r.data),
  delete: (reportId: number, commentId: number) => api.delete(`/reports/${reportId}/comments/${commentId}`),
}

export const shareLinksApi = {
  create: (reportId: number, expiresDays: number, pinned = false) =>
    api.post<{ id: number; token: string; expires_at: string; pinned: boolean; note: string }>(
      `/reports/${reportId}/share-links`, { expires_days: expiresDays, pinned }).then(r => r.data),
  list: (reportId: number) =>
    api.get<{ id: number; creator: string; created_at: string; expires_at: string; active: boolean; pinned: boolean;
      access_count: number; last_access_at: string | null }[]>(
      `/reports/${reportId}/share-links`).then(r => r.data),
  revoke: (reportId: number, linkId: number) => api.delete(`/reports/${reportId}/share-links/${linkId}`),
}

export const sharedApi = {
  // Anonymous: plain axios against the API base, no auth interceptor needed --
  // the token in the path is the credential.
  report: (token: string) =>
    api.get(`/shared/${token}`).then(r => r.data),
  widgetData: (token: string, widgetId: number) =>
    api.post(`/shared/${token}/widget-data/${widgetId}`).then(r => r.data),
}

export const embedConfigsApi = {
  // Admin CRUD -- authenticated, gated like guest-link management. The secret
  // is present in the create response ONLY (shown once); list/update never
  // carry it, mirroring shareLinksApi.
  create: (reportId: number, name: string, allowedOrigins: string[] = []) =>
    api.post<{ id: number; name: string; secret: string; allowed_origins: string[]; enabled: boolean;
      created_at: string; note: string }>(
      `/reports/${reportId}/embed-configs`, { name, allowed_origins: allowedOrigins }).then(r => r.data),
  list: (reportId: number) =>
    api.get<{ id: number; name: string; allowed_origins: string[]; enabled: boolean;
      created_at: string; last_used_at: string | null }[]>(
      `/reports/${reportId}/embed-configs`).then(r => r.data),
  setEnabled: (reportId: number, configId: number, enabled: boolean) =>
    api.patch(`/reports/${reportId}/embed-configs/${configId}`, { enabled }).then(r => r.data),
  delete: (reportId: number, configId: number) => api.delete(`/reports/${reportId}/embed-configs/${configId}`),
}

export const embedApi = {
  // Public embed surface -- no login. `token` here is the HOST-SIGNED JWT the
  // embedding application generated server-side (see EmbedDialog's sample
  // code); everything downstream (widget-data) uses the short-lived
  // `embed_session_token` this call returns instead.
  report: (token: string) =>
    api.get(`/embed/report`, { params: { token } }).then(r => r.data),
  widgetData: (sessionToken: string, widgetId: number) =>
    api.post(`/embed/widget-data/${widgetId}`, undefined,
      { headers: { Authorization: `Bearer ${sessionToken}` } }).then(r => r.data),
}

export const translationsApi = {
  list: (reportId: number) =>
    api.get<Record<string, Record<string, string>>>(`/reports/${reportId}/translations`).then(r => r.data),
  save: (reportId: number, locale: string, payload: Record<string, string>) =>
    api.put<Record<string, string>>(`/reports/${reportId}/translations/${locale}`, payload).then(r => r.data),
}

export interface PinnedTileInfo {
  id: number
  pin_type: 'widget' | 'insight'
  position: number | null
  size: 's' | 'm' | 'l'
  created_at: string
  dataset_id: number | null
  // Widget pins only:
  widget_id?: number
  widget_type?: string
  title?: string | null
  config?: Record<string, unknown>
  report_id?: number
  report_name?: string
  page_id?: number
  // Insight pins only:
  finding_key?: string
  dataset_name?: string
}

/** Personal live dashboard. A pin is a REFERENCE -- to a report widget, or to
 *  an insight finding (`kind|col|col`, columns sorted). Tiles and cards
 *  re-query as the viewer through the existing secured paths, so they show
 *  exactly what that person would see inside the report or dataset. */
export const pinsApi = {
  create: (body: { widget_id: number } | { dataset_id: number; finding_key: string }) =>
    api.post<{ id: number; already_pinned: boolean }>('/pins', body).then(r => r.data),
  list: () =>
    api.get<{ pins: PinnedTileInfo[] }>('/pins').then(r => r.data.pins),
  update: (pinId: number, body: { position?: number; size?: 's' | 'm' | 'l' }) =>
    api.patch<{ id: number; position: number | null; size: string }>(
      `/pins/${pinId}`, body).then(r => r.data),
  remove: (pinId: number) =>
    api.delete(`/pins/${pinId}`),
}

/** The identity apply_novelty and the pins table share: kind + sorted columns. */
export const findingKey = (f: { kind: string; columns: string[] }) =>
  [f.kind, ...[...f.columns].sort()].join('|')

/** Guarded LLM polish for one finding's sentence. Null = keep the template. */
export const narrateApi = {
  one: (finding: Record<string, unknown>) =>
    api.post<{ sentence: string | null }>('/analysis/narrate', { finding })
      .then(r => r.data.sentence),
}

const _insightsInFlight = new Map<number, Promise<unknown>>()

export const insightsApi = {
  /** `novelty` is present only when a previous scan exists and the caller is
   *  unrestricted -- "what changed since last time" over a shared baseline. */
  run: (dsId: number) =>
    api.post<{ findings: { kind: string; score: number; title: string; detail: string; columns: string[]
                           novelty?: 'new' | 'changed' | 'unchanged'
                           /** Tested findings only: the test, its population and effect (Phase 7.2). */
                           p_value?: number | null; p_adjusted?: number | null; significant?: boolean | null
                           evidence?: { test: string; n: number; effect: string } | null }[]
               narrative: string }>(`/datasets/${dsId}/insights`).then(r => r.data),
  /** Like run(), but N concurrent callers on one dataset share ONE request --
   *  every Dynamic Pin card on the dashboard evaluates through this, so five
   *  cards over the same dataset cost one scan, not five. */
  runShared(dsId: number) {
    const hit = _insightsInFlight.get(dsId)
    if (hit) return hit as ReturnType<typeof insightsApi.run>
    const p = insightsApi.run(dsId).finally(() => _insightsInFlight.delete(dsId))
    _insightsInFlight.set(dsId, p)
    return p
  },
}

export interface DifferenceTest {
  question: 'row counts' | 'typical row'; test: string; p_value: number; p_text: string; significant: boolean
  effect_name: string; effect_size: number; effect_label: string
  values: Record<string, number>; sentence: string
  /** The gap in the data's own units ("3,300 more rows (+15%)"), next to the
   *  unitless effect size (3.10). */
  business?: { absolute: number; percent: number | null; sentence: string }
}
export interface DifferenceCheck {
  population: { rows_a: number; rows_b: number; group_a: string; group_b: string
                dimension: string; measure: string | null; aggregation: string }
  tests: DifferenceTest[]; summary: string; caveats: string[]
  business?: { absolute: number; percent: number | null; sentence: string }
}

export interface AuthzCheck { resource: 'report' | 'dataset'; id: number; action: string; column?: string }
export interface AuthzDataRule { dataset_id: number; dataset_name: string; row_rule: string | null
  row_rule_for_you: string | null; hidden_columns: string[] }
export interface AuthzDecision extends AuthzCheck { allowed: boolean; reason: string; level?: string; sensitivity?: string | null
  /** `data_rules` only: the row and column rules on the report's data (3.13). */
  rules?: AuthzDataRule[] }

/** Batch "may I…?" with the rule that decided each (Phase 7.3), so the UI
 *  can grey out what the server would refuse AND say why. */
export const authzApi = {
  decisions: (checks: AuthzCheck[]) =>
    api.post<{ decisions: AuthzDecision[] }>('/authz/decisions', { checks }).then(r => r.data.decisions),
}

export interface DatasetSensitivity {
  label: string | null; effective: string | null; reasons: string[]; options: string[]; redacted_on_share: string[]
}
export const sensitivityApi = {
  get: (dsId: number) => api.get<DatasetSensitivity>(`/datasets/${dsId}/sensitivity`).then(r => r.data),
  set: (dsId: number, label: string) => api.put<DatasetSensitivity>(`/datasets/${dsId}/sensitivity`, { label }).then(r => r.data),
}

export interface PerfRow { widget_id: number; title: string; page: string; widget_type: string; dataset_id: number
  ms: number; rows: number | null; error: string | null; advice: string[] }
export interface PerfEvaluation { widgets: PerfRow[]; total_ms: number; slow_ms: number; slow: number
  history: Record<string, { runs: number; median_ms: number | null; p95_ms: number | null; cache_hit_share: number | null }>
  measured_at: string }

/** Report quality as CI (Phase 7.4). */
export const reviewApi = {
  review: (reportId: number) =>
    api.get<{ findings: { message: string; widget_id: number; page_id: number; category: string }[]; publish_gate: boolean }>(
      `/reports/${reportId}/review`).then(r => r.data),
  evaluate: (reportId: number) => api.post<PerfEvaluation>(`/reports/${reportId}/evaluate-performance`).then(r => r.data),
  settings: () => api.get<{ publish_gate: boolean }>('/review-settings').then(r => r.data),
  setGate: (on: boolean) => api.put<{ publish_gate: boolean }>('/review-settings', { publish_gate: on }).then(r => r.data),
}

export const differenceApi = {
  /** "Is this difference real?" over the rows the chart drew from. */
  check: (dsId: number, body: { dimension: string; groups: string[]; measure?: string | null
                                aggregation?: string; granularity?: string | null; filters?: unknown[] }) =>
    api.post<DifferenceCheck>(`/datasets/${dsId}/difference-check`, body).then(r => r.data),
}

export const explainApi = {
  /** `filters`: the widget's own and the page's, so a reader's "Explain
   *  this" is about the rows the widget shows. */
  explain: (dsId: number, column: string, filters?: unknown[]) =>
    api.post(`/datasets/${dsId}/explain`, filters?.length ? { filters } : null, { params: { column } }).then(r => r.data),
  goalSeek: (dsId: number, xColumn: string, yColumn: string, targetY: number,
             xMin?: number, xMax?: number) =>
    api.post<{ required_x: number; slope: number; intercept: number; r2: number | null
               x_observed_min: number; x_observed_max: number; within_observed_range: boolean
               within_bounds?: boolean; bound_x?: number; achievable_y?: number }>(
      `/datasets/${dsId}/goal-seek`, null,
      { params: { x_column: xColumn, y_column: yColumn, target_y: targetY,
                  ...(xMin != null ? { x_min: xMin } : {}), ...(xMax != null ? { x_max: xMax } : {}) } }).then(r => r.data),
}

export const queryBuilderApi = {
  functions: (dsId: number) =>
    api.get<{ name: string; returns: string }[]>(`/data-sources/${dsId}/functions`).then(r => r.data),
  columns: (dsId: number, table: string) =>
    api.get<{ name: string; type: string }[]>(`/data-sources/${dsId}/tables/${encodeURIComponent(table)}/columns`).then(r => r.data),
  compile: (dsId: number, model: Record<string, unknown>, mode: 'import' | 'directquery' = 'import') =>
    api.post<{ sql: string }>(`/data-sources/${dsId}/build-query`, model, { params: { mode } }).then(r => r.data),
  preview: (dsId: number, model: Record<string, unknown>) =>
    api.post<{ columns: string[]; rows: unknown[][]; sql: string }>(
      `/data-sources/${dsId}/build-query/preview`, model).then(r => r.data),
}

export const dataViewsApi = {
  list: () => api.get<{ id: number; name: string; pieces: string[]; is_default?: boolean }[]>('/datasets/data-views/list').then(r => r.data),
  save: (dsId: number, name: string) =>
    api.post<{ id: number; name: string }>(`/datasets/${dsId}/save-data-view`, null, { params: { name } }).then(r => r.data),
  apply: (dsId: number, viewId: number) =>
    api.post<{ applied: Record<string, number>; skipped: string[] }>(
      `/datasets/${dsId}/apply-data-view`, null, { params: { view_id: viewId } }).then(r => r.data),
  delete: (viewId: number) => api.delete(`/datasets/data-views/${viewId}`),
  /** SAS's admin default: the view applied to every dataset uploaded from now
   *  on. Admin-only server-side; at most one per org. */
  setDefault: (viewId: number, isDefault: boolean) =>
    api.patch<{ id: number; name: string; is_default: boolean }>(
      `/datasets/data-views/${viewId}/default`, { default: isDefault }).then(r => r.data),
}

export const columnMetaApi = {
  get: (dsId: number) =>
    api.get<Record<string, ColumnMeta>>(`/datasets/${dsId}/column-meta`).then(r => r.data),
  /** Replaces the whole map — that is what makes a bulk edit one request. */
  set: (dsId: number, meta: Record<string, ColumnMeta>) =>
    api.put<Record<string, ColumnMeta>>(`/datasets/${dsId}/column-meta`, { meta }).then(r => r.data),
}

export interface MeasureDef {
  name: string
  expression: string
  default_aggregation?: string
  format?: CalcColumnFormat
  /** E05 metric versions, kept by the server: a changed formula is a new
   *  version and the earlier ones are listed here, oldest first. */
  version?: number
  history?: MeasureVersion[]
  saved_at?: string | null
  saved_by?: string | null
}

export interface MeasureVersion {
  version: number
  expression: string
  default_aggregation?: string
  saved_at?: string | null
  saved_by?: string | null
}

export interface MeasurePreviewResult {
  ok: boolean
  dtype?: string | null
  sample?: { group: string | null; value: unknown }[]
  error?: string | null
}

export const measuresApi = {
  list:    (dsId: number)                    => api.get<MeasureDef[]>(`/datasets/${dsId}/measures`).then(r => r.data),
  save:    (dsId: number, m: MeasureDef)     => api.post<MeasureDef[]>(`/datasets/${dsId}/measures`, m).then(r => r.data),
  // `force`: delete even though something names it (the server answers 409 otherwise).
  delete:  (dsId: number, name: string, force?: boolean) => api.delete<MeasureDef[]>(`/datasets/${dsId}/measures/${encodeURIComponent(name)}`, force ? { params: { force: true } } : undefined).then(r => r.data),
  /** Bring an earlier formula back -- as a NEW version; history is never rewritten. */
  restore: (dsId: number, name: string, version: number) =>
    api.post<MeasureDef[]>(`/datasets/${dsId}/measures/${encodeURIComponent(name)}/restore`, { version }).then(r => r.data),
  preview: (dsId: number, body: { expression: string; group_by?: string }) =>
    api.post<MeasurePreviewResult>(`/datasets/${dsId}/measures/preview`, body).then(r => r.data),
}

export interface ReportParameterDef {
  id?: number
  name: string
  param_type: 'number' | 'text' | 'date' | 'expression'
  label?: string | null
  default_value?: string | null
  options?: string[]
}

export const parametersApi = {
  list: (reportId: number) =>
    api.get<ReportParameterDef[]>(`/reports/${reportId}/parameters`).then(r => r.data),
  save: (reportId: number, defs: ReportParameterDef[]) =>
    api.put<ReportParameterDef[]>(`/reports/${reportId}/parameters`, defs).then(r => r.data),
}

export const reportCapabilityApi = {
  get: (reportId: number) =>
    api.get<{ levels: Record<string, string> }>(`/reports/${reportId}/capabilities`).then(r => r.data.levels),
  set: (reportId: number, levels: Record<number, string>) =>
    api.put<{ levels: Record<string, string> }>(`/reports/${reportId}/capabilities`, { levels }).then(r => r.data.levels),
}

export const pageVisibilityApi = {
  roles: () => api.get<{ id: number; name: string }[]>('/reports/roles/lite').then(r => r.data),
  get:   (reportId: number, pageId: number) =>
    api.get<{ role_ids: number[] }>(`/reports/${reportId}/pages/${pageId}/visibility`).then(r => r.data),
  set:   (reportId: number, pageId: number, roleIds: number[]) =>
    api.put(`/reports/${reportId}/pages/${pageId}/visibility`, { role_ids: roleIds }).then(r => r.data),
}

export interface ReportScheduleRow {
  id: number; interval_minutes: number; recipients: string[]
  calendar?: { kind: 'daily' | 'weekly' | 'monthly'; hour: number; minute: number; weekday?: number; monthday?: number } | null
  format?: 'xlsx' | 'pdf'
  /** Each recipient gets the report built as THEM (their own row rules). */
  per_recipient?: boolean
  /** Nothing is sent when the data is unchanged since the last delivery. */
  only_if_changed?: boolean
  subject?: string | null; last_run_at?: string | null; last_status?: string | null
  timezone?: string | null
}

export interface DeliveryRow {
  id: number; schedule_id: number | null; kind: 'schedule' | 'alert' | 'manual'
  status: 'ok' | 'error'; error: string | null; artifact_kind: 'pdf' | 'csv' | 'xlsx' | 'none'
  duration_ms: number | null; created_at: string
  /** 5.18: what the row is about -- the alert or report, who it went to, the file. */
  subject?: string | null; recipients?: string | null; file_name?: string | null
}

// Common IANA zones for the free-text timezone input's datalist -- server-side
// validation (422 on unknown) is authoritative, this just speeds up typing.
export const COMMON_TIMEZONES = [
  'UTC', 'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'America/Sao_Paulo', 'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Moscow',
  'Africa/Cairo', 'Asia/Riyadh', 'Asia/Dubai', 'Asia/Kolkata', 'Asia/Shanghai',
  'Asia/Tokyo', 'Asia/Singapore', 'Australia/Sydney', 'Pacific/Auckland',
]

export type ExportPolicy = boolean | { formats?: string[]; auto_private?: boolean }

export const exportPolicyApi = {
  get: (dsId: number) =>
    // inherited_from: the SOURCE dataset id when this policy is resolved
    // through it (an aggregate always resolves through its source), null
    // when `dsId` governs its own policy. Not yet consumed anywhere -- see
    // the spec's follow-up list, item 14 (AdminExportPolicy should render an
    // aggregate's policy as inherited and disable the toggle).
    api.get<{ export_policy: ExportPolicy; has_security_rules: boolean; inherited_from?: number | null }>(
      `/datasets/${dsId}/export-policy`).then(r => r.data),
  setAll: (dsId: number, disabled: boolean) =>
    api.post(`/datasets/${dsId}/export-policy?disabled=${disabled}`).then(r => r.data),
  setGranular: (dsId: number, formats: string[], autoPrivate: boolean) =>
    api.post<{ export_policy: ExportPolicy }>(`/datasets/${dsId}/export-policy`,
      { formats, auto_private: autoPrivate }).then(r => r.data),
}

export interface AdminAuditRow {
  id: number
  actor_email: string | null
  action: string
  target: string | null
  detail: string | null
  created_at: string
}

export const adminAuditApi = {
  list: (params?: { action?: string; q?: string; limit?: number }) =>
    api.get<AdminAuditRow[]>('/admin/admin-audit', { params }).then(r => r.data),
}

/** The org's general activity log (`audit_log`) -- distinct from the S5
 * admin-mutation trail above: this one records ordinary actions (logins,
 * uploads, report edits), that one records security-relevant admin writes. */
export interface ActivityRow {
  id: number
  user_email: string | null
  action: string
  entity: string | null
  entity_id: number | null
  detail: string | null
  created_at: string
}

export interface MonitoringJobRow {
  kind: 'dataset_refresh' | 'dataflow' | 'report_schedule' | 'alert'
  id: number
  name: string
  interval_minutes: number
  /** A calendar report schedule ("weekly on Monday at 09:00"). */
  calendar?: { kind: 'daily' | 'weekly' | 'monthly'; hour: number; minute: number; weekday?: number; monthday?: number } | null
  timezone?: string | null
  last_run_at: string | null
  status: string | null
  error: string | null
  report_id?: number
  dataset_id?: number
  /** A failing dataset refresh or dataflow: when it is next tried (backoff). */
  next_retry_at?: string | null
  /** A dataset: when its data last actually changed (a failed run leaves it). */
  last_refreshed_at?: string | null
}

/** One dataset refresh or dataflow run, scheduled or manual. */
export interface RefreshRunRow {
  id: number
  kind: 'dataset' | 'dataflow'
  item_id: number
  /** null when the dataset or dataflow has since been deleted. */
  name: string | null
  trigger: 'schedule' | 'manual'
  status: 'running' | 'ok' | 'failed' | 'skipped' | 'blocked'
  started_at: string | null
  finished_at: string | null
  rows: number | null
  duration_ms: number | null
  error: string | null
  error_code: string | null
}

export interface MonitoringDeliveryRow extends DeliveryRow {
  report_id: number | null
  report_name: string | null
}

export const monitoringApi = {
  jobs: () => api.get<MonitoringJobRow[]>('/admin/monitoring/jobs').then(r => r.data),
  refreshRuns: (params: { status?: string; kind?: string; item_id?: number; limit?: number } = {}) =>
    api.get<RefreshRunRow[]>('/admin/monitoring/refresh-runs', { params }).then(r => r.data),
  deliveries: (limit = 200) =>
    api.get<MonitoringDeliveryRow[]>('/admin/monitoring/deliveries', { params: { limit } }).then(r => r.data),
  activity: (limit = 200) =>
    api.get<ActivityRow[]>('/admin/audit-log', { params: { limit } }).then(r => r.data),
}

/** One node of the organization's own chart (Country → Region → Branch → …).
 *  Row access flows DOWN from wherever a user is placed. */
export interface OrgUnit {
  id: number
  parent_id: number | null
  name: string
  level_name: string | null
  /** The value this unit takes in the DATA -- what `MYSCOPE()` compares against. */
  match_value: string
  position: number
  child_count: number
}

export interface UserOrgUnitRow {
  id: number
  org_unit_id: number
  name: string
  level_name: string | null
  match_value: string
}

export const orgUnitsApi = {
  list: () => api.get<OrgUnit[]>('/admin/org-units').then(r => r.data),
  create: (body: { name: string; parent_id?: number | null; level_name?: string; match_value?: string }) =>
    api.post<OrgUnit>('/admin/org-units', body).then(r => r.data),
  update: (id: number, body: Partial<{ name: string; parent_id: number | null; level_name: string; match_value: string; position: number }>) =>
    api.patch<OrgUnit>(`/admin/org-units/${id}`, body).then(r => r.data),
  remove: (id: number) => api.delete(`/admin/org-units/${id}`).then(() => undefined),
  forUser: (userId: number) =>
    api.get<UserOrgUnitRow[]>(`/admin/users/${userId}/org-units`).then(r => r.data),
  setForUser: (userId: number, orgUnitIds: number[]) =>
    api.put<{ org_unit_ids: number[] }>(`/admin/users/${userId}/org-units`,
      { org_unit_ids: orgUnitIds }).then(r => r.data),
  /** The CALLER's own scope -- open to any signed-in user, which is why it
   *  lives under /auth rather than /admin. */
  myScope: () =>
    api.get<{ placed: boolean; values: string[]; is_org_admin: boolean }>(
      '/auth/my-scope').then(r => r.data),
}

export interface ColumnSecurityRuleRow {
  id: number
  role_id: number
  dataset_id: number
  denied_columns: string[]
}

export const columnSecurityApi = {
  list: () => api.get<ColumnSecurityRuleRow[]>('/admin/column-security-rules').then(r => r.data),
  create: (body: { role_id: number; dataset_id: number; denied_columns: string[] }) =>
    api.post<{ id: number }>('/admin/column-security-rules', body).then(r => r.data),
  remove: (id: number) =>
    api.delete(`/admin/column-security-rules/${id}`).then(() => undefined),
}

export interface WidgetSuggestion {
  widget_type: string; title: string; reason: string
  config: Record<string, unknown>; score: number; kind: string; aligned: boolean
  /** What the chart shows, read from its drawn result on every row. */
  takeaway?: string
  takeaway_i18n?: SaidI18n | null
}

export const suggestApi = {
  forReport: (reportId: number) =>
    api.post<{ suggestions: WidgetSuggestion[] }>(`/reports/${reportId}/suggest-widgets`)
      .then(r => r.data.suggestions),
  /** Build a whole page from the insights engine: summary KPIs, then the
   *  strongest findings as charts sized by rank, then detail and the
   *  narrative. Returns the new page's id. */
  autoCompose: (reportId: number) =>
    api.post<{ page_id: number; name: string; widget_count: number }>(
      `/reports/${reportId}/auto-compose`).then(r => r.data),
}

export const schedulesApi = {
  list:   (reportId: number) => api.get<ReportScheduleRow[]>(`/reports/${reportId}/schedules`).then(r => r.data),
  create: (reportId: number, body: { interval_minutes?: number; recipients: string[]; subject?: string;
                                     format?: 'xlsx' | 'pdf'; timezone?: string;
                                     per_recipient?: boolean; only_if_changed?: boolean;
                                     calendar?: { kind: 'daily' | 'weekly' | 'monthly'; hour: number; minute: number; weekday?: number; monthday?: number } }) =>
    api.post(`/reports/${reportId}/schedules`, body).then(r => r.data),
  delete: (reportId: number, id: number) => api.delete(`/reports/${reportId}/schedules/${id}`),
  runNow: (reportId: number, id: number) =>
    api.post<{ last_status: string }>(`/reports/${reportId}/schedules/${id}/run-now`).then(r => r.data),
}

export const deliveriesApi = {
  list: (reportId: number) => api.get<DeliveryRow[]>(`/reports/${reportId}/deliveries`).then(r => r.data),
}

export const pageTemplatesApi = {
  builtins: () => api.get<{ key: string; name: string; widgets: number }[]>('/reports/templates/builtin').then(r => r.data),
  list:     () => api.get<{ id: number; name: string; widgets: number }[]>('/reports/templates/page').then(r => r.data),
  saveFrom: (reportId: number, pageId: number, name: string) =>
    api.post(`/reports/${reportId}/pages/${pageId}/save-as-template`, { name }).then(r => r.data),
  addFrom:  (reportId: number, source: { template_id?: number; builtin?: string; source_report_id?: number; source_page_id?: number }) =>
    api.post<{ page_id: number; widgets: number }>(`/reports/${reportId}/pages/from-template`, source).then(r => r.data),
  /** A template is a stamp, not a link: pages already built from it are
   *  untouched. Without this a name typed wrong was permanent. */
  delete:   (templateId: number) => api.delete(`/reports/templates/page/${templateId}`).then(() => undefined),
}

// ── Widget-data fetch discipline ─────────────────────────────────────────────
// Applied ONLY to widgetDataApi.query. Three mechanisms:
//  * in-flight dedup — identical concurrent requests share one promise (a text
//    widget's several {{agg}} placeholders, page-flip races)
//  * a 30s TTL cache — Report→Data→Report and page flips re-serve from memory;
//    30s stays well under the 60s scheduler tick, and `fresh: true` bypasses it
//    for the paths that promise liveness (auto-reload widgets, kiosk ticks)
//  * a concurrency gate — at most 6 POSTs in flight, so a 28-widget page is a
//    queue, not a stampede
// The cache key is the exact request body. RLS and column masks are resolved
// server-side per token, and this cache lives in one tab of one session, so
// the body IS the full identity of the result.
export interface ReconcileMapping { keys: [string, string][]; values: [string, string][] }
export interface ReconcileResult {
  mapping: ReconcileMapping
  columns: { widget: string[]; file: string[] }
  counts: { match: number; mismatch: number; missing_in_widget: number; missing_in_file: number }
  rows: { key: Record<string, unknown>; status: 'match' | 'mismatch' | 'missing_in_widget' | 'missing_in_file'
          values: { column: string; expected: unknown; actual: unknown; difference: number | null; ok: boolean }[] }[]
  totals: { column: string; expected: number; actual: number; difference: number }[]
  duplicate_keys: { widget: number; file: number }
  reconciled: boolean
  file: string
  /** The migration item the result was kept on, when one was named. */
  recorded_on?: number | null
}

export const WIDGET_DATA_TTL_MS = 30_000
export const WIDGET_DATA_MAX_CONCURRENT = 6
const WD_CACHE_MAX = 100
const wdCache = new Map<string, { at: number; data: unknown }>()
const wdInflight = new Map<string, WdEntry>()

let wdActive = 0
const wdQueue: (() => void)[] = []
/** A queued request whose signal aborts leaves the queue and is never sent. */
const wdAcquire = (signal: AbortSignal) => new Promise<void>((resolve, reject) => {
  if (signal.aborted) { reject(canceledRequest()); return }
  if (wdActive < WIDGET_DATA_MAX_CONCURRENT) { wdActive += 1; resolve(); return }
  const turn = () => { signal.removeEventListener('abort', leave); wdActive += 1; resolve() }
  const leave = () => {
    const i = wdQueue.indexOf(turn)
    if (i >= 0) wdQueue.splice(i, 1)
    reject(canceledRequest())
  }
  signal.addEventListener('abort', leave, { once: true })
  wdQueue.push(turn)
})
const wdRelease = () => {
  wdActive -= 1
  const next = wdQueue.shift()
  if (next) next()
}

/** One POST, shared by every caller that asked for the same body at once.
 *  It is aborted only when every caller has let go: a caller without a
 *  signal holds it for good. */
interface WdEntry { promise: Promise<unknown>; controller: AbortController; holders: number; pinned: boolean; settled: boolean }

/** Join a shared request. Letting go (the signal aborting) rejects this
 *  caller at once; the POST itself is aborted when the last holder lets go
 *  -- still queued, it is never sent; in flight, the browser closes it and
 *  the server drops it if it has not started (E14). */
function holdWd(entry: WdEntry, key: string, signal?: AbortSignal): Promise<any> {
  if (!signal) { entry.pinned = true; return entry.promise }
  if (signal.aborted) return Promise.reject(canceledRequest())
  entry.holders += 1
  return new Promise((resolve, reject) => {
    const letGo = () => {
      reject(canceledRequest())
      entry.holders -= 1
      if (entry.holders <= 0 && !entry.pinned && !entry.settled) {
        if (wdInflight.get(key) === entry) wdInflight.delete(key)
        entry.controller.abort()
      }
    }
    signal.addEventListener('abort', letGo, { once: true })
    entry.promise.then(
      v => { signal.removeEventListener('abort', letGo); resolve(v) },
      e => { signal.removeEventListener('abort', letGo); reject(e) })
  })
}

/** Test hook + logout hygiene: drop every cached widget result. */
export const clearWidgetDataClientCache = () => { wdCache.clear() }

export const widgetDataApi = {
  query: (dsId: number, config: Record<string, unknown>, calculatedColumns: CalcColumn[] = [], widgetType = 'bar',
          opts?: { reportId?: number; parameters?: Record<string, unknown>; fresh?: boolean; signal?: AbortSignal }) => {
    const body = {
      config, calculated_columns: calculatedColumns, widget_type: widgetType,
      // Values travel raw; the server substitutes them against the DECLARED types.
      // Building expressions out of parameter values client-side would reopen the
      // injection door the server-side encoding closes.
      report_id: opts?.reportId, parameters: opts?.parameters ?? {},
    }
    const key = `${dsId}|${JSON.stringify(body)}`

    if (!opts?.fresh) {
      const hit = wdCache.get(key)
      if (hit && Date.now() - hit.at < WIDGET_DATA_TTL_MS) return Promise.resolve(hit.data)
      const inflight = wdInflight.get(key)
      if (inflight) return holdWd(inflight, key, opts?.signal)
    }

    const controller = new AbortController()
    const entry: WdEntry = { promise: Promise.resolve(), controller, holders: 0, pinned: false, settled: false }
    entry.promise = (async () => {
      await wdAcquire(controller.signal)
      try {
        const r = await api.post(`/datasets/${dsId}/widget-data`, body, { signal: controller.signal })
        wdCache.set(key, { at: Date.now(), data: r.data })
        while (wdCache.size > WD_CACHE_MAX) {
          const oldest = wdCache.keys().next().value as string | undefined
          if (oldest === undefined) break
          wdCache.delete(oldest)
        }
        return r.data
      } finally {
        wdRelease()
      }
    })().finally(() => {
      entry.settled = true
      if (wdInflight.get(key) === entry) wdInflight.delete(key)
    })
    wdInflight.set(key, entry)
    return holdWd(entry, key, opts?.signal)
  },

  /** E17: compare the widget with the old report's export of the same table
   *  (CSV or Excel). `mapping` pairs widget columns with file columns; left
   *  out, the server pairs them by name. */
  reconcile: (dsId: number, body: { config: Record<string, unknown>; widget_type: string
                                    calculated_columns?: CalcColumn[]; report_id?: number
                                    parameters?: Record<string, unknown> },
              file: File, mapping?: ReconcileMapping,
              record?: { itemId: number; widgetKey: string; widgetTitle: string }) => {
    const form = new FormData()
    form.append('widget', JSON.stringify(body))
    if (mapping) form.append('mapping', JSON.stringify(mapping))
    if (record) {
      form.append('migration_item', String(record.itemId))
      form.append('widget_key', record.widgetKey)
      form.append('widget_title', record.widgetTitle)
    }
    form.append('file', file)
    return api.post<ReconcileResult>(`/datasets/${dsId}/widget-data/reconcile`, form).then(r => r.data)
  },

  /** Downloads the widget's data. Goes through the same endpoint family as `query`,
   *  so the file contains exactly what the widget shows -- including row-level
   *  security, which is applied server-side and must never be re-derived here. */
  export: async (dsId: number, config: Record<string, unknown>, widgetType: string,
                 format: 'csv' | 'xlsx', calculatedColumns: CalcColumn[] = []) => {
    const r = await api.post(
      `/datasets/${dsId}/widget-data/export?format=${format}`,
      { config, calculated_columns: calculatedColumns, widget_type: widgetType },
      { responseType: 'blob' },
    )
    // The filename is the server's to choose: it has already sanitised it for the
    // Content-Disposition header, and re-deriving it from the widget title here would
    // reintroduce the untrusted string this avoided.
    const disposition = String(r.headers['content-disposition'] ?? '')
    const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `widget.${format}`
    const url = URL.createObjectURL(r.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = name
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
}

export interface DataSource {
  id: number
  name: string
  type: string
  config: Record<string, unknown>
  created_at: string
  custom_connector_id?: number | null
  custom_connector_label?: string | null
  /** Sensitivity label for everything read from this connection; every
   *  dataset built from it inherits it as a floor. */
  sensitivity?: string | null
  /** Transient, on the response to a CREATE only: the metadata sync that
   *  started for this connection, so the client can go straight to the review
   *  page with progress already running. Null when nothing was started. */
  sync_run_id?: number | null
}

export interface CustomConnector {
  id: number
  key: string
  label: string
  base_type: string
  base_config: Record<string, unknown>
  locked_fields: string[]
  created_at: string
}

export interface ConnectorConfigField {
  name: string; label: string; kind: 'text' | 'password' | 'number' | 'select'
  required: boolean; default: unknown; placeholder: string; options: string[]
  secret: boolean; show_if: [string, unknown] | null
}
export interface ConnectorSpec {
  key: string; label: string; icon: string; category: string
  default_port: number | null; driver_installed: boolean; supports_directquery: boolean
  config_fields: ConnectorConfigField[]
  is_custom?: boolean
  base_type?: string
  custom_connector_id?: number
}

/** What the platform has watched itself filter on, against the customer's
 *  own indexes. Recommendations only -- nothing creates an index anywhere. */
export interface IndexAdviceColumn {
  column: string; runs: number; avg_ms: number; score: number
  indexed: boolean | null; recommended: boolean; statement: string | null
}
export interface IndexAdvice {
  tables: { table: string; columns: IndexAdviceColumn[] }[]
  min_runs: number; observed_days: number; runs_considered: number
  /** 'checked' when pg_indexes was read; 'unavailable' when the source could not be reached. */
  /** 'unsupported': not a Postgres source, so no index check and no statement. */
  index_check: 'checked' | 'unavailable' | 'unsupported'
}

/** A durable background job (backend services/jobs.py). `state` is the
 *  truth; `cancel_requested` on a running job means "stopping". */
export type JobState = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'
export interface Job {
  id: number
  kind: string
  state: JobState
  subject: string | null
  progress: { stage?: string; rows?: number; resumed?: boolean } | null
  result: { dataset_id?: number; dataset_name?: string; row_count?: number;
            col_count?: number; replaced?: boolean
            /** A refresh: what ran, and anything it fell back to. */
            mode?: 'full' | 'incremental'; rows_added?: number; warning?: string | null
            /** A refresh refused by a schema break (error_code `schema_break`). */
            missing?: string[]; suggestions?: Record<string, string[]>; available?: string[]
            dependents?: Record<string, { kind: string; label: string }[]>
            /** Phase 3: a refresh refused by a blocking data check -- every check's result. */
            checks?: CheckResult[] } | null
  error: string | null
  error_code: string | null
  attempt: number
  max_attempts: number
  cancel_requested: boolean
  retry_of: number | null
  created_by: number | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  updated_at: string | null
}

export const isJobActive = (j: Pick<Job, 'state'>) => j.state === 'queued' || j.state === 'running'

/** E12: an automated analysis run (routers/automation.py). */
export type AutomationStatus = 'pending' | 'running' | 'failed' | 'needs_review' | 'done' | 'cancelled'
export interface AutomationStepRow {
  name: string
  label: string
  order: number
  status: 'pending' | 'running' | 'ok' | 'failed'
  attempts: number
  error: string | null
  next_attempt_at: string | null
  started_at: string | null
  finished_at: string | null
}
export interface AutomationRunRow {
  id: number
  status: AutomationStatus
  trigger: string
  created_by: number | null
  dataset: { id: number; name: string } | null
  created_at: string | null
  finished_at: string | null
  error: string | null
  summary: string | null
  result_report: { id: number; name: string | null } | null
  steps: AutomationStepRow[]
  proposal_path?: string | null
  widgets_accepted?: number | null
  widgets_rejected?: number | null
  rejection_reasons?: { title?: string; widget_type?: string; reason?: string }[]
}
export const isAutomationActive = (r: Pick<AutomationRunRow, 'status'>) =>
  r.status === 'pending' || r.status === 'running' || r.status === 'failed'

export const automationApi = {
  list: (params: { dataset_id?: number } = {}) =>
    api.get<AutomationRunRow[]>('/automation/runs', { params }).then(r => r.data),
  get: (id: number) => api.get<AutomationRunRow>(`/automation/runs/${id}`).then(r => r.data),
  start: (datasetId: number) =>
    api.post<AutomationRunRow>('/automation/runs', { dataset_id: datasetId }).then(r => r.data),
  approve: (id: number) => api.post<AutomationRunRow>(`/automation/runs/${id}/approve`).then(r => r.data),
  reject: (id: number, reason?: string) =>
    api.post<AutomationRunRow>(`/automation/runs/${id}/reject`, { reason: reason || null }).then(r => r.data),
  cancel: (id: number) => api.post<AutomationRunRow>(`/automation/runs/${id}/cancel`).then(r => r.data),
  retry: (id: number) => api.post<AutomationRunRow>(`/automation/runs/${id}/retry`).then(r => r.data),
}

export const jobsApi = {
  list: (params: { kind?: string; state?: JobState; active?: boolean; limit?: number } = {}) =>
    api.get<Job[]>('/jobs', { params }).then(r => r.data),
  get: (id: number) => api.get<Job>(`/jobs/${id}`).then(r => r.data),
  cancel: (id: number) => api.post<Job>(`/jobs/${id}/cancel`).then(r => r.data),
  /** A NEW job with the same inputs; the failed one stays as history. */
  retry: (id: number) => api.post<Job>(`/jobs/${id}/retry`).then(r => r.data),
}

export interface SavedQuery { id: number; name: string | null; sql: string; created_at: string | null }

export const dataSourcesApi = {
  indexAdvice: (id: number, days = 30) =>
    api.get<IndexAdvice>(`/data-sources/${id}/index-advice`, { params: { days } }).then(r => r.data),
  connectors: () => api.get<ConnectorSpec[]>('/data-sources/connectors').then(r => r.data),
  list:    ()                                              => api.get<DataSource[]>('/data-sources').then(r => r.data),
  create:  (body: { name: string; type: string; config: Record<string, unknown>; custom_connector_id?: number | null; sensitivity?: string | null }) =>
    api.post<DataSource>('/data-sources', body).then(r => r.data),
  update:  (id: number, body: Partial<{ name: string; type: string; config: Record<string, unknown>; custom_connector_id: number | null; sensitivity: string }>) =>
    api.put<DataSource>(`/data-sources/${id}`, body).then(r => r.data),
  delete:  (id: number)                                   => api.delete(`/data-sources/${id}`),
  test:    (id: number)                                   => api.post<{ ok: boolean; error?: string }>(`/data-sources/${id}/test`).then(r => r.data),
  /** Try settings BEFORE saving them. `source_id` lets an edit form send a
   *  secret back redacted and have the stored one used. Nothing is written. */
  testSettings: (body: { type: string; config: Record<string, unknown>; custom_connector_id?: number | null; source_id?: number }) =>
    api.post<{ ok: boolean; error?: string }>('/data-sources/test', body).then(r => r.data),
  schema:  (id: number)                                   => api.get<{ tables: { name: string; kind: string }[] }>(`/data-sources/${id}/schema`).then(r => r.data),
  preview: (id: number, table?: string, query?: string, limit = 200) =>
    api.post<{ columns: string[]; rows: unknown[][]; total: number }>(`/data-sources/${id}/preview`, { table, query, limit }).then(r => r.data),
  /** 4.2: named queries for this connection and the caller's last runs. */
  queries: (id: number) =>
    api.get<{ saved: SavedQuery[]; history: SavedQuery[] }>(`/data-sources/${id}/queries`).then(r => r.data),
  saveQuery: (id: number, name: string, sql: string) =>
    api.post<SavedQuery>(`/data-sources/${id}/queries`, { name, sql }).then(r => r.data),
  deleteQuery: (id: number, queryId: number) =>
    api.delete(`/data-sources/${id}/queries/${queryId}`),
  /** 4.3: the rows of a table or query as CSV (refused on a Restricted connection). */
  downloadCsv: async (id: number, table?: string, query?: string) => {
    const r = await api.post(`/data-sources/${id}/query-csv`, { table, query }, { responseType: 'blob' })
    const url = URL.createObjectURL(r.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${table || 'query'}.csv`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    return { rows: Number(r.headers?.['x-rows'] ?? 0), truncated: r.headers?.['x-truncated'] === '1' }
  },
  import:  (id: number, dataset_name: string, table?: string, query?: string, mode: 'import' | 'directquery' = 'import',
            query_model?: Record<string, unknown>, dataset_id?: number) =>
    api.post<{ id: number; name: string; row_count: number; col_count: number; mode: string }>(
      `/data-sources/${id}/import`, { dataset_name, table, query, mode, query_model, dataset_id }).then(r => r.data),
  /** Queue an import as a durable job (E07) and return at once. The job runs
   *  in the server's worker: closing the tab loses nothing, and it can be
   *  cancelled or retried. `idempotencyKey` makes a double-click or a resent
   *  request answer with the job it already made. Poll `jobsApi.get`. */
  queueImport: (id: number, body: { dataset_name: string; table?: string; query?: string;
                query_model?: Record<string, unknown>; dataset_id?: number },
                idempotencyKey?: string) =>
    api.post<Job>(`/data-sources/${id}/import-jobs`, { ...body, mode: 'import' },
      idempotencyKey ? { headers: { 'Idempotency-Key': idempotencyKey } } : undefined).then(r => r.data),
  /** Propose a dashboard for a kind of person, from this connection's catalog --
   *  the step BEFORE a dataset exists. The backend has answered this since it
   *  shipped and nothing ever called it. Slow by nature (the model designs, then
   *  every proposed query is executed against the source before it is offered),
   *  so the timeout matches suggestDashboards'. */
  suggestDashboard: (id: number, body: { for_role: string; goal?: string }) =>
    api.post<{ ok: boolean; reason: string; suggestion: SourceDashboardSuggestion | null }>(
      `/data-sources/${id}/suggest-dashboard`, body, { timeout: 300000 }).then(r => r.data),
  /** Datasets already built from this connection that cover these columns.
   *  Advisory: it never blocks a create, it tells the person what they have. */
  similarDatasets: (id: number, body: { columns: string[]; table?: string; query?: string }) =>
    api.post<{ matches: SimilarDataset[] }>(
      `/data-sources/${id}/similar-datasets`, body).then(r => r.data),
}

/** One dashboard proposed from a CONNECTION's catalog: the query that builds
 *  its data and the tiles to put over it. Mirrors the backend's
 *  `suggest_dashboard.SUGGESTION_SCHEMA`, and deliberately the same shape the
 *  chat's `DashboardProposal` already carries so one component renders both. */
export interface SourceDashboardSuggestion {
  title: string
  sql: string
  widgets: {
    widget_type: string
    title: string
    dimension: string
    measure: string
    aggregation: string
    note?: string
    limit?: number
    sort?: string
    sort_by?: string
    dimension_granularity?: string
    running?: string
  }[]
}

/** A dataset that already covers much of what is about to be built.
 *  `coverage` is the share of the PROPOSED columns it has; `by_name` marks the
 *  weaker match made on column names because one side had no provenance. */
export interface SimilarDataset {
  dataset_id: number
  name: string
  mode: string
  row_count: number
  overlap: number
  coverage: number
  matched_columns: string[]
  by_name: boolean
}

export const customConnectorsApi = {
  list:   () => api.get<CustomConnector[]>('/custom-connectors').then(r => r.data),
  create: (body: { key: string; label: string; base_type: string; base_config: Record<string, unknown>; locked_fields: string[] }) =>
    api.post<CustomConnector>('/custom-connectors', body).then(r => r.data),
  update: (id: number, body: Partial<{ key: string; label: string; base_type: string; base_config: Record<string, unknown>; locked_fields: string[] }>) =>
    api.put<CustomConnector>(`/custom-connectors/${id}`, body).then(r => r.data),
  delete: (id: number) => api.delete(`/custom-connectors/${id}`),
}

export interface Organization {
  id: number
  name: string
}

export interface Role {
  id: number
  name: string
  is_org_admin: boolean
}

export interface User {
  id: number
  email: string
  is_active: boolean
  organization: Organization
  role: Role
  is_super_admin?: boolean
}

export const authApi = {
  // The server sets the session cookie; the token in the body is for API
  // clients and is deliberately not kept here.
  login: (email: string, password: string) =>
    api.post<{ access_token: string; token_type: string }>('/auth/login', { email, password }).then(() => undefined),
  /** `quiet`: a 401 means "not logged in", not "session expired". */
  me: (opts?: { quiet?: boolean }) =>
    api.get<User>('/auth/me', opts?.quiet ? ({ quiet401: true } as object) : undefined).then(r => r.data),
  logout: () => api.post('/auth/logout').then(() => undefined),
  /** Move a pre-T6 localStorage token into the httpOnly cookie, once. */
  adoptSession: (token: string) =>
    api.post('/auth/session', null, { headers: { Authorization: `Bearer ${token}` }, quiet401: true } as object)
      .then(() => undefined),
}

// ── SSO (OIDC single sign-on) ───────────────────────────────────────────────────
// (the origin is resolved once at the top of this file)

export interface SsoConfig {
  configured?: boolean
  protocol?: string
  enabled?: boolean
  email_domain?: string
  issuer?: string
  client_id?: string
  client_secret?: string      // the redaction sentinel on read; send back to keep unchanged
  config?: Record<string, unknown>
}

export const ssoApi = {
  // Does this email's domain have SSO configured? Drives the login page's SSO button.
  discover: (email: string) =>
    api.post<{ sso: boolean; protocol: string | null }>('/auth/sso/discover', { email }).then(r => r.data),
  // A full browser navigation (not XHR) so the IdP round-trip and cookies work.
  loginUrl: (email: string, protocol?: string | null) =>
    `${API_ORIGIN}/api/v1/auth/sso/${protocol === 'saml' ? 'saml' : 'oidc'}/login?email=${encodeURIComponent(email)}`,
  getConfig: () => api.get<SsoConfig>('/auth/sso/config').then(r => r.data),
  putConfig: (body: SsoConfig) => api.put<SsoConfig>('/auth/sso/config', body).then(r => r.data),
  deleteConfig: () => api.delete('/auth/sso/config').then(r => r.data),
}

export interface ApiKey {
  id: number
  name: string
  prefix: string
  created_at?: string
  last_used_at?: string | null
}

export const apiKeysApi = {
  list:   () => api.get<ApiKey[]>('/auth/api-keys').then(r => r.data),
  // The response carries `key` (the full secret) exactly once, at creation.
  create: (name: string) => api.post<ApiKey & { key: string }>('/auth/api-keys', { name }).then(r => r.data),
  revoke: (id: number) => api.delete(`/auth/api-keys/${id}`),
}

export interface OrgQuota {
  max_queries_per_day: number | null
  max_agent_asks_per_day: number | null
  max_storage_mb: number | null
  max_concurrent_asks: number | null
  /** E11: the model's tokens (prompt + completion) per UTC day / calendar month. */
  max_ai_tokens_per_day: number | null
  max_ai_tokens_per_month: number | null
}

export interface OrgUsage {
  queries_today: number
  agent_asks_today: number
  storage_bytes: number
  ai_tokens_today: number
  ai_tokens_month: number
}

/** E11: where an org's AI tokens went over the last `days` days. */
export interface OrgAiUsage {
  org_id: number
  days: number
  since: string
  total_tokens: number
  remaining: number | null
  binding_limit: 'ai_tokens_per_day' | 'ai_tokens_per_month' | null
  by_day: { day: string; tokens: number; calls: number; refused: number }[]
  by_feature: { feature: string; tokens: number; calls: number; refused: number }[]
  by_user: { user_id: number | null; email: string | null; tokens: number; calls: number; refused: number }[]
}

export interface PlatformOrg {
  id: number
  name: string
  created_at?: string
  user_count: number
  parent_org_id: number | null
  mcp_enabled: boolean
  quota: OrgQuota
  usage: OrgUsage
}

export const platformApi = {
  listOrgs: () => api.get<PlatformOrg[]>('/platform/organizations').then(r => r.data),
  aiUsage: (orgId: number, days = 30) =>
    api.get<OrgAiUsage>(`/platform/organizations/${orgId}/ai-usage`, { params: { days } }).then(r => r.data),
  createOrg: (body: { name: string; admin_email: string; admin_password: string }) =>
    api.post<{ org_id: number; name: string; admin_user_id: number; admin_email: string }>('/platform/organizations', body).then(r => r.data),
  setParent: (orgId: number, parentOrgId: number | null) =>
    api.put<{ org_id: number; parent_org_id: number | null }>(`/platform/organizations/${orgId}/parent`, { parent_org_id: parentOrgId }).then(r => r.data),
  setMcp: (orgId: number, enabled: boolean) =>
    api.put<{ org_id: number; mcp_enabled: boolean }>(`/platform/organizations/${orgId}/mcp`, { enabled }).then(r => r.data),
  setQuota: (orgId: number, body: OrgQuota) =>
    api.put<{ org_id: number } & OrgQuota>(`/platform/organizations/${orgId}/quota`, body).then(r => r.data),
}

export const adminRolesApi = {
  list:   () => api.get<Role[]>('/admin/roles').then(r => r.data),
  create: (body: { name: string; is_org_admin: boolean }) =>
    api.post<Role>('/admin/roles', body).then(r => r.data),
  update: (id: number, body: Partial<{ name: string; is_org_admin: boolean }>) =>
    api.patch<Role>(`/admin/roles/${id}`, body).then(r => r.data),
  delete: (id: number) => api.delete(`/admin/roles/${id}`),
}

export const adminUsersApi = {
  list:   () => api.get<User[]>('/admin/users').then(r => r.data),
  create: (body: { email: string; password: string; role_id: number }) =>
    api.post<User>('/admin/users', body).then(r => r.data),
  update: (id: number, body: Partial<{ email: string; password: string; role_id: number; is_active: boolean }>) =>
    api.patch<User>(`/admin/users/${id}`, body).then(r => r.data),
  delete: (id: number) => api.delete(`/admin/users/${id}`),
  bulkCreate: (users: { email: string; password: string; role: string }[]) =>
    api.post<{ created_count: number; created: string[]; errors: { row: number; email: string; error: string }[] }>(
      '/admin/users/bulk', { users }).then(r => r.data),
}

export interface RowSecurityRule {
  id: number
  role_id: number
  dataset_id: number
  filter_expr: string
  // S0c: true when this rule (or its current filter_expr) came from
  // /admin/rls-rules/auto-generate rather than being hand-typed. Editing it
  // through the normal update flow clears the flag server-side.
  auto_generated: boolean
  created_at: string
}

/** S0c: one column-derived candidate — `restrict by current user/org?` — shown
 *  as a checkbox before the admin applies it. */
export interface RlsRuleProposal {
  column: string
  kind: 'user_email' | 'org_id' | 'org_name'
  expression: string
}

export const adminRlsRulesApi = {
  list:   () => api.get<RowSecurityRule[]>('/admin/row-security-rules').then(r => r.data),
  create: (body: { role_id: number; dataset_id: number; filter_expr: string }) =>
    api.post<RowSecurityRule>('/admin/row-security-rules', body).then(r => r.data),
  update: (id: number, body: { filter_expr: string }) =>
    api.patch<RowSecurityRule>(`/admin/row-security-rules/${id}`, body).then(r => r.data),
  delete: (id: number) => api.delete(`/admin/row-security-rules/${id}`),
  /** apply=false (default): just the proposals for this dataset's columns.
   *  apply=true (needs role_id): creates/extends the role+dataset rule from the
   *  selected columns (all proposals when `columns` is omitted). */
  autoGenerate: (dataset_id: number, opts?: { role_id?: number; apply?: boolean; columns?: string[] }) =>
    api.post<{ proposals: RlsRuleProposal[]; created?: RowSecurityRule | null; skipped?: string[]; reason?: string }>(
      '/admin/rls-rules/auto-generate', { dataset_id, ...opts }).then(r => r.data),
  /** What a draft rule reads, and which of those columns the role cannot see
   *  (column security). Informational, for the Row security modal. */
  preflight: (role_id: number, dataset_id: number, filter_expr: string) =>
    api.get<{ columns: string[]; denied: string[] }>('/admin/row-security-rules/preflight',
      { params: { role_id, dataset_id, filter_expr } }).then(r => r.data),
}


// ── Layer 1: metadata plane ──────────────────────────────────────────────────
// Sync, review and column statistics. See
// docs/superpowers/specs/2026-08-24-layer1-connectors-ingestion-design.md.

export interface SyncStage {
  name: string
  status: 'ok' | 'failed' | 'skipped'
  ms?: number
  detail?: Record<string, any>
  error?: string
}

export interface SyncRun {
  id?: number
  status: 'running' | 'ok' | 'partial' | 'failed' | 'never_run'
  trigger?: string
  stages: SyncStage[]
  error?: string | null
  started_at?: string
  finished_at?: string | null
}

/** Why inference proposed a relationship. Rendered in review so a suggestion can
 *  be judged rather than taken on trust. */
export interface FkEvidence {
  overlap: number
  name_score: number
  child_distinct?: number
  parent_distinct?: number
  high_confidence?: boolean
}

export interface ReviewRelationship {
  id: number
  from_dataset_id: number
  from_dataset: string
  from_column: string
  to_dataset_id: number
  to_dataset: string | null
  to_column: string
  confidence: number
  /** confirmed > declared > inferred. Only `inferred` is ever asked about. */
  source: 'inferred' | 'declared' | 'confirmed'
  cardinality: string | null
  evidence: FkEvidence | null
  needs_review: boolean
}

export interface ReviewColumn {
  id: number
  dataset_id: number
  dataset: string
  name: string
  dtype: string
  semantic_type: string | null
  description: string | null
  description_source: string | null
  needs_review: boolean
  /** What a coded value MEANS, e.g. {"1": "new", "2": "paid"}. */
  enum_labels?: Record<string, string> | null
  enum_labels_source?: string | null
}

/** The database-level summary — what a person reads first after a sync. */
export interface ReviewSource {
  id: number
  name: string
  type: string
  description: string | null
  description_source: string | null
  allow_llm_sampling: boolean
  sync_status: string | null
  last_synced_at: string | null
}

export interface ReviewQueue {
  source: ReviewSource
  /** Objects in the SOURCE CATALOG — every table and view the connection can
   *  see, not the datasets anyone imported. Named `datasets` for continuity
   *  with the older contract. */
  datasets: {
    id: number; name: string; kind?: string; row_count?: number | null
    is_deprecated: boolean
    /** Set when sampling this object last ran out of its time budget. Non-null
     *  means the next sync will skip it, so it has to be visible and undoable
     *  rather than silent. */
    sample_timed_out_at?: string | null
    description: string | null; description_source: string | null
    /** An admin's assertion that this object is the source of truth for what
     *  it describes -- see agent/nodes/generate.py's canonical preference. */
    is_canonical?: boolean
  }[]
  relationships: ReviewRelationship[]
  columns: ReviewColumn[]
}

export interface ColumnStats {
  column: string
  dtype: string
  semantic_type: string | null
  description?: string | null
  description_source?: string | null
  profiled: boolean
  null_ratio?: number | null
  distinct_count?: number | null
  /** The column's real values. A filter control can offer these as a dropdown
   *  instead of a free-text box the user has to guess into. */
  top_k?: { value: string; count: number | null; ratio: number }[] | null
  min_value?: string | null
  max_value?: string | null
  /** False means these are the engine's estimates, not measured values. */
  exact?: boolean
  computed_at?: string
  /** True when the caller's rows are filtered by a row rule: the figures are
   *  whole-table, so the value-bearing ones are left out. */
  restricted?: boolean
}

/** Task R3 / spec section 5 (E2): a named business object this source
 *  models -- "customer", "order" -- distinct from the raw table/view that
 *  backs it. `grain` states what a single row of the entity IS. */
export interface ReviewEntity {
  id: number
  name: string
  business_name: string | null
  grain: string | null
  description: string | null
  primary_object: string | null
  /** inferred | confirmed -- mirrors ReviewColumn.enum_labels_source. */
  source: 'inferred' | 'confirmed'
}

export interface DriftVersion {
  id: number
  fingerprint: string
  detected_at: string
  is_baseline: boolean
  added: { table: string; name: string; dtype: string }[]
  removed: { table: string; name: string; dtype: string }[]
  changed: { table: string; name: string; changes: Record<string, { from: any; to: any }> }[]
  orphaned_annotations: { table: string; name: string; detail: string }[]
}

/** POST /sync returns as soon as the run row exists — the stages are still
 *  running. Poll `syncStatus` with this id to follow them. */
export interface SyncStarted {
  sync_run_id: number
  status: 'running'
  stages: SyncStage[]
}

// ── Layer 4: agent orchestration ─────────────────────────────────────────────
// A conversation is created lazily on first question, scoped to one data
// source. Each answer names the run that produced it, so provenance (the SQL
// each step actually ran) is a follow-up fetch keyed on that run id rather
// than something the answer payload has to carry every time.

/** A sink step's rows, capped server-side (RESULT_ROW_CAP): `total` is the
 *  true count and `truncated` says whether `rows` is only the head of it. */
export interface AgentResult {
  step: string
  columns: string[]
  rows: (string | number | boolean | null)[][]
  total: number
  truncated: boolean
  /** Where these rows came from. `query` is what a SELECT returned; `catalog`
   *  is the metadata store's own description of what is in scope, shown when
   *  someone asks what the data IS. Rows with no query behind them are the
   *  shape a fabricated answer has, so the two are never left to look alike. */
  source?: 'query' | 'catalog'
}

/** One number the answer states, traced by the server (services/agent/
 *  evidence.py). `traced` points at where it came from: a cell (`row` and
 *  `column` of `results[result]`), the row count, or arithmetic over the rows
 *  (a column's sum or average, a row's share, the difference or change between
 *  `rows`). `untraced` is a number found nowhere in the rows; `context` is one
 *  the question or the SQL stated ("top 5", LIMIT 10), not a finding. */
export interface EvidenceClaim {
  start: number
  end: number
  text: string
  status: 'traced' | 'untraced' | 'context'
  source?: {
    result: number
    row: number | null
    column: string | null
    value: number | string | null
    kind: 'cell' | 'count' | 'sum' | 'average' | 'share' | 'difference' | 'change'
    rows?: number[]
  }
}

export interface AnswerEvidence {
  claims: EvidenceClaim[]
  untraced: number
}

/** Set on a run that only re-shows an earlier result ("as a bar chart"). */
export interface AgentPresentation {
  format: 'table' | 'bar' | 'line' | 'pie' | 'csv'
  limit: number | null
  /** The two columns a chart uses: `x` labels the marks, `y` sizes them.
   *  Chosen on the server (services/agent/charts.py) so the picture the chat
   *  draws is the one the agent decided on, not a second guess made here. */
  x?: string | null
  y?: string | null
}

export interface AgentAnswer {
  run_id: number
  status: 'ok' | 'failed' | 'needs_clarification'
  answer: string | null
  intent: string | null
  error: string | null
  results?: AgentResult[]
  sql?: string[]
  presentation?: AgentPresentation | null
  context_objects?: string[] | null
  evidence?: AnswerEvidence | null
}

export interface AgentConversation {
  id: number
  title: string
  data_source_id: number | null
  dataset_ids: number[] | null
  created_at?: string | null
}

/** One turn of a stored conversation; assistant turns carry their run. */
export interface AgentMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string | null
  run: {
    id: number
    status: AgentAnswer['status']
    intent: string | null
    error: string | null
    results: AgentResult[]
    sql: string[]
    presentation: AgentPresentation | null
    context_objects: string[] | null
    evidence?: AnswerEvidence | null
  } | null
}

export const agentApi = {
  createConversation: (target: { dataSourceId?: number; datasetIds?: number[] }, title?: string) =>
    api.post<{ id: number; title: string }>('/agent/conversations',
      target.dataSourceId != null
        ? { data_source_id: target.dataSourceId, title }
        : { dataset_ids: target.datasetIds, title }).then(r => r.data),
  listConversations: () =>
    api.get<AgentConversation[]>('/agent/conversations').then(r => r.data),
  messages: (conversationId: number) =>
    api.get<AgentMessage[]>(`/agent/conversations/${conversationId}/messages`).then(r => r.data),
  rename: (conversationId: number, title: string) =>
    api.patch<{ id: number; title: string }>(`/agent/conversations/${conversationId}`,
      { title }).then(r => r.data),
  remove: (conversationId: number) =>
    api.delete(`/agent/conversations/${conversationId}`).then(() => undefined),
  ask: (conversationId: number, question: string) =>
    api.post<AgentAnswer>(`/agent/conversations/${conversationId}/ask`,
      { question }).then(r => r.data),
  runDetail: (runId: number) =>
    api.get<{ steps: { sql: string | null; status: string; result_rows?: AgentResult | null }[]
              context_objects?: string[] | null }>(
      `/agent/runs/${runId}`).then(r => r.data),
  /** Download one answer's result as Excel or PDF, built server-side from
   *  the stored snapshot (CSV stays client-side -- the rows are already in
   *  the browser). Blob response; the browser saves it. */
  downloadRunFile: async (runId: number, format: 'xlsx' | 'pdf') => {
    const r = await api.get(`/agent/runs/${runId}/export`,
      { params: { format }, responseType: 'blob' })
    const url = URL.createObjectURL(r.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `ask-ai-result-${runId}.${format}`
    document.body.appendChild(a); a.click(); a.remove()
    URL.revokeObjectURL(url)
  },
  feedback: (conversationId: number, body: { runId: number | null; rating: 'up' | 'down' }) =>
    api.post<{ id: number; run_id: number | null; rating: string; comment: string | null }>(
      `/agent/conversations/${conversationId}/feedback`,
      { run_id: body.runId, rating: body.rating }).then(r => r.data),
}

/** Describe one of a dataset's columns. The response says WHERE the sentence
 *  landed: `source` means it was written to the catalog and now describes that
 *  column for every dataset built from the same table; `dataset` means this
 *  dataset is the only place it could go (an upload, or a query whose output
 *  matched no catalogued column). */
export interface ColumnDescriptionResult {
  written_to: 'source' | 'dataset'
  shared: boolean
  object: string
  column: string
}

export const metadataApi = {
  sync:       (sourceId: number) =>
    api.post<SyncStarted>(`/data-sources/${sourceId}/sync`).then(r => r.data),
  latestSync: (sourceId: number) =>
    api.get<SyncRun>(`/data-sources/${sourceId}/sync/latest`).then(r => r.data),
  syncStatus: (sourceId: number, runId: number) =>
    api.get<SyncRun>(`/data-sources/${sourceId}/sync/${runId}`).then(r => r.data),
  review:     (sourceId: number) =>
    api.get<ReviewQueue>(`/data-sources/${sourceId}/review`).then(r => r.data),
  confirm:    (sourceId: number, body: {
                 relationship_ids?: number[]
                 rejected_relationship_ids?: number[]
                 column_updates?: { id: number; description?: string; semantic_type?: string
                                     enum_labels?: Record<string, string> }[]
                 /** `retry_sample` clears a skip flag: the next sync then treats
                  *  the object like any other. `is_canonical` marks the object as
                  *  the source of truth for what it describes. */
                 object_updates?: { id: number; description?: string; retry_sample?: boolean
                                     is_canonical?: boolean }[]
               }) =>
    api.post<{ confirmed: number; rejected: number; columns_updated: number }>(
      `/data-sources/${sourceId}/review/confirm`, body).then(r => r.data),
  settings:   (sourceId: number, body: { allow_llm_sampling?: boolean; description?: string }) =>
    api.patch<{ allow_llm_sampling: boolean; description: string | null
                description_source: string | null }>(
      `/data-sources/${sourceId}/metadata-settings`, body).then(r => r.data),
  drift:      (sourceId: number) =>
    api.get<DriftVersion[]>(`/data-sources/${sourceId}/drift`).then(r => r.data),
  columnStats: (datasetId: number, column: string) =>
    api.get<ColumnStats>(
      `/datasets/${datasetId}/columns/${encodeURIComponent(column)}/stats`).then(r => r.data),
  entities:   (sourceId: number) =>
    api.get<ReviewEntity[]>(`/data-sources/${sourceId}/entities`).then(r => r.data),
  confirmEntities: (sourceId: number, body: {
                     updates: { id: number; business_name?: string; grain?: string
                                description?: string; confirm?: boolean }[]
                   }) =>
    api.post<{ updated: number }>(
      `/data-sources/${sourceId}/entities/confirm`, body).then(r => r.data),
  /** The business vocabulary. These three endpoints shipped with the retrieval
   *  work and had NO caller until the Glossary tab existed -- so "GMV" and
   *  "إجمالي المبيعات" could resolve to the same metric in principle and
   *  nobody could ever type one in. */
  glossary: (sourceId: number) =>
    api.get<GlossaryTerm[]>(`/data-sources/${sourceId}/glossary`).then(r => r.data),
  addTerm: (sourceId: number, body: { term: string; definition?: string
                                      synonyms?: string[]; maps_to_object?: string
                                      maps_to_column?: string; rule?: string; always?: boolean }) =>
    api.post<GlossaryTerm>(`/data-sources/${sourceId}/glossary`, body).then(r => r.data),
  updateTerm: (sourceId: number, termId: number, body: { definition?: string | null
                                      synonyms?: string[]; rule?: string | null; always?: boolean }) =>
    api.patch<GlossaryTerm>(`/data-sources/${sourceId}/glossary/${termId}`, body).then(r => r.data),
  deleteTerm: (sourceId: number, termId: number) =>
    api.delete(`/data-sources/${sourceId}/glossary/${termId}`),
}

/** A business term and its aliases. `data_source_id` null means the term is
 *  org-wide -- "GMV" usually means the same thing on every connection. */
export interface GlossaryTerm {
  id: number
  term: string
  definition: string | null
  synonyms: string[]
  maps_to_object: string | null
  maps_to_column: string | null
  /** A rule the AI must follow when the term is meant: a SQL predicate
   *  ("dept_emp.to_date = '9999-01-01'") or a one-line instruction. */
  rule?: string | null
  /** Apply `rule` to every question on this connection, named or not. */
  always?: boolean
  data_source_id: number | null
}

/** One share on a workspace folder, names resolved server-side. Exactly one
 *  of user/role/org-unit is set. */
export interface WorkspaceGrant {
  id: number
  level: 'view' | 'edit'
  user_id: number | null
  user_email: string | null
  role_id: number | null
  role_name: string | null
  org_unit_id: number | null
  org_unit_name: string | null
}

/** What the PUT accepts: a member typed by email, a role, or a team. */
export interface WorkspaceGrantEntry {
  user_email?: string
  role_id?: number
  org_unit_id?: number
  level: 'view' | 'edit'
}

/** Names any member may need to address a share. Members stay unlisted —
 *  they are typed as emails. */
export interface WorkspaceShareOptions {
  roles: { id: number; name: string }[]
  /** The org chart: Country > Region > Department > Team. `level_name` is the
   *  org's OWN word for the tier (free text, so depth and vocabulary differ
   *  per organisation) and the share picker groups on it. */
  org_units: { id: number; name: string; parent_id: number | null
               level_name: string | null }[]
}

export const workspaceApi = {
  tree:   ()                                    => api.get<WorkspaceTree>('/workspace/tree').then(r => r.data),
  create: (data: Partial<WorkspaceNode>)        => api.post<WorkspaceNode>('/workspace/nodes', data).then(r => r.data),
  update: (id: number, data: Partial<WorkspaceNode>) => api.patch<WorkspaceNode>(`/workspace/nodes/${id}`, data).then(r => r.data),
  delete: (id: number)                          => api.delete(`/workspace/nodes/${id}`),
  roles:    (id: number)                        => api.get<number[]>(`/workspace/nodes/${id}/roles`).then(r => r.data),
  setRoles: (id: number, roleIds: number[])     => api.put<number[]>(`/workspace/nodes/${id}/roles`, roleIds).then(r => r.data),
  grants:    (id: number)                       => api.get<WorkspaceGrant[]>(`/workspace/nodes/${id}/grants`).then(r => r.data),
  setGrants: (id: number, entries: WorkspaceGrantEntry[]) => api.put<WorkspaceGrant[]>(`/workspace/nodes/${id}/grants`, entries).then(r => r.data),
  shareOptions: ()                              => api.get<WorkspaceShareOptions>('/workspace/share-options').then(r => r.data),
}

/** Row rules that apply to a CONNECTION — the ones Ask AI obeys.
 *
 *  Distinct from `adminRulesApi` above, which narrows a DATASET. The two are
 *  separate systems and setting one does not affect the other; a dataset rule
 *  does not reach the agent, which is why this had to become reachable. */
export const agentPoliciesApi = {
  list:   (sourceId: number) =>
    api.get<ConnectionRowPolicy[]>('/agent/row-policies', { params: { source_id: sourceId } })
      .then(r => r.data),
  create: (body: { source_object_id: number; role_id: number; predicate: string }) =>
    api.post<ConnectionRowPolicy>('/agent/row-policies', body).then(r => r.data),
  remove: (id: number) => api.delete(`/agent/row-policies/${id}`),
}

export interface ConnectionRowPolicy {
  id: number
  source_object_id: number
  object_name: string
  role_id: number
  role_name: string
  predicate: string
}

export interface QualityColumn {
  column: string
  dtype: string
  missing: number
  missing_pct: number
  distinct: number
  outliers: number | null
  issues: string[]
}

export interface QualityReport {
  rows: number
  columns: number
  missing_cells: number
  missing_pct: number
  duplicate_rows: number
  duplicate_examples: Record<string, unknown>[]
  columns_with_issues: number
  column_report: QualityColumn[]
  rules: { rule: string; failing_rows?: number; examples?: Record<string, unknown>[]; error?: string }[]
}

// ── E17: the migration inventory ────────────────────────────────────────────

export type MigrationStatus = 'to_map' | 'mapped' | 'differences' | 'reconciled' | 'signed_off' | 'retired'
export type MigrationFit = 'native' | 'partial' | 'manual'
export interface MigrationFeature {
  key: string; label: string; target: string; fit: MigrationFit; note: string; count?: number
}
export interface MigrationReconcile {
  widget_key: string; title: string | null; file: string | null; at: string; by_email: string
  counts: ReconcileResult['counts']; report_id: number; revision: number | null
}
export interface MigrationItem {
  id: number; name: string; kind: string; source_system: string; source_path: string | null
  decision: 'migrate' | 'retire'; notes: string | null
  owner: { id: number; email: string } | null
  report: { id: number; name: string | null; can_open: boolean } | null
  features: { features: MigrationFeature[]; unknown_procs: string[]; libnames: string[]; lines: number; file?: string } | null
  fit: MigrationFit | null
  reconciles: MigrationReconcile[]
  sign_off: { by_email: string; at: string; basis: 'reconciled' | 'accepted' | 'no_comparison'; note: string | null } | null
  report_changed_since_sign_off: boolean
  status: MigrationStatus
  can_edit: boolean; can_sign_off: boolean
}
export interface MigrationItemIn {
  name?: string; kind?: string; source_system?: string; source_path?: string | null
  owner_id?: number | null; report_id?: number | null; decision?: 'migrate' | 'retire'; notes?: string | null
}

export const migrationApi = {
  list: () => api.get<{ items: MigrationItem[]; summary: Record<MigrationStatus, number>; can_manage: boolean }>(
    '/migration/items').then(r => r.data),
  featureMap: () => api.get<MigrationFeature[]>('/migration/feature-map').then(r => r.data),
  create: (body: MigrationItemIn) => api.post<MigrationItem>('/migration/items', body).then(r => r.data),
  update: (id: number, body: MigrationItemIn) => api.patch<MigrationItem>(`/migration/items/${id}`, body).then(r => r.data),
  remove: (id: number) => api.delete(`/migration/items/${id}`),
  import: (files: File[]) => {
    const form = new FormData()
    files.forEach(f => form.append('files', f))
    return api.post<{ created: number; updated: number; warnings: string[] }>('/migration/items/import', form)
      .then(r => r.data)
  },
  scan: (id: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<MigrationItem>(`/migration/items/${id}/scan`, form).then(r => r.data)
  },
  signOff: (id: number, body: { note?: string; accept_differences?: boolean }) =>
    api.post<MigrationItem>(`/migration/items/${id}/sign-off`, body).then(r => r.data),
  withdrawSignOff: (id: number) => api.delete<MigrationItem>(`/migration/items/${id}/sign-off`).then(r => r.data),
}
