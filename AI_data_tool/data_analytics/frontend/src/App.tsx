import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import { Suspense, lazy } from 'react'
import { AuthProvider } from './contexts/AuthContext'
import { DirectionProvider } from './contexts/DirectionContext'
import { ConfirmProvider } from './components/ui/ConfirmDialog'
import { PromptProvider } from './components/ui/PromptDialog'
import ProtectedRoute from './components/ProtectedRoute'
import RequireAdmin from './components/RequireAdmin'
import RequireSuperAdmin from './components/RequireSuperAdmin'
import Layout from './components/Layout'
import Login from './pages/Login'
import { useT } from './i18n'
const SsoCallback = lazy(() => import('./pages/SsoCallback'))
import Dashboard from './pages/Dashboard'
const Home = lazy(() => import('./pages/Home'))
import Upload from './pages/Upload'
const DatasetDetail = lazy(() => import('./pages/DatasetDetail'))
import Reports from './pages/Reports'
import Loader from './components/ui/Loader'
import ErrorBoundary from './components/ui/ErrorBoundary'
import NotFound from './pages/NotFound'
const ReportBuilder = lazy(() => import('./pages/ReportBuilder'))
const ReportPrint = lazy(() => import('./pages/ReportPrint'))
const Connections = lazy(() => import('./pages/Connections'))
const Lineage = lazy(() => import('./pages/Lineage'))
const SourceReview = lazy(() => import('./pages/SourceReview'))
const SharedReport = lazy(() => import('./pages/SharedReport'))
const EmbeddedReport = lazy(() => import('./pages/EmbeddedReport'))
const AdminRoles = lazy(() => import('./pages/admin/AdminRoles'))
const AdminCustomConnectors = lazy(() => import('./pages/admin/AdminCustomConnectors'))
const AdminUsers = lazy(() => import('./pages/admin/AdminUsers'))
const AdminRowSecurityRules = lazy(() => import('./pages/admin/AdminRowSecurityRules'))
const ConnectionRowPolicies = lazy(() => import('./pages/admin/ConnectionRowPolicies'))
const AdminExportPolicy = lazy(() => import('./pages/admin/AdminExportPolicy'))
const AdminMaps = lazy(() => import('./pages/admin/AdminMaps'))
const PlatformOrgs = lazy(() => import('./pages/admin/PlatformOrgs'))
const ApiKeys = lazy(() => import('./pages/admin/ApiKeys'))
const AdminSso = lazy(() => import('./pages/admin/AdminSso'))
const AdminAudit = lazy(() => import('./pages/admin/AdminAudit'))
const AdminColumnSecurityRules = lazy(() => import('./pages/admin/AdminColumnSecurityRules'))
const AdminOrgUnits = lazy(() => import('./pages/admin/AdminOrgUnits'))
const AskAI = lazy(() => import('./pages/AskAI'))
const InsightsHub = lazy(() => import('./pages/InsightsHub'))
const MonitoringJobs = lazy(() => import('./pages/monitoring/MonitoringJobs'))
const MonitoringDeliveries = lazy(() => import('./pages/monitoring/MonitoringDeliveries'))
const MonitoringActivity = lazy(() => import('./pages/monitoring/MonitoringActivity'))

function DashboardAlias() {
  const { id } = useParams()
  return <Navigate to={`/reports/${id}`} replace />
}

/**
 * What you see WHILE NAVIGATING between pages.
 *
 * The routes below are lazy, so this renders for exactly as long as the next
 * page's chunk takes to arrive -- which is the only moment in this app where
 * nothing is on screen and something is on its way. It is deliberately the
 * ONE place the bouncing loader appears: every other wait in the product is a
 * panel or a dialog fetching its own data with the page already drawn around
 * it, and an animation there competes with content the reader is using.
 */
function LoadingFallback() {
  const t = useT()
  return <Loader label={t('common.loading')} />
}

