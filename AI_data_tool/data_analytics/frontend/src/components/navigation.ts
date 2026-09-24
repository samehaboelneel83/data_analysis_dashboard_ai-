import { Home, Bot, Database, GitBranch, Waypoints, LayoutDashboard, Sparkles, RefreshCw, Mail, Activity, Users, Shield, Lock, EyeOff, Download, Key, Fingerprint, ScrollText, Building2, Network, Upload, Plug, Map as MapIcon, type LucideIcon } from 'lucide-react'

/**
 * The navigation tree, as data.
 *
 * The rail used to be twenty-one hand-written `item(...)` calls interleaved with
 * `user?.role.is_org_admin && (...)` blocks. Two things were wrong with that:
 * reordering or re-gating an entry meant editing JSX in the middle of a render
 * function, and the permission rule for a destination lived in a different place
 * from the route guard that actually enforces it -- so the two could drift, and
 * a drifted rail either hides a page a user may open or advertises one the
 * router will refuse.
 *
 * So navigation is declared here once: section, label, icon, route, and the
 * permission REQUIRED TO SEE THE ENTRY. `visibleSections()` filters the tree for
 * a viewer; `Layout` renders whatever survives. Adding a destination is one
 * object in this file, and `test_router_reachability` still checks the route
 * itself exists.
 *
 * The gates mirror `App.tsx` exactly:
 *   'member'      -> inside <ProtectedRoute>       (any signed-in user)
 *   'org_admin'   -> inside <RequireAdmin>
 *   'super_admin' -> inside <RequireSuperAdmin>
 * A rail entry must never be less strict than its route guard. `navigationGuards`
 * in Layout.test.tsx pins that correspondence.
 */

export type NavPermission = 'member' | 'org_admin' | 'super_admin'

export interface NavItem {
  /** Route path, exactly as declared in App.tsx -- never a second definition. */
  to: string
  label: string
  icon: LucideIcon
  /** react-router `end`: only the Home route matches exactly. */
  end?: boolean
  permission: NavPermission
}

export interface NavSection {
  /** Section heading, or null for the ungrouped entries at the top of the rail. */
  title: string | null
  permission: NavPermission
  items: NavItem[]
}

/**
 * Deliberately ABSENT, and staying that way until the objects exist: Apps, Data
 * Products, Semantic Models, and any My/Recent/Published split (those are
 * filters inside pages, never navigation nodes). A menu entry with nothing
 * behind it is the dead-control defect `widgetCapabilities.ts` exists to prevent.
 */
export const NAVIGATION: NavSection[] = [
  {
    title: null,
    permission: 'member',
    items: [
      { to: '/', label: 'Home', icon: Home, end: true, permission: 'member' },
      { to: '/ask', label: 'Ask AI', icon: Bot, permission: 'member' },
    ],
  },
  {
    title: 'Data',
    permission: 'member',
    items: [
      { to: '/datasets', label: 'Datasets', icon: Database, permission: 'member', end: true },
      { to: '/lineage', label: 'Lineage', icon: Waypoints, permission: 'member' },
    ],
  },
  {
    // File upload and live connections are how data enters the platform, so
    // they sit together under Data sources rather than as tabs on Datasets.
    title: 'Data sources',
    permission: 'member',
    items: [
      { to: '/upload', label: 'Upload', icon: Upload, permission: 'member' },
      { to: '/connections', label: 'Connections', icon: Plug, permission: 'member' },
    ],
  },
  {
    // The workspace tree renders inside this section, under Dashboards -- it IS
    // the dashboard list, organised, so it is not a separate entry.
    title: 'Analyse',
    permission: 'member',
    items: [
      { to: '/reports', label: 'Dashboards', icon: LayoutDashboard, permission: 'member' },
      { to: '/insights', label: 'Insights', icon: Sparkles, permission: 'member' },
    ],
  },
  {
    title: 'Monitoring',
    permission: 'org_admin',
    items: [
      { to: '/monitoring/jobs', label: 'Refresh & jobs', icon: RefreshCw, permission: 'org_admin' },
      { to: '/monitoring/deliveries', label: 'Deliveries', icon: Mail, permission: 'org_admin' },
      { to: '/monitoring/activity', label: 'Activity', icon: Activity, permission: 'org_admin' },
    ],
  },
  {
    title: 'Admin',
    permission: 'org_admin',
    items: [
      { to: '/admin/users', label: 'Users', icon: Users, permission: 'org_admin' },
      { to: '/admin/roles', label: 'Roles', icon: Shield, permission: 'org_admin' },
      // Directly above Row security: the chart is what a hierarchical rule
      // (`branch in MYSCOPE()`) resolves against, so the two are read together.
      { to: '/admin/org-units', label: 'Organization chart', icon: Network, permission: 'org_admin' },
      { to: '/admin/row-security-rules', label: 'Row security', icon: Lock, permission: 'org_admin' },
      { to: '/admin/column-security-rules', label: 'Column security', icon: EyeOff, permission: 'org_admin' },
      { to: '/admin/export-policy', label: 'Export policy', icon: Download, permission: 'org_admin' },
      { to: '/admin/api-keys', label: 'API keys', icon: Key, permission: 'org_admin' },
      { to: '/admin/custom-connectors', label: 'Custom connectors', icon: Plug, permission: 'org_admin' },
      { to: '/admin/sso', label: 'Single sign-on', icon: Fingerprint, permission: 'org_admin' },
      { to: '/admin/maps', label: 'Maps', icon: MapIcon, permission: 'org_admin' },
      { to: '/admin/audit', label: 'Audit trail', icon: ScrollText, permission: 'org_admin' },
    ],
  },
  {
    title: 'Platform',
    permission: 'super_admin',
    items: [
      { to: '/platform/organizations', label: 'Organizations', icon: Building2, permission: 'super_admin' },
    ],
  },
]

/** What a viewer holds, derived from the same User fields the guards read. */
export interface NavViewer {
  isOrgAdmin: boolean
  isSuperAdmin: boolean
}

export function canSee(permission: NavPermission, viewer: NavViewer): boolean {
  if (permission === 'super_admin') return viewer.isSuperAdmin
  // A super admin administers organizations, which does not by itself grant org
  // administration -- `RequireAdmin` reads is_org_admin, so this must too.
  if (permission === 'org_admin') return viewer.isOrgAdmin
  return true
}

/**
 * The sections this viewer may see, with entries they may not already removed.
 * A section whose items are all filtered out disappears with them -- a heading
 * over nothing is noise.
 */
export function visibleSections(viewer: NavViewer): NavSection[] {
  return NAVIGATION
    .filter(s => canSee(s.permission, viewer))
    .map(s => ({ ...s, items: s.items.filter(i => canSee(i.permission, viewer)) }))
    .filter(s => s.items.length > 0)
}
