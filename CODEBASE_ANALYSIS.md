# FarmDidi Daily Production Check-in
## Complete Codebase Context and End-to-End Analysis

**Document status:** Current repository analysis
**Repository phase:** Phase 1 - Project Foundation
**Last verified:** 2026-09-09
**Scope:** The code that exists in this repository today, plus the fixed business architecture that future phases must implement

---

## 1. Executive Summary

FarmDidi Daily Production Check-in is planned as a small business workflow for collecting daily production updates from rural women, called Didis. A Didi should be able to reply naturally in Hindi, Hinglish, English, or mixed language. The system will eventually extract production details, validate them, ask for confirmation, and save only confirmed records to Google Sheets.

The repository is currently at the foundation stage. It does **not** yet implement the production check-in workflow. The working code currently provides:

- A Python virtual environment setup path.
- A FastAPI application.
- Environment-backed application configuration.
- A typed `/health` endpoint.
- The initial directory structure for later phases.
- Dependency and Git ignore configuration.

The following capabilities are intentionally not implemented yet:

- React web chat.
- Didi identification and business data loading.
- Conversation state management.
- Groq API integration.
- Natural-language extraction.
- Validation and business rules for production records.
- Confirmation handling.
- Google Sheets persistence.
- Issue management.
- Scheduling.
- No-response handling.
- Daily operations summaries.
- Automated tests.
- Deployment configuration.

This separation is important. The current code is a foundation, not a chatbot or production automation system.

---

## 2. Fixed Product and Architecture Context

### 2.1 Business problem

FarmDidi supports Didis who physically produce products such as achar. The business needs a simple daily check-in that asks:

1. What are you making today?
2. How much are you making?
3. Are you facing an issue or do you need anything?

The response may be informal and multilingual. The application must turn that response into reliable structured information without guessing when the response is ambiguous.

### 2.2 Fixed architecture

The intended end-to-end flow is:

```text
Daily Scheduler
      |
      v
Conversation Layer
      |
      v
FastAPI Backend
      |
      v
Deterministic Conversation State
      |
      v
Groq API / LLM
      |
      v
Structured JSON
      |
      v
Validation and Business Rules
      |
      v
Confirmation from Didi
      |
      v
Save Confirmed Record
      |
      v
Google Sheets
      |
      v
Issue Visibility / Daily Operations Summary
```

The critical design rule is that the LLM is an interpreter, not the application controller. Python must control:

- Which conversation state is active.
- Which question is asked next.
- Whether required information is present.
- Whether a value is valid.
- Whether clarification is required.
- Whether confirmation has been received.
- Whether a record is saved.
- How API and user-input failures are handled.

Google Sheets remains the final operational record, but it is deliberately excluded from Phase 1.

### 2.3 Fixed technology choices

| Concern | Chosen technology | Current status |
|---|---|---|
| Backend | Python and FastAPI | Present |
| AI provider | Groq API | Not connected |
| Communication | React web chat for the MVP | Not created |
| Storage | Google Sheets API | Not connected |
| Initial data | JSON | Placeholder exists |
| Scheduling | Python scheduler or cron initially | Not created |
| Source control | Git and GitHub | Local Git repository initialized |

No vector database, RAG system, multi-agent framework, fine-tuning, Kubernetes, or unnecessary infrastructure belongs in this MVP unless a real later requirement justifies it.

---

## 3. Current Repository Structure