export default function App() {
  // React Router 7: startTransition and relative splat paths, opted into under
  // v6 through future flags, are simply the default now.
  return (
    <BrowserRouter>
      <DirectionProvider>
      <AuthProvider>
        <ConfirmProvider>
        <PromptProvider>
        {/* The report builder pulls in the whole charting library, and the admin pages
            are reached by a minority of users -- both load on demand so the login
            screen does not wait on them. */}
        <Suspense fallback={<LoadingFallback />}>
        <ErrorBoundary>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/sso/callback" element={<SsoCallback />} />
          <Route path="/shared/:token" element={<SharedReport />} />
          <Route path="/embed" element={<EmbeddedReport />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<Layout />}>
              {/* Home is the landing page; the dataset LIST kept its table and
                  moved to its own route + rail entry. `/` no longer renders it,
                  so any old bookmark of "/" still lands somewhere useful rather
                  than 404ing. */}
              <Route index element={<Home />} />
              <Route path="datasets" element={<Dashboard />} />
              <Route path="upload" element={<Upload />} />
              <Route path="ask" element={<AskAI />} />
              <Route path="insights" element={<InsightsHub />} />
              <Route path="datasets/:id" element={<DatasetDetail />} />
              <Route path="reports" element={<Reports />} />
              <Route path="reports/:id" element={<ReportBuilder />} />
              {/* "Dashboards" alias: the product renamed reports to dashboards
                  in every label, and a typed /dashboards URL should land, but
                  /reports stays canonical so no existing link breaks. */}
              <Route path="dashboards" element={<Navigate to="/reports" replace />} />
              <Route path="dashboards/:id" element={<DashboardAlias />} />
              <Route path="reports/:id/print" element={<ReportPrint />} />
              <Route path="connections" element={<Connections />} />
              <Route path="lineage" element={<Lineage />} />
          {/* Layer 1 — confirm the relationships and descriptions that
              metadata inference proposed for one connection. */}
          <Route path="connections/:id/review" element={<SourceReview />} />
              <Route element={<RequireAdmin />}>
                <Route path="admin/roles" element={<AdminRoles />} />
                <Route path="admin/custom-connectors" element={<AdminCustomConnectors />} />
                <Route path="admin/users" element={<AdminUsers />} />
                <Route path="admin/row-security-rules" element={<AdminRowSecurityRules />} />
              {/* The rules Ask AI obeys. Separate system from the dataset rules
                  above, and until now it had no page at all. */}
              <Route path="admin/connection-rules" element={<ConnectionRowPolicies />} />
                <Route path="admin/column-security-rules" element={<AdminColumnSecurityRules />} />
                <Route path="admin/org-units" element={<AdminOrgUnits />} />
                {/* Monitoring is a rail SECTION, not an /admin page family --
                    but it is admin-gated exactly like Admin, so it shares the
                    same route guard. */}
                <Route path="monitoring/jobs" element={<MonitoringJobs />} />
                <Route path="monitoring/deliveries" element={<MonitoringDeliveries />} />
                <Route path="monitoring/activity" element={<MonitoringActivity />} />
                <Route path="admin/export-policy" element={<AdminExportPolicy />} />
                <Route path="admin/api-keys" element={<ApiKeys />} />
                <Route path="admin/sso" element={<AdminSso />} />
                <Route path="admin/maps" element={<AdminMaps />} />
                <Route path="admin/audit" element={<AdminAudit />} />
              </Route>
              <Route element={<RequireSuperAdmin />}>
                <Route path="platform/organizations" element={<PlatformOrgs />} />
              </Route>
              {/* Anything else: a 404 INSIDE the shell. A blank page for a
                  mistyped link read as a crash. */}
              <Route path="*" element={<NotFound />} />
            </Route>
          </Route>
        </Routes>
        </ErrorBoundary>
        </Suspense>
        </PromptProvider>
        </ConfirmProvider>
      </AuthProvider>
      </DirectionProvider>
    </BrowserRouter>
  )
}
