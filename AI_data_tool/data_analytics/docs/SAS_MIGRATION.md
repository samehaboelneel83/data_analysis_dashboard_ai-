# Moving reports off SAS: the migration inventory

**Migration** (left rail, under Analyse) is the ledger for a move off SAS. Each item is one thing in the old estate: a report, program, stored process, job or dataset. For each item it records what replaces it, the evidence that the replacement gives the same answers, and the owner's sign-off.

## 1. Build the inventory (an org admin)

- **Import a CSV.** Put one row per item and include a `Name` column. The import also reads `Type`, `Owner` (the user's email), `Folder` (or `Path`), `Datalytics report` (a report id or its exact name) and `Notes` when present. It detects the separator (comma, semicolon or tab). If a row's owner isn't an active user, the item is added without an owner and the import tells you. A row whose name is already in the inventory is skipped, and the import tells you that too.
- **Import SAS programs.** Each `.sas` file becomes an item. The import scans each program for the SAS constructs it uses: PROCs, DATA steps, macros, ODS destinations, LIBNAMEs and OS commands. Comments are removed before the scan. Each construct is then mapped to its Datalytics equivalent. Importing a program whose name is already in the inventory rescans it.
- Admins can also add items one at a time, and can rename items, change their owner or delete them.

The **feature map** at the bottom of the page lists everything the scanner recognises. For each construct it shows the Datalytics replacement and how well it fits:
- **Built in**: a Datalytics feature does the same job.
- **Partly**: the note says what is not covered.
- **By hand**: there is no equivalent.

A PROC the map doesn't cover is listed by name as *By hand*. The scan never drops a construct it doesn't recognise.

## 2. Map, compare, sign off (the item's owner)

1. **Link** the Datalytics report that replaces the item.
2. Open that report and choose **⇄ Reconcile with an export…** on each widget. Pick the old report's CSV or Excel export and keep the result on the item. The item keeps the latest comparison for each widget.
3. **Sign off.** A sign-off records its basis:
   - *Every comparison agreed.*
   - *Differences accepted.* You must tick the box and write a note saying why.
   - *Nothing to compare.* This applies to a job or dataset, and needs a note.

   A report item cannot be signed off until it has been compared.

Only the named owner can sign off. An admin can withdraw a sign-off. If the owner changes, or the item is linked to a different report, the sign-off is withdrawn. It is also withdrawn if a comparison recorded after sign-off disagrees. If the report is edited after sign-off, the item shows *Report changed since*.

To retire an item instead of migrating it, write a note saying why and choose **Retire it**.

## Status

The status is worked out from the evidence and is never stored:

| Status | Meaning |
|---|---|
| Not mapped | No replacement is linked. |
| Mapped | A report is linked but has not been compared yet. |
| Differences | At least one comparison with the linked report disagreed. |
| Reconciled | Every comparison with the linked report agreed. |
| Signed off | The owner signed off on the linked report. |
| Retired | The item will not be migrated. |

Every change is recorded in the audit trail (`migration.*`).
