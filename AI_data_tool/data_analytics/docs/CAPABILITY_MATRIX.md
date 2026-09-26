# Capability matrix

Who may open, read and change what. This is the rule `app/core/capability.py`
implements; `backend/tests/test_capability_matrix.py` rebuilds the scenario
below and checks every cell of the first table against the code, so the table
cannot drift from it.

Three separate questions are answered for every request, in this order:

1. **Organization.** Anything in another organization does not exist for you:
   404, even for that organization's admin.
2. **Access.** May you open this object at all? That is the matrix below.
   Refusals are 404, never 403, so a refusal never confirms that an id exists.
   403 is kept for "you can see it, but not do this", for example a viewer
   trying to edit, or a non-admin on an admin-only action.
3. **Rows and columns.** Once you may read a dataset, your role's row rule
   (`RowSecurityRule`) and column rule (`ColumnSecurityRule`) decide what you
   see of it. They apply however you reached the dataset: as its owner, through
   a share, or through a dashboard. Only organization admins bypass them.

## The scenario

Olivia (a member) owns dataset **D** and dataset **E**. Her unpublished draft
report **R** is built on D. Her published report **P** is built on E. Nobody
else has touched any of them unless the row says so.

<!-- matrix:start -->
| Actor | Read D | Edit D's model | Open R | Open P | Read E |
|---|---|---|---|---|---|
| Organization admin | yes | yes | data | data | yes |
| Olivia, the owner | yes | yes | data | data | yes |
| Colleague with a DatasetShare on D | yes | yes | none | view | yes |
| Colleague with a 'view' grant on R | yes | yes | view | view | yes |
| Colleague with no grant | no | no | none | view | yes |
| Admin of another organization | no | no | none | none | no |
<!-- matrix:end -->

How to read it:

- **Read D** is `can_read_dataset`: every data surface (preview, export,
  widget data, analyses, statistics, previews of expressions, column
  statistics, Ask AI, the semantic API) asks it first. The cross-surface suite
  `backend/tests/test_security_surfaces.py` walks every one of them.
- **Edit D's model** is `require_dataset_capability(..., "data")`: calculated
  columns, measures, prep steps, the default filter, the drill hierarchy,
  aggregates. It asks Read D first, then your role's level on the reports
  built on D. With no `ReportCapability` row for your role it is open, so
  anyone who can read a dataset can change its model unless an admin restricts
  their role on **every** report built on it.
- **Open R / Open P** is `effective_capability`: `none` (404), `view`, `edit`
  or `data`.
- **Read E** shows the dashboard rung: a report you can open opens the data it
  draws, but only data its **author** can read. A report cannot become a way
  into a dataset its author was never given.

## The rungs, in order

**Dataset read** (`can_read_dataset`, `readable_dataset_ids`):

1. Organization admin: every dataset in the organization.
2. Owner (`Dataset.created_by`).
3. A `DatasetShare` naming you.
4. A report you can open (capability other than `none`) that draws the
   dataset (as its primary dataset, an additional dataset, or a widget's own
   `dataset_id`), limited to what that report's author can read directly.
   When the report has a release (E09), a reader who holds only `view` is
   served the release, so it is the RELEASE's datasets this rung opens to
   them, not ones the draft has added since; editors read the draft's and the
   release's.
5. An unowned dataset (`created_by` is NULL): readable by every member. Only
   rows from before ownership existed, and seeded demo content, are unowned.
   Everything the app creates is owned by the person who created it: uploads,
   combines, imports, aggregates, materialized copies and dataflow outputs.

**Report capability** (`effective_capability`), best first:

1. Organization admin: `data`.
2. Author (`Report.created_by`): `data`.
3. A per-user grant (`ReportUserGrant`): its level, even when it is lower
   than what publication would give.
4. A workspace folder grant over the report: its level. Sharing a folder
   publishes what is in it to the people it is shared with.
5. Published (or unowned): your role's `ReportCapability` row, or `view`.
6. Otherwise `none`.

**Dataflows** (`effective_dataflow_capability`): admin `data`; otherwise your
role's row; with no row, `view` if the flow has any grants and `data` if it has
none.

**Releases** (E09, `services/report_release.py`): a reader with `view` on a
report that has a release is served the release -- in `GET /reports/{id}`,
the report list, a PDF and the offline package -- and so are guest links,
embeds and scheduled deliveries. A release is frozen content, never frozen
access: a page restricted when it was released stays restricted after the
draft deletes it, and a restriction added since applies too. Releasing needs
`edit`; on a published report, the organization's publish gate applies. Pinned Home tiles are served under the same rules: a pin on a report the reader can no longer open is not served, and a viewer's pin shows the released widget.

## Connections and imports

- **Seeing a connection** (`_visible_source_ids`): admins see all. Members see
  the ones they added, unowned ones, and any that back a dataset they can read.
  The configuration comes back with secrets redacted.
- **Changing or testing a connection**: an admin, or the person who added it.
- **Reading a source directly** (table preview, the query builder's preview,
  import, import jobs): admins only. There is no dataset between the source
  and the caller, so there is no row or column rule to apply.
- **Schema and table lists**: any member who can see the connection. These are
  names, not values.

## Everything that runs as someone else

| Surface | Runs as | Checked when it runs |
|---|---|---|
| Scheduled delivery (PDF, digest) | the schedule's creator | the creator's report view and dataset read; each widget's dataset is read through the report |
| Run a schedule now, delete a schedule | the caller | edit on the report the schedule belongs to |
| Data alert | the alert's creator | dataset read, row and column rules at every check |
| Share link | the signed-in viewer if they are in the same organization, otherwise the link's creator | read, row and column rules on every widget request |
| Embed | the embed configuration's creator | read, row and column rules on every widget request |
| Queued import (job) | the person who queued it | still an admin, the connection still exists |
| Ask AI | the person asking | dataset read (or connection visibility) on every question, not only when the conversation starts |

## Admin-only

Row rules, column rules, dataset shares, export policy, users and roles,
connection imports and previews. A non-admin gets 403 on these before any
lookup, so the answer says nothing about whether the object exists.

## Known limits

- **Ask AI over a connection** applies `ObjectRowPolicy` and the column rules
  of datasets bound to that connection, but not dataset `RowSecurityRule`s.
  A connection-scoped conversation is therefore an admin-grade tool unless
  object row policies are set.
- **Column statistics** are computed over the whole table. For a caller whose
  rows are filtered, the value-bearing figures (top values, minimum, maximum,
  distinct count) are withheld rather than recomputed.