```text
FARMDIDI/
|
|-- backend/
|   |-- __init__.py
|   |-- main.py
|   |-- config.py
|   |-- models.py
|   |-- services/
|   |   |-- __init__.py
|   |   |-- ai.py
|   |   `-- validation.py
|   `-- data/
|       `-- didis.json
|
|-- frontend/
|   `-- .gitkeep
|
|-- .env
|-- .gitignore
|-- README.md
|-- requirements.txt
|-- CODEBASE_ANALYSIS.md
|-- .venv/                 (local, ignored)
`-- .git/                  (local Git metadata)
```

### Important repository facts

- The repository was initialized with `git init` but no commit has been created yet.
- `.env` is ignored so local configuration is not accidentally committed.
- `.venv` is ignored so installed packages are not committed.
- Python cache directories are ignored.
- `frontend/` is intentionally empty apart from `.gitkeep`.
- `backend/data/didis.json` currently contains an empty JSON array.
- `backend/services/ai.py` and `backend/services/validation.py` are currently empty placeholders.

---

## 4. Current Module-by-Module Analysis

### 4.1 `backend/main.py`

This is the FastAPI application entry point.

Current responsibilities:

1. Import the FastAPI framework.
2. Import the application settings from `backend.config`.
3. Import the response schema from `backend.models`.
4. Create the FastAPI application object.
5. Register the health endpoint.

The application is created with the configured application name:

```python
app = FastAPI(title=settings.app_name)
```

The only route is:

```text
GET /health
```

It returns a `HealthResponse` object with:

```json
{
  "status": "ok",
  "service": "farmdidi-checkin"
}
```

The import uses `backend.models` rather than a bare `models` import. This is required because the documented launch command imports the application as `backend.main:app` from the project root.

What this module does **not** do:

- It does not receive chat messages.
- It does not identify a Didi.
- It does not call Groq.
- It does not manage conversation state.
- It does not validate production data.
- It does not save anything.

### 4.2 `backend/config.py`

This module provides the first configuration boundary.

It calls `load_dotenv()` from `python-dotenv`, then exposes a frozen `Settings` dataclass. Current settings are:

| Setting | Environment variable | Default |
|---|---|---|
| Application name | `APP_NAME` | `FarmDidi Daily Production Check-in` |
| Environment | `APP_ENV` | `development` |
| Host | `HOST` | `127.0.0.1` |
| Port | `PORT` | `8000` |

The module creates one shared instance:

```python
settings = Settings()
```

The current FastAPI application uses `settings.app_name`. The host and port values are available for future startup wiring, but the current README command passes Uvicorn's defaults/command-line behavior directly. In other words, `HOST` and `PORT` are defined configuration values, but they are not yet used to construct a startup command automatically.

The settings module is intentionally small. It is not yet responsible for secrets, Groq configuration, Google credentials, or business rules.

### 4.3 `backend/models.py`

This module contains the current Pydantic response model:

```python
class HealthResponse(BaseModel):
    status: str
    service: str
```

FastAPI uses this model as the response contract for `/health`. Pydantic therefore validates and serializes the health response consistently.

This is not yet the business record model. The future production record will need a separate explicit schema rather than reusing `HealthResponse`.

### 4.4 `backend/services/ai.py`

This file is a reserved service boundary for the future Groq integration. It is currently empty.

The intended responsibility is narrow:

- Accept text and the context needed for extraction.
- Call Groq through a provider-specific implementation.
- Request structured output.
- Return parsed extraction data or a controlled error.

It must not own the complete conversation flow. The application layer should decide what to ask and what to do with the extraction result.

### 4.5 `backend/services/validation.py`

This file is a reserved service boundary for future validation and business rules. It is currently empty.

The intended responsibility is to check extracted values such as:

- Product validity.
- Quantity presence.
- Quantity ambiguity.
- Unit validity.
- Issue clarity.
- Required field completeness.
- Business-specific constraints.

Validation must reject uncertainty or return a clarification requirement. It must not silently convert ambiguous information into a guessed value.

### 4.6 `backend/data/didis.json`

This file is the reserved initial JSON data source for Didi records. It currently contains:

```json
[]
```

No fictional Didi records have been loaded yet. Adding the sample Didis and defining their schema belongs to Phase 2, not Phase 1.

The future sample data is expected to include fictional entries such as D001 Meena, D002 Sunita, D003 Asha, D004 Rekha, and D005 Lata. These must remain clearly marked as demo data.

### 4.7 `frontend/.gitkeep`

The frontend directory currently has no React application. `.gitkeep` exists only so Git can represent the planned directory.

The web chat belongs to Phase 4. It should eventually communicate with FastAPI, but it should not duplicate business rules that belong in Python.

### 4.8 `requirements.txt`

Current pinned dependencies:

| Dependency | Purpose |
|---|---|
| `fastapi==0.115.12` | Web API framework |
| `uvicorn[standard]==0.34.2` | ASGI server for running FastAPI |
| `python-dotenv==1.1.0` | Loads local `.env` configuration |

There are no Groq, Google Sheets, React, test, or scheduler dependencies yet. That is consistent with the current phase.

### 4.9 `.env`

Current local configuration:

```text
APP_NAME=FarmDidi Daily Production Check-in
APP_ENV=development
HOST=127.0.0.1
PORT=8000
```

This file is local-only and ignored by Git. It currently contains no secrets. Future API keys and service credentials must also remain in environment variables or a secure deployment secret store, never in source code.

### 4.10 `.gitignore`

The ignore rules exclude:

- `.env`
- `.venv/`
- Python cache files and directories
- Pytest cache
- VS Code local metadata
- Node modules
- Frontend distribution output

This is adequate for the current mixed Python/future React repository foundation.

### 4.11 `README.md`

The README currently documents:

- The Phase 1 scope.
- Virtual environment creation.
- Dependency installation.
- The Uvicorn startup command.
- The local API address.
- The `/health` endpoint.

It correctly states that Google Sheets, Groq, conversation logic, and the React interface are later-phase work.

---

## 5. Current Runtime Flow

The actual Phase 1 runtime path is short:

```text
Command line
    |
    v
