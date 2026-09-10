# FarmDidi Validation Rules

## 1. Purpose

This document defines the validation contract for the FarmDidi Daily Production Check-in MVP.

The current phase defines rules only. It does not implement validation code, change the conversation engine, change Groq prompts, or alter frontend behavior.

The core separation is:

```text
Groq extracts meaning
        |
        v
Python validates structure and business data
        |
        v
Conversation flow decides what happens next
```

An LLM result must never be trusted blindly. If the result is malformed, incomplete, ambiguous, or inconsistent with the demo catalog, the system must not create a final operational record from it.

This document describes demo/MVP rules only. It does not claim to represent FarmDidi's real production policy.

---

## 2. Validation Outcome Categories

Every future validation operation should distinguish these outcomes:

### VALID

The extracted data is structurally usable and meets the rules known to the MVP. It may continue to the next workflow step.

### INVALID

The data conflicts with a known structural, identity, catalog, or supported-value rule. It must not continue as submitted.

Examples:

- Unknown Didi ID.
- Inactive Didi.
- Product not present in the active catalog.
- Non-numeric quantity.
- Quantity less than or equal to zero.
- Unsupported production status.
- Unsupported issue type.

### INCOMPLETE / NEEDS CLARIFICATION

The response is understandable enough to identify the missing or ambiguous information, but it is not ready for a final record. The system should ask a clarification question rather than guess.

Examples:

- Planned production with no quantity.
- `20 ya 30 kilo`.
- Planned production with no product.
- An issue is reported but the available structured result does not provide enough detail for the workflow requirement.

A clarification result is not an invalid user or an application crash. It is a recoverable workflow state.

---

## 3. Structural Validation

Before business validation, the system should check that:

- The input object exists.
- The expected fields exist.
- The extracted data can be represented by the expected Pydantic model.
- Boolean fields are actually boolean.
- Numeric quantities are numeric.
- Enum-like values use supported normalized strings.
- A malformed AI response does not silently become a default business record.
- JSON parsing failures are treated as validation failure.

The existing models are:

- `ProductionUpdate`
- `IssueUpdate`
- `CheckInRecord`

Pydantic model construction is necessary but not sufficient. The current Pydantic models intentionally allow optional fields because incomplete responses must be representable while the conversation asks for clarification. Business validation must decide whether those optional fields are acceptable for the current workflow stage.

A structurally invalid result must not advance the conversation with invented fallback values.

---

## 4. Didi Validation

The source of truth for demo Didi identity is:

```text
backend/data/didis.json
```

A Didi is valid for a check-in only when:

1. The supplied `didi_id` exists in the file.
2. The matching record has `active: true`.

Current demo IDs are:

| ID | Name | Active |
|---|---|---|
| D001 | Meena | Yes |
| D002 | Sunita | Yes |
| D003 | Asha | Yes |
| D004 | Rekha | Yes |
| D005 | Lata | Yes |

An unknown or inactive Didi must not produce a valid production record.

No additional identity assumptions should be introduced. In particular, the validation layer must not infer identity from a name, language, phone number, or free-form message unless a later requirement explicitly defines that behavior.

---

## 5. Production Validation

The source of truth for valid products is:

```text
backend/data/products.json
```

The current active demo products are:

- Mango Achar
- Lemon Achar
- Chilli Achar
- Mixed Achar
- Garlic Achar

Product comparisons should use the normalized catalog name or a clearly defined catalog lookup. A product not found in the active catalog is invalid; the system must not silently map it to the nearest product.

### 5.1 Production status

The current production parser defines these values:

- `planned`
- `completed`
- `none`
- `unclear`

These are the exact current parser values. The earlier design discussion used `not_planned` in places, but the active implementation uses `none`; validation must document and follow the implementation value rather than silently changing it.

Interpretation for this MVP:

- `planned`: the Didi says she plans to make or is making a product.
- `completed`: the Didi explicitly says production is already completed.
- `none`: the Didi says there is no production today.
- `unclear`: the message cannot be reliably understood as a production status.

`planned` and `completed` require a known product when a production record is being prepared. `none` may have a null product and null quantity. `unclear` is not ready for a final production record and requires clarification or controlled handling.

