# Data Model and State Model

> Part of the Visual Analytics reverse-engineering deliverable. Sibling files: `application-map.md`, `screens.md`, `activities.md`, `components.md`, `visualizations.md`, `data-model.md`, `interaction-model.md`, `design-system.md`, `implementation-spec.md`, `screenshots/`.
> **Evidence labels:** OBSERVED (seen in the running app) · INFERRED — confidence High/Medium/Low · DOCUMENTED (vendor training material, not re-verified) · UNKNOWN.

## I. Data Model (conceptual, from observable behaviour)

```
User ──owns──> Report ──has──> Page ──has──> Object ──has──> RoleAssignment ──references──> DataItem
                  │               │             ├──has──> Filter ├──has──> Rank
                  │               │             ├──has──> DisplayRule
                  │               │             └──has──> Action (ObjectLink | PageLink | ReportLink | UrlLink | ParameterLink)
                  │               └──has──> Control (report-level controls attach to Report)
                  ├──uses──> DataSource ──exposes──> DataItem (Category | Measure | AggregatedMeasure | Date | Geography | Hierarchy | CustomCategory | CalculatedItem | Parameter | Partition)
                  ├──has──> CommonFilter
                  ├──has──> Theme/Style
                  └──has──> PageTemplate (report-scoped save target)
```

| Entity | Observed attributes | Relationships | Create | Edit | Delete | States |
|---|---|---|---|---|---|---|
| Report | name, location (after save), summary, thumbnail object, created/modified by+date, viewer customization level, insights allowed, export policy, fixed size, theme, palettes, persistence flag | 1..n Page, 0..n DataSource, 0..n CommonFilter | New report | Editor | Close (confirm) / Recycle Bin | Unsaved → Saved → Modified; Editing ↔ Viewing |
| Page | name (required), type (Basic/Hidden/Pop-up), padding, direction (vertical default), avoid scrollbars, control placement, visibility limits | belongs to Report; 0..n Object, 0..n Control | "+" / template | Options, ⋮ | Delete (needs ≥2 pages) | Basic / Hidden / Pop-up |
| Object | name (auto, follows data), title mode (Automatic/Custom/None), alt text, selection enabled, data limit override, reload flag, style, layout flags | belongs to Page; has roles, filters, ranks, rules, actions | Objects pane / data item / template / suggestion / convert | Right rail + context menus | Delete / Undo | Placeholder → Configured → Rendered → Capped / Empty / Error |
| DataSource | name, table, library, row count, columns, modified metadata | belongs to Report; exposes DataItem | Add data / Import / Join / Aggregation | Replace, Refresh, Edit aggregated data | Remove | Loaded / Loading / Failed (join timeout) |
| DataItem | label, **name-in-data** (the physical column — both halves are shown on the item’s hover card, with distinct count and format), classification (Category/Geography/Measure), format, aggregation default, distinct count, **sensitivity flag** (a quasi-identifier badge whose hover text reads *"… includes information that might identify an individual when combined with other information"*, **inherited by derived items**), outlier flag, expression, "used by" list | belongs to DataSource | Auto on load, or + New data item | Edit properties (inline) | Hide / Delete (varies) | — |
| **GeographyItem** | name, **basedOn** (any DataItem — the picker is not type-filtered), **source** = `nameOrCodeLookup` \| `provider` \| `latLong`, plus per-source fields: *lookup* → one of ten **contexts** (country names / ISO 2, 3, numeric / SAS map IDs / subdivision names / subdivision map IDs / US state names / US state abbreviations / US ZIP); *provider* → registered provider + ID column + optional lat/long; *latLong* → latitude column, longitude column, **coordinate space** (Web Mercator \| WGS84 \| OSGB36 \| Singapore Transverse Mercator \| Custom PROJ string). Derived at create time: **mappedPercent**, **unmappedValues[]**, and which **layer families** it can serve (point \| region) | a DataItem subtype, in its own **Geography** group in the Data pane; inherits the source item's sensitivity flag | New data item ▸ Geography item | the same dialog | delete | Unconfigured / Validating / `N% mapped` / provider-missing (renders nothing — defect 65) |
| CalculatedItem | name, expression, auto-detected format, optional Scope (Custom intersection / Grand total) | a DataItem subtype | dialog | dialog | delete | Valid / Invalid (blocks OK) |
| Parameter | name, type (Character/Numeric/Date/Datetime), multiple values, include missing, format, default (literal or expression) | referenced by controls, filters, calculations | dialog | dialog | delete | — |
| Filter | target item, condition type, values/range, include-missing, detail vs aggregated, continuous vs discrete, inverted | on Object; CommonFilter is report-scoped | Filters pane | card + ⋮ | Delete filter | Active / Reset / Empty-result |
| Rank | category, subset (Top/Bottom × count/percent), count, rank-by measure, ties, All Other | on Object | Ranks pane | card | trash | — |
| DisplayRule | label, target, operator, value (constant or measure), style, intersections, alerts flag | on Object (scoped Object or Measure) | dialog | pencil | trash | — |
| Action/Link | type (Filter / Linked selection / Page / Report / URL / Parameter), source, target, options | on Object or Page | Actions pane | checkbox + ⋮ | untick | — |
| Control | control type, roles, required, initial value, multi-select, search, missing option, placement scope (report/page/body) | on Report or Page | drag to strip | Options | delete | Empty / Selected / Required-unset |
| DataView *(DOCUMENTED)* | reusable data-item customizations bound to a source, shareable between users | belongs to DataSource | Save data view | Manage data views | delete | — |
| DataSourceMapping *(DOCUMENTED)* | pairs of corresponding items across two sources; formats must match | between two DataSources | Map data | Map data | delete | — |

**UNKNOWN:** persistence format of a saved report, permission model beyond the observed "Limit visibility to specified users", versioning, concurrent editing, and how common filters are stored.

---

## J. State Model

**Report**
```
New(unsaved) ──edit──> Modified ──Save──> Saved ──edit──> Modified
     │                                   │
     └──Close──> [Save? / Don't save? / Cancel]
Saved ──Close──> closed ; any state ──session loss──> Recoverable ──Restore──> reopened
```
Capabilities gated by `Saved`: Export, Share, Copy link, Copy embeddable markup, Distribute, Localize, Comments, Evaluate Performance, page Export/Copy link/Save as template, About this report.

**Object**
```
Inserted(placeholder, synthetic sample data)
   → RolesPartial (required role unfilled → still placeholder)
   → Querying ("Loading…")
   → Rendered
        ├─ RowCapped   (ⓘ "Only N rows of the data appear.")
        ├─ TieCapped   (ⓘ "…too many ties associated with the rank.")
        ├─ EmptyResult ("No data matches the current filters.")
        └─ Refused     (e.g. Model comparison: "No Comparable Models")
   → Maximized ↔ Restored
   → Deleted (undoable)
```

**Page:** `Basic ↔ Hidden ↔ Pop-up` (Hidden/Pop-up require ≥2 pages; both undo as "Hide page").

**Editor mode:** `Editing ↔ Viewing` (rails hidden, menus differ, AI icon disappears, selections carry over).

**Expression:** `Empty → Invalid(n errors, OK greyed) ↔ Valid(OK enabled)`; the preview grid keeps the **last valid** result while invalid.

**Automatic actions mode:** `Off → One-way ↔ Two-way ↔ LinkedSelection`; entering any mode destroys manual object links; every transition clears control selections.