Uvicorn imports backend.main:app
    |
    v
backend.config loads .env
    |
    v
FastAPI app is created
    |
    v
GET /health
    |
    v
HealthResponse is validated and serialized
    |
    v
JSON response returned
```

### Startup command

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --reload
```

The current verified server address is:

```text
http://127.0.0.1:8000
```

### Health request

```text
GET http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "farmdidi-checkin"
}
```

---

## 6. Validation Performed

The current foundation has been checked in three ways:

### 6.1 Dependency installation

The pinned dependencies install successfully into `.venv` using:

```powershell
python -m pip install -r requirements.txt
```

### 6.2 Python compilation

The backend compiles successfully using:

```powershell
python -m compileall -q backend
```

### 6.3 Application import and live endpoint

The application imports successfully using:

```powershell
.\.venv\Scripts\python.exe -c "from backend.main import app; print(app.title)"
```

The live Uvicorn server returns HTTP 200 for `/health` with the expected JSON response.

No automated test suite exists yet. The checks above are manual foundation checks, not comprehensive application tests.

---

## 7. What Is Implemented Versus Planned

| Capability | Current state | Intended phase |
|---|---|---|
| Project directory | Implemented | Phase 1 |
| Python environment | Implemented locally | Phase 1 |
| FastAPI app | Implemented | Phase 1 |
| Environment config | Implemented minimally | Phase 1 |
| Health endpoint | Implemented and verified | Phase 1 |
| Didi model/data | Empty placeholder only | Phase 2 |
| Conversation states | Not implemented | Phase 3 |
| React chat | Empty frontend directory | Phase 4 |
| Groq extraction | Placeholder module only | Phase 5 |
| Validation rules | Placeholder module only | Phase 6 |
| Confirmation flow | Not implemented | Phase 7 |
| Google Sheets | Not connected | Phase 8 |
| Issue visibility | Not implemented | Phase 9 |
| Scheduler | Not implemented | Phase 10 |
| Failure/no-response handling | Not implemented | Phase 11 |
| Daily summary | Not implemented | Phase 12 |
| Dashboard | Not implemented | Phase 13 |
| Tests/evaluation | Not implemented | Phase 14 |
| Deployment | Not implemented | Phase 15 |
| Final documentation/demo | This document covers current code context | Phase 16 |

---

## 8. Intended Future Business Record

The final confirmed production record is expected to contain useful fields such as:

