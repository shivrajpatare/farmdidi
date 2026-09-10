# Issue Management Design (MVP)

## 1. Purpose

The FarmDidi Daily Production Check-in system captures operational bottlenecks during daily check-ins (e.g., bottle shortages, machine breakdowns, raw material delays).

Capturing issues is only valuable if the business can act upon them. This document defines the MVP issue-management model by answering:

> **What happens to a reported issue after it is recorded?**

The goal is to provide a lightweight, closed-loop operational workflow:
- The Didi reports an issue.
- The issue is validated and confirmed during check-in.
- An operational record is logged as **`open`**.
- The FarmDidi operations team addresses the bottleneck and marks it **`resolved`**.

This establishes an actionable trail without burdening the MVP with a complex enterprise ticketing system.

---

## 2. Issue Lifecycle

```text
               Didi Check-in Conversation
                           │
                           ▼
                 Issue Mentioned & Validated
                           │
                           ▼
                  Check-in Confirmation
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
      has_issue = false           has_issue = true
             │                           │
             ▼                           ▼
     Check-in Saved              Check-in Saved
   (No issue created)                  │
                                       ▼
                              Issue Created: OPEN
                                       │
                                       ▼
                              [FarmDidi Operations
                               Team Resolves Problem]
                                       │
                                       ▼
                                Status: RESOLVED
```

---

## 3. Creation Rules

### When an Issue Is Created
An issue record is created **only** when all of the following conditions are met:
1. **`has_issue == true`**: The Didi reported a real operational issue during the check-in.
2. **`session.state == ConversationState.COMPLETE`**: The check-in conversation has finished.
3. **`session.confirmed == True`**: The Didi explicitly confirmed the check-in (`"Yes, correct"`).
4. **Issue fields are validated**: `issue_type` and `issue` are non-empty and validated.

### When an Issue Is NOT Created
No issue record is created if:
1. **`has_issue == false`**: The Didi stated that everything is fine (e.g., *"Koi dikkat nahi hai"*, *"Sab theek hai"*).
2. **Session is unconfirmed or abandoned**: The session never reached `COMPLETE` with `confirmed = True`.
3. **Correction removed the issue**: If the Didi initially reported an issue but corrected it to *"Sab theek hai"* before confirming, no issue record is created.

In all "no issue" cases, the daily check-in is still saved normally to Google Sheets with `has_issue = false`.

---

## 4. Issue Record Schema

The issue record represents a single operational problem requiring team follow-up:

| Field | Type | Required | Description | Example |
|---|---|---|---|---|
| `issue_id` | string | Yes | Unique identifier for the issue | `"ISS-20260910-D001"` |
| `date` | string | Yes | Date of the confirmed check-in (`YYYY-MM-DD`) | `"2026-09-10"` |
| `didi_id` | string | Yes | Identifier of the Didi who reported it | `"D001"` |
| `didi_name` | string | Yes | Display name of the Didi | `"Meena"` |
| `issue_type` | string | Yes | Standard category from catalog | `"inventory"` |
| `issue` | string | Yes | Short normalized issue summary | `"Bottle shortage"` |
| `issue_details` | string \| null | No | Contextual detail provided by Didi | `"Only 30 bottles available"` |
| `status` | string | Yes | Current operational status (`open` \| `resolved`) | `"open"` |
| `resolved_at` | string \| null | No | Timestamp when issue was marked resolved | `null` |
| `resolution_notes` | string \| null | No | Operational note on how problem was solved | `null` |

---

## 5. Statuses (MVP State Machine)

For the MVP, issues use strictly two statuses:

```text
┌──────────┐     Operations team solves bottleneck      ┌────────────┐
│   OPEN   │ ─────────────────────────────────────────> │  RESOLVED  │
└──────────┘                                            └────────────┘
```

1. **`open`**:
   - Initial status assigned immediately upon creation from a confirmed check-in.
   - Signifies that the bottleneck is currently active and requires team action.
2. **`resolved`**:
   - Status updated when the FarmDidi operations team has addressed the root cause (e.g., delivered bottles, arranged raw materials, repaired machines).
   - Terminal status for normal MVP flow.

No other statuses (`pending`, `in_progress`, `escalated`, `blocked`) are included in the MVP.

---

## 6. Relationship with the Daily Check-in

### Separation of Concerns
- **`CheckInRecord` (Daily Check-ins)**:
  - An **immutable historical record** representing the snapshot of what was produced and reported on a given day.
  - Does not change after confirmation.
- **`IssueRecord` (Issue Management)**:
  - A **mutable operational tracking record** representing the operational lifecycle of a problem.
  - Evolves from `open` to `resolved`.

### Sheet Integrity
- The existing 12-column **`Daily Check-ins`** Google Sheet is **NOT modified**.
- No issue-tracking columns (such as `resolved_at` or `resolution_status`) will be added to the daily check-in sheet.
- If issues are persisted to Google Sheets in future steps, they will live in a separate, dedicated worksheet (e.g. `Issues`), keeping production check-in data clean and decoupled.

---

## 7. How an Issue Becomes Resolved

1. **Operational Resolution**:
   The FarmDidi team resolves the issue in the real world (e.g. sending 50 new bottles to Meena ji).
2. **Status Update**:
   The issue's status is transitioned from `open` to `resolved` via a dedicated administrative action (API endpoint or admin operation).
3. **No Automated Guesswork**:
   Resolution is explicitly human-governed. AI does not automatically mark issues resolved, preventing false resolutions of ongoing physical bottlenecks.

---

## 8. Explicitly Excluded Features (Out of Scope for MVP)

To maintain architectural simplicity, the following enterprise ticketing features are deliberately excluded:

| Excluded Feature | Reason for Exclusion |
|---|---|
| **Full Helpdesk / Ticketing System** | Overkill for daily rural enterprise check-ins. |
| **Severity / Priority Matrices** | Not required for initial volume; all open issues are reviewed directly. |
| **SLA & Escalation Timers** | Adds time-based daemon complexity unnecessary for the MVP. |
| **Automated AI Resolution** | Risk of prematurely closing unresolved physical bottlenecks. |
| **SMS / WhatsApp / Email Alerts** | External notification infrastructure is deferred to later phases. |
| **Agent / Didi Assignment Queues** | Small operations team handles issues collectively without ticket routing. |
| **Separate Relational Database** | MVP relies on simple in-memory / Google Sheets operational tracking. |
