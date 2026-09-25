import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import RequireAdmin from './components/RequireAdmin'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Upload from './pages/Upload'
import DatasetDetail from './pages/DatasetDetail'
import Reports from './pages/Reports'
import ReportBuilder from './pages/ReportBuilder'
import Connections from './pages/Connections'
import AdminRoles from './pages/admin/AdminRoles'
import AdminUsers from './pages/admin/AdminUsers'
import AdminRowSecurityRules from './pages/admin/AdminRowSecurityRules'

export default function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="upload" element={<Upload />} />
              <Route path="datasets/:id" element={<DatasetDetail />} />
              <Route path="reports" element={<Reports />} />
              <Route path="connections" element={<Connections />} />
              <Route element={<RequireAdmin />}>
                <Route path="admin/roles" element={<AdminRoles />} />
                <Route path="admin/users" element={<AdminUsers />} />
                <Route path="admin/row-security-rules" element={<AdminRowSecurityRules />} />
              </Route>
            </Route>
            {/* ReportBuilder is full-page — its own sidebar replaces the global Layout */}
            <Route path="reports/:id" element={<ReportBuilder />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