```text
date
didi_id
didi_name
production_status
product
quantity
unit
has_issue
issue_type
issue
issue_details
status
```

The exact Pydantic model should be introduced when the business data model and conversation engine are implemented. It should not be added to the Phase 1 health model just to make the repository look more complete.

Only confirmed records should reach the persistence layer.

---

## 9. Intended Deterministic Conversation Flow

The future application flow is:

```text
START
  |
  v
ASK_PRODUCTION
  |
  v
GET_PRODUCTION
  |
  v
ASK_ISSUE
  |
  v
GET_ISSUE
  |
  v
CONFIRM
  |
  v
SAVE
  |
  v
COMPLETE
```

The state machine belongs to Python. The LLM should extract information from a Didi's response, but it should not decide that a record is saved.

For an ambiguous response such as:

```text
Aaj aam ka achar banaungi, 20 ya 30 kilo.
```

The system must ask for clarification instead of selecting a number:

```text
Bas confirm kar du, quantity 20 kg hai ya 30 kg?
```

This behavior is central to operational reliability.

---

## 10. Reliability and Failure Boundaries

The future implementation must explicitly handle:

- Missing quantity.
- Ambiguous quantity.
- Invalid product.
- Unknown Didi.
- Missing or unclear issue details.
- Explicit no-issue responses.
- Groq API failure.
- Invalid JSON from the model.
- Duplicate submissions.
- No response from a Didi.
- Unexpected user input.

The safe default is clarification or a controlled failure. The system must not invent a product, quantity, issue, or Didi identity.

The future service boundaries should look conceptually like this:

```text
HTTP/channel adapter
        |
        v
Conversation state controller
        |
        +--> AI extraction service
        |
        +--> Validation/business rules
        |
        +--> Confirmation decision
        |
        `--> Persistence adapter
```

This keeps the web chat replaceable later by another channel without rewriting the core business workflow.

---

## 11. Current Technical Risks and Gaps

### 11.1 No automated tests

There are no unit or API tests. The health route has been manually verified, but future state transitions, validation rules, duplicate handling, and persistence need automated coverage.

### 11.2 Startup configuration is only partially wired

`HOST` and `PORT` are loaded into settings, but the documented Uvicorn command still supplies startup behavior separately. This is acceptable for Phase 1, but a later startup command or application runner should use one clear configuration source.

### 11.3 No production secret management

The current `.env` contains no secrets. When Groq and Google credentials are added, the project will need documented environment variable names and a secure deployment approach.

### 11.4 No persistence yet

There is no local record store and no Google Sheets adapter. No production data can be saved by the current code.

### 11.5 No request or authentication boundary yet

The health endpoint is public on the local development server. There is no user authentication, Didi verification, session identity, or production access control. These concerns should be addressed only when the relevant workflow is introduced.

### 11.6 Empty placeholders can be mistaken for implemented services

`ai.py`, `validation.py`, and `didis.json` establish structure only. They do not currently provide callable behavior or usable demo data. Future documentation should preserve this distinction.

---

## 12. Recommended Next Step: Phase 2 Only

The next phase should define the Didi and business data model without adding Groq, Google Sheets, scheduling, or frontend work.

A focused Phase 2 should:

1. Define the shape of a fictional Didi record.
2. Populate `backend/data/didis.json` with the five demo Didis.
3. Define the allowed demo product values.
4. Add simple loading/access code for the JSON data if needed.
5. Add focused tests for known and unknown Didi lookup.
6. Keep `/health` working.

Phase 2 should not yet call an LLM or save anything to Google Sheets. Those responsibilities belong to their explicitly assigned phases.

---

## 13. Bottom Line

The repository is a clean, working Phase 1 foundation. Its strongest property is scope discipline: the FastAPI service starts, configuration loads, the health contract is typed, and future service boundaries exist without pretending that the business workflow already works.

The next meaningful implementation step is the Didi and business data model. From there, the project can add deterministic conversation state first, then natural-language extraction, validation, confirmation, and finally Google Sheets persistence in the fixed order defined by the project context.