### 5.2 Product

When production status indicates production is planned or completed:

- Product should be present.
- Product must match an active product in `products.json`.
- A missing product is incomplete.
- An unknown product is invalid.
- The validator must not invent a product from a vague message.

When production status is `none`:

- Product may be null.
- The validator must not require a product that the Didi explicitly said she is not making.

### 5.3 Quantity

When production is planned or completed and a quantity is provided:

- It must be numeric.
- It must be greater than zero.
- It must not be `NaN`.
- It must not be positive or negative infinity.

No arbitrary upper limit is defined. No minimum production quantity is defined beyond the basic numeric rule that a provided quantity must be greater than zero.

When production is planned or completed and quantity is missing:

- The result is incomplete.
- The system must ask for the quantity.
- The system must not invent a quantity.

When production status is `none`:

- Quantity may be null.
- The validator must not invent or require a quantity.

### 5.4 Unit

The current product catalog defines `kg` as the unit for every active demo product. Therefore:

- A planned or completed achar production record should use `kg`.
- An unrelated or unsupported unit is invalid for the current demo catalog.
- A missing unit may be incomplete when quantity is present.
- The validator must not silently convert an unrelated unit into `kg`.
- When production status is `none`, unit may be null.

The catalog is the source of truth. If future products support other units, the rules should be updated from the catalog rather than by adding hard-coded assumptions.

### 5.5 Ambiguous quantity

An unresolved quantity is incomplete, not valid for a final record.

Example:

```text
Aam ka achar 20 ya 30 kilo
```

The production parser is expected to return a null quantity for this case. Validation must preserve that uncertainty and return a clarification requirement such as:

```text
Production quantity is ambiguous.
```

The validator must never choose 20 or 30.

---

## 6. Issue Validation

Issue data uses the existing `IssueUpdate` model.

### 6.1 No issue

When:

```text
has_issue = false
```

the following representation is valid:

```json
{
  "has_issue": false,
  "issue_type": null,
  "issue": null,
  "details": null
}
```

Issue fields are not required when there is no issue. Any supplied issue detail alongside `has_issue: false` should not be promoted into an issue without an explicit rule; the conservative behavior is to normalize or flag the inconsistency for review rather than inventing a problem.

### 6.2 Issue present

When:

```text
has_issue = true
```

an issue has been reported. The supported normalized issue types are:

- `inventory`
- `raw_material`
- `equipment`
- `production`
- `personal`
- `other`
- `unknown`

The type must be one of these values or a safely normalized equivalent. Unknown information may use `unknown`.

The validator must not invent:

- A missing supply.
- A quantity of missing supplies.
- Severity.
- A required action.
- An escalation category.
- Details that were not communicated.

### 6.3 Vague issue

For a message such as:

```text
Thoda problem hai
```

the safe structured result is:

```json
{
  "has_issue": true,
  "issue_type": "unknown",
  "issue": null,
  "details": "Didi reported a problem but did not specify it"
}
```

This can be a valid issue presence result while the issue detail remains unknown. It must not be rewritten as a specific inventory, packaging, equipment, or personal problem without evidence.

Whether an unknown issue detail blocks final record creation is a workflow decision for the later validation implementation. The important rule is that the system must preserve the uncertainty and never hallucinate a specific issue.

---

## 7. Missing and Ambiguous Information

The following are not ready for a final operational record:

- Missing planned production quantity.
- Ambiguous production quantity.
- Missing required production product.
- Invalid product.
- Unsupported or unclear production status.
- Unsupported unit.
- Malformed structured AI output.
- Unknown Didi.
- Inactive Didi.
- Issue data that cannot be represented safely.

The future validator should return a clear reason for each case. It should not silently repair the input.

Examples:

| Input condition | Classification | Expected behavior |
|---|---|---|
| Planned production with no quantity | Incomplete | Ask for quantity |
| `20 ya 30 kilo` | Incomplete / ambiguous | Ask which quantity is correct |
| Unknown product | Invalid | Reject and request a supported product |
| Unknown Didi | Invalid | Do not create a record |
| `has_issue=false`, all issue fields null | Valid | Continue without an issue |
| `has_issue=true`, type `unknown`, no specific issue | Valid issue presence, possibly incomplete detail | Preserve unknown; do not invent |
| Malformed JSON/model data | Invalid | Fail closed and ask again or return an error |

