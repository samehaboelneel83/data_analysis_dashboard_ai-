"""Write the live identity map to an Excel workbook (demo passwords included)."""
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "datalytics-users-and-privileges.xlsx"
OUT.parent.mkdir(parents=True, exist_ok=True)

# Seeded password for every account in this database. Hashes are not reversible;
# these are the values from seed_dev_accounts.py, demo_up.ps1, and demo_use_cases.py.
PASSWORD = "demo-password"

HEADER_FILL = PatternFill("solid", fgColor="1D4ED8")
HEADER_FONT = Font(bold=True, color="FFFFFF")
ADMIN_FILL = PatternFill("solid", fgColor="DBEAFE")
MEMBER_FILL = PatternFill("solid", fgColor="F8FAFC")
NOTE_FILL = PatternFill("solid", fgColor="FEF3C7")
THIN = Border(
    left=Side(style="thin", color="E2E8F0"),
    right=Side(style="thin", color="E2E8F0"),
    top=Side(style="thin", color="E2E8F0"),
    bottom=Side(style="thin", color="E2E8F0"),
)
WRAP = Alignment(wrap_text=True, vertical="top")


def style_header(ws: Worksheet, ncols: int) -> None:
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col in range(1, ncols + 1):
        cell = ws.cell(1, col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center")


def autosize(ws: Worksheet, widths: dict[int, int]) -> None:
    for col, width in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = width


def write_rows(ws: Worksheet, headers: list[str], rows: list[list], fills: list[PatternFill] | None = None) -> None:
    ws.append(headers)
    for i, row in enumerate(rows):
        ws.append(row)
        fill = fills[i] if fills else MEMBER_FILL
        for col in range(1, len(headers) + 1):
            cell = ws.cell(i + 2, col)
            cell.fill = fill
            cell.border = THIN
            cell.alignment = WRAP
    style_header(ws, len(headers))


wb = Workbook()

# ── Users (main sheet) ──────────────────────────────────────────────────────
users = [
    [8, "admin@datalytics.local", PASSWORD, "Default Organization", "Platform Admin",
     "Yes", "Yes", "Yes", "None",
     "Full org admin + platform super-admin (Organizations, quotas, org tree). Sees Admin, Monitoring, Platform.",
     "seed_dev_accounts.py"],
    [1, "admin@example.invalid", PASSWORD, "Default Organization", "Admin",
     "Yes", "Yes", "No", "None",
     "Org admin for Default Organization (first bootstrap from demo_up.ps1). Same org powers as Platform Admin except Platform menu.",
     "demo_up.ps1"],
    [25, "demo-emea@example.invalid", PASSWORD, "Default Organization", "Demo — EMEA analyst",
     "Yes", "No", "No", "None",
     "Member. Demo — Sales: only region=Europe rows (the dataset's EMEA-equivalent value); column cost hidden. Use cases folder visible; Widget gallery visible. No Admin/Monitoring.",
     "Load demo content"],
    [26, "demo-global@example.invalid", PASSWORD, "Default Organization", "Demo — Global analyst",
     "Yes", "No", "No", "None",
     "Member. Demo — Sales: all rows and columns. Widget gallery visible; Use cases folder hidden (role lock). No Admin/Monitoring.",
     "Load demo content"],
    [9, "admin@contoso.invalid", PASSWORD, "Contoso Ltd", "Admin",
     "Yes", "Yes", "No", "None",
     "Org admin for Contoso only. Cannot see Default Organization or Northwind data.",
     "seed_dev_accounts.py"],
    [10, "analyst@contoso.invalid", PASSWORD, "Contoso Ltd", "Analyst",
     "Yes", "No", "No", "Sales Team (under Sales)",
     "Member of Contoso. Placed on org-chart unit Sales Team (hierarchical row security / MYSCOPE). No Admin menu.",
     "seed_dev_accounts.py"],
    [11, "admin@northwind.invalid", PASSWORD, "Northwind Trading", "Admin",
     "Yes", "Yes", "No", "None",
     "Org admin for Northwind only. Cannot see other organizations' data.",
     "seed_dev_accounts.py"],
    [12, "analyst@northwind.invalid", PASSWORD, "Northwind Trading", "Analyst",
     "Yes", "No", "No", "None",
     "Member of Northwind. No org-unit placement. No Admin menu.",
     "seed_dev_accounts.py"],
]
user_fills = [
    ADMIN_FILL if row[6] == "Yes" else MEMBER_FILL for row in users
]

ws = wb.active
ws.title = "Users"
write_rows(ws, [
    "User ID", "Email (login)", "Password", "Organization", "Role",
    "Active", "Org admin", "Platform super-admin", "Org unit / team",
    "Privileges and notes", "How created",
], users, user_fills)
autosize(ws, {1: 10, 2: 32, 3: 16, 4: 24, 5: 24, 6: 10, 7: 12, 8: 22, 9: 28, 10: 72, 11: 22})
ws.row_dimensions[1].height = 22
for r in range(2, 10):
    ws.row_dimensions[r].height = 48

# ── How to read this ────────────────────────────────────────────────────────
how = wb.create_sheet("How to read this")
how["A1"] = "How identity works in Datalytics"
how["A1"].font = Font(bold=True, size=14)
how.merge_cells("A1:B1")
lines = [
    ("Organization",
     "A company / tenant. Users, datasets and dashboards never mix across orgs."),
    ("Role",
     "One permission pack per user, inside that org. Org admin = Users/Roles/security/monitoring. Member = use data and dashboards only."),
    ("Platform super-admin",
     "Not a role. Emails listed in SUPER_ADMIN_EMAILS (default: admin@datalytics.local). Opens Platform → Organizations."),
    ("Org unit / team",
     "Seat on the company chart (Country → Region → Team). Used for hierarchical row security (MYSCOPE), not for login. Most users have none."),
    ("Password",
     "Every account below was seeded with demo-password. The database stores hashes only; this sheet records the known seed password, not recovered hashes."),
    ("Workspaces",
     "Unlocked folders are visible to the whole org. A lock restricts the menu to listed roles. That is separate from dashboard publish/share."),
    ("App URL",
     "http://localhost:3001  (API http://localhost:8000)"),
]
how.append(["Concept", "Meaning"])
for concept, meaning in lines:
    how.append([concept, meaning])
style_header(how, 2)
for r in range(2, 9):
    how.cell(r, 1).fill = NOTE_FILL
    how.cell(r, 1).border = THIN
    how.cell(r, 2).fill = MEMBER_FILL
    how.cell(r, 2).border = THIN
    how.cell(r, 2).alignment = WRAP
    how.row_dimensions[r].height = 36
autosize(how, {1: 24, 2: 100})
how["A10"] = "Exported from the running Postgres on 2026-09-05. Re-run this script after seeding if accounts change."
how["A10"].font = Font(italic=True, color="64748B")
how.merge_cells("A10:B10")

# ── Organizations ───────────────────────────────────────────────────────────
orgs = wb.create_sheet("Organizations")
write_rows(orgs, ["Org ID", "Name", "What it is", "Users"], [
    [1, "Default Organization", "Main tenant (created at first startup). Demo content and your admin work live here.",
     "admin@datalytics.local, admin@example.invalid, demo-emea@…, demo-global@…"],
    [2, "Contoso Ltd", "Separate company from seed_dev_accounts.py. Isolated data.",
     "admin@contoso.invalid, analyst@contoso.invalid"],
    [3, "Northwind Trading", "Separate company from seed_dev_accounts.py. Isolated data.",
     "admin@northwind.invalid, analyst@northwind.invalid"],
], [ADMIN_FILL, MEMBER_FILL, MEMBER_FILL])
autosize(orgs, {1: 10, 2: 24, 3: 80, 4: 70})

# ── Roles ───────────────────────────────────────────────────────────────────
roles = wb.create_sheet("Roles")
write_rows(roles, ["Role ID", "Organization", "Role name", "Org admin", "What it can do"], [
    [1, "Default Organization", "Admin", "Yes", "Full org administration"],
    [8, "Default Organization", "Platform Admin", "Yes", "Full org administration; user also on super-admin allowlist"],
    [29, "Default Organization", "Demo — EMEA analyst", "No", "Member + RLS: Europe rows only, no cost column; can see Use cases folder"],
    [30, "Default Organization", "Demo — Global analyst", "No", "Member; all demo sales rows; cannot see Use cases folder"],
    [9, "Contoso Ltd", "Admin", "Yes", "Full Contoso administration"],
    [10, "Contoso Ltd", "Analyst", "No", "Contoso member"],
    [13, "Contoso Ltd", "Demo — EMEA analyst", "No", "Role exists from a demo seed in this org; no user attached"],
    [14, "Contoso Ltd", "Demo — Global analyst", "No", "Role exists from a demo seed in this org; no user attached"],
    [11, "Northwind Trading", "Admin", "Yes", "Full Northwind administration"],
    [12, "Northwind Trading", "Analyst", "No", "Northwind member"],
    [15, "Northwind Trading", "Demo — EMEA analyst", "No", "Role exists from a demo seed in this org; no user attached"],
    [16, "Northwind Trading", "Demo — Global analyst", "No", "Role exists from a demo seed in this org; no user attached"],
])
autosize(roles, {1: 10, 2: 24, 3: 26, 4: 12, 5: 72})

# ── Org chart ───────────────────────────────────────────────────────────────
chart = wb.create_sheet("Org chart (units)")
write_rows(chart, ["Unit ID", "Organization", "Level", "Name", "Match value (in data)", "Parent", "Who sits here"], [
    [1, "Default Organization", "Country", "Egypt", "Egypt", "", "Nobody assigned"],
    [2, "Default Organization", "Region", "Alexandria", "Alexandria", "Egypt", "Nobody assigned"],
    [3, "Default Organization", "Department", "Engineering", "Engineering", "Alexandria", "Nobody assigned"],
    [4, "Default Organization", "Team", "Software", "Software", "Engineering", "Nobody assigned"],
    [5, "Default Organization", "Team", "Network", "Network", "Engineering", "Nobody assigned"],
    [6, "Default Organization", "Team", "Infrastructure", "Infrastructure", "Engineering", "Nobody assigned"],
    [7, "Default Organization", "Region", "Cairo", "Cairo", "Egypt", "Nobody assigned"],
    [8, "Contoso Ltd", "", "Sales", "Sales", "", "Nobody assigned at this node"],
    [9, "Contoso Ltd", "", "Sales Team", "Sales Team", "Sales", "analyst@contoso.invalid"],
])
autosize(chart, {1: 10, 2: 24, 3: 14, 4: 16, 5: 22, 6: 16, 7: 28})

# ── Data restrictions ───────────────────────────────────────────────────────
sec = wb.create_sheet("Data restrictions")
write_rows(sec, ["Organization", "Role", "Dataset", "Row filter", "Hidden columns"], [
    ["Default Organization", "Demo — EMEA analyst", "Demo — Sales", "region == 'Europe'", "cost"],
], [NOTE_FILL])
autosize(sec, {1: 24, 2: 24, 3: 16, 4: 22, 5: 18})
sec["A4"] = "All other roles/users have no row or column security rules stored."
sec["A4"].font = Font(italic=True, color="64748B")

# ── Privilege matrix ────────────────────────────────────────────────────────
mx = wb.create_sheet("Privilege matrix")
write_rows(mx, [
    "Capability",
    "Org admin (Admin / Platform Admin)",
    "Analyst / demo analysts",
    "Platform super-admin only",
], [
    ["Sign in and use Home, Datasets, Ask AI, Dashboards", "Yes", "Yes", "—"],
    ["Admin menu (users, roles, org chart, RLS, SSO, audit)", "Yes", "No", "—"],
    ["Monitoring (jobs, deliveries, activity)", "Yes", "No", "—"],
    ["Platform → Organizations", "No (unless email is on allowlist)", "No", "Yes"],
    ["See other organizations' data", "No", "No", "Manage tenants, not their datasets from this login"],
    ["Row/column security applies", "Bypassed", "Yes, if a rule exists for the role", "Bypassed inside their own org"],
    ["Unlocked workspace folders in the org", "Yes", "Yes (menu visibility)", "Yes"],
    ["Locked folders (e.g. Use cases)", "Yes (admins always see locks)", "Only if their role is on the lock", "Yes in their org"],
])
autosize(mx, {1: 52, 2: 36, 3: 36, 4: 42})
for r in range(2, 10):
    mx.row_dimensions[r].height = 32

wb.save(OUT)
print(OUT)
