# Google Sheets Persistence Design

## 1. Purpose

Google Sheets will be the MVP operational record for completed FarmDidi daily production check-ins.

This phase defines the persistence contract only. It does not connect to Google, install API packages, create credentials, or write rows.

The intended flow is:

```text
Didi conversation
      |
      v
Validation
      |
      v
Confirmation: Yes
      |
      v
COMPLETE and confirmed=True
      |
      v
CheckInRecord
      |
      v
Google Sheets row
```

Only confirmed completed check-ins may reach the sheet.

---

## 2. Sheet and Tab Name

The Google spreadsheet may use a workbook named:

```text
FarmDidi Daily Check-ins
```

The operational worksheet/tab should be named:

```text
Daily Check-ins
```

The tab name is a simple MVP convention and can be configured later through an environment variable if the business chooses a different spreadsheet.

---

## 3. Column Order

The sheet must use these columns in this exact order:

| Position | Column |
|---:|---|
| 1 | Date |
| 2 | Didi ID |
| 3 | Didi Name |
| 4 | Production Status |
| 5 | Product |
| 6 | Quantity |
| 7 | Unit |
| 8 | Has Issue |
| 9 | Issue Type |
| 10 | Issue |
| 11 | Issue Details |
| 12 | Status |

The first row should contain the headers:

```text
Date | Didi ID | Didi Name | Production Status | Product | Quantity | Unit | Has Issue | Issue Type | Issue | Issue Details | Status
```

No analytics, dashboard, severity, escalation, owner, timestamp, or workflow columns are added in this design step.

---

## 4. `CheckInRecord` Mapping

The existing `CheckInRecord` is the source of truth for a row. Each confirmed record becomes one row, with fields mapped as follows:

| Sheet column | `CheckInRecord` field | Mapping rule |
|---|---|---|
| Date | `date` | Write the record date as the agreed date string, currently `YYYY-MM-DD` in examples. |
| Didi ID | `didi_id` | Write the Didi's known catalog ID, such as `D001`. |
| Didi Name | `didi_name` | Write the name stored in the confirmed record. |
| Production Status | `production_status` | Write the normalized status, such as `planned`, `completed`, or `none`. |
| Product | `product` | Write the catalog product name, or blank when production status is `none`. |
| Quantity | `quantity` | Write the numeric quantity, or blank when there is no production. |
| Unit | `unit` | Write the normalized unit, currently `kg` for the demo achar catalog. |
| Has Issue | `has_issue` | Write a boolean representation consistently, such as `TRUE` or `FALSE`. |
| Issue Type | `issue_type` | Write the normalized issue category, or blank when there is no issue. |
| Issue | `issue` | Write the structured issue description, or blank when there is no issue. |
| Issue Details | `issue_details` | Write additional issue details, or blank when there are none. |
| Status | `status` | Write `confirmed` for a persisted completed record. |

### Example row

For a confirmed session containing Meena's 25 kg Mango Achar production and a bottle shortage:

```text
2026-09-09 | D001 | Meena | planned | Mango Achar | 25 | kg | TRUE | inventory | Bottle shortage | Only 30 bottles available | confirmed
```

The row should contain values from the final confirmed `CheckInRecord`, not raw LLM output and not an unvalidated session snapshot.

---

## 5. Persistence Gate

A row may be written only when both conditions are true:

```text
session.state == COMPLETE
session.confirmed is True
```

The persistence layer should also receive or construct a valid `CheckInRecord` from the final session data before writing.

The following must never be written:

- Incomplete records.
- Invalid records.
- Sessions in `ASK_PRODUCTION`.
- Sessions in `ASK_ISSUE`.
- Sessions in `CONFIRM`.
- Sessions in `AWAITING_CORRECTION`.
- Unconfirmed records.
- Parser output that has not passed validation.
- Candidate correction data before the Didi confirms it.

`COMPLETE` means the session is confirmed and ready for persistence. It does not itself perform the Google Sheets write in this design step.

---

## 6. One Row per Completed Check-in

The MVP operational rule is one row per completed daily check-in for a Didi.

The future writer should append or update only after the confirmation gate has passed. It should not create rows for every conversation message or every correction attempt.

A correction before confirmation changes the in-memory candidate data. Only the final confirmed version should become the operational row.

---

## 7. Duplicate-Prevention Design

The future uniqueness key is:

```text
didi_id + date
```

For example:

```text
D001 + 2026-09-09
```

This means the MVP should normally have at most one daily operational row per Didi.

No duplicate-handling implementation is added in this phase. When persistence is implemented, the writer should use this key to check whether a row already exists before appending a new one. The later implementation must decide whether an existing row is rejected, updated, or treated as already persisted; that policy is intentionally not chosen here.

The key must be based on the final record's `didi_id` and `date`, not on a transient session ID.

---

## 8. Empty Values and Formatting

For optional fields that do not apply, the writer should use blank sheet cells rather than invented text.

Examples:

- No production: blank Product, Quantity, and Unit cells.
- No issue: blank Issue Type, Issue, and Issue Details cells.
- Issue with no additional details: blank Issue Details cell.

The writer should preserve numeric quantity as a numeric sheet value where the Google Sheets API allows it, rather than embedding the unit in the quantity cell. The unit remains in the separate Unit column.

Boolean `Has Issue` values should use one consistent representation. `TRUE` and `FALSE` are the preferred sheet values for the MVP.

---

## 9. Security and Credentials

Google credentials must never be committed to source control or pasted into application code.

When the integration is implemented:

- Keep service-account credentials outside source files.
- Use environment variables or secure local configuration for identifiers and secret paths.
- Keep `.env` ignored by Git.
- Do not expose credentials in API responses, logs, frontend code, or error messages.
- Use the minimum Google Sheets permissions needed by the writer.
- Document required environment variable names without documenting secret values.

No credentials or Google API packages are added in Phase 8 Step 1.

---

## 10. Scope Boundary

This document defines the persistence shape only. It does not implement:

- Google authentication.
- Service-account setup.
- Google Sheets API calls.
- Spreadsheet creation.
- Header creation through the API.
- Row append or update behavior.
- Duplicate detection code.
- Retry handling.
- Offline queues.
- Scheduler integration.
- Dashboard queries.
- Issue-management workflows.

Those belong to later phases.

---

## 11. Phase 8 Step 1 Completion Contract

Before implementing the Google Sheets connection, the project agrees on:

1. Operational worksheet: `Daily Check-ins`.
2. One row per completed check-in.
3. Twelve columns in the documented order.
4. `CheckInRecord` as the row source of truth.
5. Only `COMPLETE` plus `confirmed=True` can be persisted.
6. Future duplicate key: `didi_id + date`.
7. Credentials remain outside source code and use secure configuration.

No application behavior was changed by this design step.
