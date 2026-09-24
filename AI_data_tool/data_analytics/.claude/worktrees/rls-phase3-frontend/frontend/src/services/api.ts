import axios from 'axios'
import type { Report, ReportPage, Widget, HierarchyNode } from '../types/report'

const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000') + '/api/v1'
export const api = axios.create({ baseURL: BASE })

const TOKEN_KEY = 'datalytics_token'
let authToken: string | null = localStorage.getItem(TOKEN_KEY)
let onUnauthorized: (() => void) | null = null

export function getAuthToken(): string | null {
  return authToken
}

export function setAuthToken(token: string | null): void {
  authToken = token
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler
}

export function attachAuthHeader(config: any) {
  if (authToken) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${authToken}`
  }
  return config
}

export function handleResponseError(error: any) {
  if (error?.response?.status === 401) {
    setAuthToken(null)
    onUnauthorized?.()
  }
  return Promise.reject(error)
}

api.interceptors.request.use(attachAuthHeader)
api.interceptors.response.use(r => r, handleResponseError)

export interface DatasetColumn {
  id: number
  name: string
  dtype: string
  missing_pct: number
  stats: Record<string, unknown>
}

export interface CalcColumnFormat {
  type: 'none' | 'number' | 'integer' | 'currency' | 'percent' | 'bar' | 'badge' | 'trend'
  decimals?: number
  symbol?: string       // currency symbol e.g. '$', 'SAR', '€'
  prefix?: string
  suffix?: string
  min?: number          // bar scale min
  max?: number          // bar scale max
  color?: string        // bar fill color
  thresholds?: [number, number]  // [low, high] for badge coloring
}

export interface CalcColumn {
  name: string
  expression: string
  dtype?: string
  format?: CalcColumnFormat
}

export interface Dataset {
  id: number
  name: string
  description?: string
  filename?: string
  row_count: number
  col_count: number
  file_size: number
  created_at: string
  updated_at: string
  columns: DatasetColumn[]
  calculated_columns: CalcColumn[]
  column_formats: Record<string, CalcColumnFormat>
  default_filter_expr?: string | null
  data_source_id?:     number | null
  source_table?:       string | null
  source_query?:       string | null
}

export const datasetsApi = {
  list:    ()         => api.get<Dataset[]>('/datasets').then(r => r.data),
  get:     (id: number) => api.get<Dataset>(`/datasets/${id}`).then(r => r.data),
  delete:  (id: number) => api.delete(`/datasets/${id}`),
  refresh: (id: number) => api.post<Dataset>(`/datasets/${id}/refresh`).then(r => r.data),
  upload: (file: File, name: string, desc = '') => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('name', name)
    fd.append('description', desc)
    return api.post<Dataset>('/datasets', fd).then(r => r.data)
  },
}

export const analysisApi = {
  run: (id: number, type = 'full') =>
    api.post(`/datasets/${id}/analysis`, { analysis_type: type }).then(r => r.data),
  get: (id: number) =>
    api.get(`/datasets/${id}/analysis`).then(r => r.data),
}

export const reportsApi = {
  list:   ()                                       => api.get<Report[]>('/reports').then(r => r.data),
  get:    (id: number)                             => api.get<Report>(`/reports/${id}`).then(r => r.data),
  create: (data: { name: string; description?: string; dataset_id?: number }) =>
    api.post<Report>('/reports', data).then(r => r.data),
  update: (id: number, data: Partial<{ name: string; description: string; dataset_id: number; additional_dataset_ids: number[] }>) =>
    api.patch<Report>(`/reports/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/reports/${id}`),

  addPage:    (rid: number, data: Partial<ReportPage> & { name: string; position: number }) =>
    api.post<ReportPage>(`/reports/${rid}/pages`, data).then(r => r.data),
  updatePage: (rid: number, pid: number, data: Partial<ReportPage>) =>
    api.patch<ReportPage>(`/reports/${rid}/pages/${pid}`, data).then(r => r.data),
  deletePage: (rid: number, pid: number) => api.delete(`/reports/${rid}/pages/${pid}`),

  addWidget:    (rid: number, pid: number, data: Partial<Widget>) =>
    api.post<Widget>(`/reports/${rid}/pages/${pid}/widgets`, data).then(r => r.data),
  updateWidget: (rid: number, pid: number, wid: number, data: Partial<Widget>) =>
    api.patch<Widget>(`/reports/${rid}/pages/${pid}/widgets/${wid}`, data).then(r => r.data),
  deleteWidget: (rid: number, pid: number, wid: number) =>
    api.delete(`/reports/${rid}/pages/${pid}/widgets/${wid}`),
}

export const hierarchyApi = {
  get:          (dsId: number)                              => api.get<HierarchyNode[]>(`/datasets/${dsId}/hierarchy`).then(r => r.data),
  create:       (dsId: number, data: Partial<HierarchyNode>) => api.post<HierarchyNode>(`/datasets/${dsId}/hierarchy`, data).then(r => r.data),
  update:       (dsId: number, nid: number, data: Partial<HierarchyNode>) => api.patch<HierarchyNode>(`/datasets/${dsId}/hierarchy/${nid}`, data).then(r => r.data),
  delete:       (dsId: number, nid: number)                 => api.delete(`/datasets/${dsId}/hierarchy/${nid}`),
  autoGenerate: (dsId: number)                              => api.post<HierarchyNode[]>(`/datasets/${dsId}/hierarchy/auto-generate`).then(r => r.data),
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

export const calcColumnsApi = {
  list:    (dsId: number)                            => api.get<CalcColumn[]>(`/datasets/${dsId}/calculated-columns`).then(r => r.data),
  save:    (dsId: number, col: CalcColumn)           => api.put<CalcColumn[]>(`/datasets/${dsId}/calculated-columns`, col).then(r => r.data),
  delete:  (dsId: number, name: string)              => api.delete<CalcColumn[]>(`/datasets/${dsId}/calculated-columns/${encodeURIComponent(name)}`).then(r => r.data),
  preview: (dsId: number, expression: string)        => api.post<{ok:boolean;dtype?:string;sample?:unknown[];error?:string}>(`/datasets/${dsId}/calculated-columns/preview`, { expression }).then(r => r.data),
}

export const widgetDataApi = {
  query: (dsId: number, config: Record<string, unknown>, calculatedColumns: CalcColumn[] = [], widgetType = 'bar') =>
    api.post(`/datasets/${dsId}/widget-data`, { config, calculated_columns: calculatedColumns, widget_type: widgetType }).then(r => r.data),
}

export interface DataSource {
  id: number
  name: string
  type: string
  config: Record<string, unknown>
  created_at: string
}

export const dataSourcesApi = {
  list:    ()                                              => api.get<DataSource[]>('/data-sources').then(r => r.data),
  create:  (body: { name: string; type: string; config: Record<string, unknown> }) =>
    api.post<DataSource>('/data-sources', body).then(r => r.data),
  update:  (id: number, body: Partial<{ name: string; type: string; config: Record<string, unknown> }>) =>
    api.put<DataSource>(`/data-sources/${id}`, body).then(r => r.data),
  delete:  (id: number)                                   => api.delete(`/data-sources/${id}`),
  test:    (id: number)                                   => api.post<{ ok: boolean; error?: string }>(`/data-sources/${id}/test`).then(r => r.data),
  schema:  (id: number)                                   => api.get<{ tables: { name: string; kind: string }[] }>(`/data-sources/${id}/schema`).then(r => r.data),
  preview: (id: number, table?: string, query?: string, limit = 200) =>
    api.post<{ columns: string[]; rows: unknown[][]; total: number }>(`/data-sources/${id}/preview`, { table, query, limit }).then(r => r.data),
  import:  (id: number, dataset_name: string, table?: string, query?: string) =>
    api.post<{ id: number; name: string; row_count: number; col_count: number }>(`/data-sources/${id}/import`, { dataset_name, table, query }).then(r => r.data),
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
}

export const authApi = {
  login: (email: string, password: string) =>
    api.post<{ access_token: string; token_type: string }>('/auth/login', { email, password }).then(r => r.data),
  me: () => api.get<User>('/auth/me').then(r => r.data),
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
}

export interface RowSecurityRule {
  id: number
  role_id: number
  dataset_id: number
  filter_expr: string
  created_at: string
}

export const adminRlsRulesApi = {
  list:   () => api.get<RowSecurityRule[]>('/admin/row-security-rules').then(r => r.data),
  create: (body: { role_id: number; dataset_id: number; filter_expr: string }) =>
    api.post<RowSecurityRule>('/admin/row-security-rules', body).then(r => r.data),
  update: (id: number, body: { filter_expr: string }) =>
    api.patch<RowSecurityRule>(`/admin/row-security-rules/${id}`, body).then(r => r.data),
  delete: (id: number) => api.delete(`/admin/row-security-rules/${id}`),
}