---

## 8. Conceptual Validation Result

The future implementation should expose a small result structure rather than only returning a boolean:

```json
{
  "valid": false,
  "errors": [
    "Production quantity is missing"
  ],
  "warnings": []
}
```

A valid result:

```json
{
  "valid": true,
  "errors": [],
  "warnings": []
}
```

An ambiguous result may use the same shape while its error identifies clarification rather than a permanent rejection:

```json
{
  "valid": false,
  "errors": [
    "Production quantity is ambiguous"
  ],
  "warnings": []
}
```

The later implementation may add an explicit outcome such as `needs_clarification` if that makes the distinction clearer, but it must retain the conceptual separation between invalid data and incomplete data.

Validation errors should be safe for frontend display. They must not expose API keys, raw provider responses, stack traces, or internal request details.

---

## 9. Examples Reviewed

### Example 1: Complete valid check-in

```text
D001 + Mango Achar + 20 kg + no issue
```

Result: `VALID`, assuming the Didi is active, the product is active, the unit is `kg`, and the issue is represented as `has_issue=false` with null issue fields.

### Example 2: Missing quantity

```text
D001 + Mango Achar + missing quantity
```

Result: `INCOMPLETE / NEEDS CLARIFICATION`.

The validator must not approve this as a complete record or invent a quantity.

### Example 3: Ambiguous quantity

```text
D001 + Mango Achar + "20 or 30"
```

Result: `INCOMPLETE / AMBIGUOUS`.

The validator must not select either number.

### Example 4: Unknown product

```text
D001 + Unknown Achar
```

Result: `INVALID PRODUCT`.

The product is not in the active catalog and must not be mapped by guesswork.

### Example 5: Unknown Didi

```text
Unknown Didi ID + Mango Achar + 20 kg
```

Result: `INVALID DIDI`.

No valid production record may be created.

### Example 6: No production today

```text
production_status = "none"
product = null
quantity = null
unit = null
```

Result: `VALID` for a no-production response, assuming the Didi is valid and the structured result is otherwise well formed.

### Example 7: No issue

```text
has_issue = false
issue_type = null
issue = null
details = null
```

Result: `VALID`.

### Example 8: Unknown issue detail

```text
has_issue = true
issue_type = "unknown"
issue = null
```

Result: valid issue presence with unknown detail, subject to the later workflow decision about whether clarification is required before final confirmation. The system must not invent a specific issue.

---

## 10. Explicitly Excluded Assumptions

This specification does **not** define or assume:

- A maximum kilograms per day.
- A minimum batch size or minimum kilograms beyond rejecting non-positive supplied quantities.
- Production hours or working hours.
- Required inventory quantities.
- Required raw-material quantities.
- Issue severity levels.
- Service-level agreements.
- Automatic escalation rules.
- Financial limits.
- Staff capacity limits.
- Didi productivity targets.
- Product-specific output limits.
- Automatic substitutions between products.
- Automatic unit conversion.
- Approval authority.
- Attendance or leave policy.
- Phone-number identity matching.
- Language-specific business rules.
- Production completion rules beyond explicit extracted status.
- Confirmation acceptance behavior.
- Record-saving behavior.
- Google Sheets write behavior.
- Scheduler behavior.
- Dashboard or issue-management behavior.

These may be introduced only when FarmDidi provides an actual requirement or policy.

---

## 11. Phase Boundary

Phase 6 Step 1 is complete when this document is accepted as the validation contract.

This step intentionally does not:

- Add validator functions.
- Change Pydantic models.
- Change Groq prompts or parsers.
- Change `ConversationEngine`.
- Change the frontend.
- Add confirmation acceptance.
- Save records.
- Connect Google Sheets.
- Add issue status management.
- Add scheduling or dashboards.

The next step may implement production validation against these rules, beginning with the active Didi and product catalogs and the distinction between valid, invalid, and clarification-required data.
