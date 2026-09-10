import { useState, useCallback, useRef } from "react";
import ChatWindow from "./components/ChatWindow";
import ChatInput from "./components/ChatInput";
import OperationsView from "./components/OperationsView";

const API = "http://localhost:8000";

const DIDIS = [
  { id: "D002", name: "Sunita" },
  { id: "D001", name: "Meena" },
  { id: "D003", name: "Asha" },
  { id: "D004", name: "Rekha" },
  { id: "D005", name: "Lata" },
];

function generateSessionId() {
  return "S" + Date.now().toString(36);
}

function App() {
  const [currentView, setCurrentView] = useState("checkin");
  const [selectedDidi, setSelectedDidi] = useState("D002");
  const [messages, setMessages] = useState([]);
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [state, setState] = useState(null);
  const [error, setError] = useState(null);
  const [confirmationChoice, setConfirmationChoice] = useState(null);
  const [sheetSaved, setSheetSaved] = useState(null);
  // Track whether the session hit a 409 duplicate rejection
  const [duplicateRejected, setDuplicateRejected] = useState(false);
  // Guard against rapid double-clicks on confirmation
  const confirmingRef = useRef(false);

  const started = sessionId !== null;

  // ----- Reset for another check-in -----
  function handleReset() {
    setSessionId(null);
    setMessages([]);
    setState(null);
    setError(null);
    setConfirmationChoice(null);
    setSheetSaved(null);
    setDuplicateRejected(false);
    confirmingRef.current = false;
  }

  // ----- API helpers -----

  async function apiPost(path, body) {
    const res = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      const err = new Error(detail.detail || `Request failed (${res.status})`);
      err.httpStatus = res.status;
      throw err;
    }
    return res.json();
  }

  // ----- Start check-in -----

  async function handleStart() {
    setSending(true);
    setError(null);
    try {
      const sid = generateSessionId();
      const data = await apiPost("/api/checkin/start", {
        session_id: sid,
        didi_id: selectedDidi,
      });
      setSessionId(data.session_id);
      setState(data.state);
      setSheetSaved(null);
      setDuplicateRejected(false);
      setMessages([{ role: "assistant", text: data.message }]);
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  }

  // ----- Send message -----

  const handleSend = useCallback(
    async (text) => {
      if (sending || !sessionId) return;

      setMessages((prev) => [...prev, { role: "user", text }]);
      setSending(true);
      setError(null);

      try {
        let data;

        if (state === "ASK_PRODUCTION") {
          data = await apiPost("/api/checkin/production", {
            session_id: sessionId,
            message: text,
          });
        } else if (state === "ASK_ISSUE") {
          data = await apiPost("/api/checkin/issue", {
            session_id: sessionId,
            message: text,
          });
        } else if (state === "AWAITING_CORRECTION") {
          data = await apiPost("/api/checkin/correct", {
            session_id: sessionId,
            message: text,
          });
        } else {
          data = null;
        }

        if (data) {
          setState(data.state);
          setConfirmationChoice(null);
          setMessages((prev) => [
            ...prev,
            { role: "assistant", text: data.message },
          ]);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setSending(false);
      }
    },
    [sending, sessionId, state]
  );

  async function handleConfirmationChoice(choice) {
    // Guard: prevent double-clicks or clicks after duplicate rejection
    if (sending || !sessionId || duplicateRejected || confirmingRef.current)
      return;

    confirmingRef.current = true;

    const choiceLabel = choice === "yes" ? "Yes, correct" : "No, change";
    setConfirmationChoice(choiceLabel);
    setMessages((prev) => [...prev, { role: "user", text: choiceLabel }]);
    setSending(true);
    setError(null);

    try {
      const data = await apiPost("/api/checkin/confirm", {
        session_id: sessionId,
        decision: choice,
      });
      setState(data.state);
      if (data.sheet_saved !== undefined) {
        setSheetSaved(data.sheet_saved);
      }
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: data.message },
      ]);
      if (data.state !== "CONFIRM") {
        setConfirmationChoice(null);
      }
    } catch (err) {
      // If 409, mark duplicate rejected so buttons stay permanently disabled
      if (err.httpStatus === 409) {
        setDuplicateRejected(true);
        setError(
          "Aaj ka check-in already confirm ho chuka hai. Doosra check-in is Didi ke liye aaj nahi ho sakta."
        );
      } else {
        setError(err.message);
        setConfirmationChoice(null);
      }
    } finally {
      setSending(false);
      confirmingRef.current = false;
    }
  }

  // Determine if confirmation buttons should be shown
  const showConfirmationButtons =
    state === "CONFIRM" && !confirmationChoice && !duplicateRejected;

  // ----- Render -----

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-main">
          <div>
            <h1>FarmDidi Daily Check-in</h1>
            <p className="subtitle">
              {currentView === "checkin"
                ? "Today's check-in"
                : "Operations & Issue Management"}
            </p>
          </div>
          <nav className="header-nav" aria-label="Main Navigation">
            <button
              type="button"
              className={`nav-btn ${
                currentView === "checkin" ? "nav-btn-active" : ""
              }`}
              onClick={() => setCurrentView("checkin")}
            >
              Check-in
            </button>
            <button
              type="button"
              className={`nav-btn ${
                currentView === "operations" ? "nav-btn-active" : ""
              }`}
              onClick={() => setCurrentView("operations")}
            >
              Operations
            </button>
          </nav>
        </div>
      </header>

      {currentView === "operations" ? (
        <OperationsView apiBase={API} />
      ) : (
        <div className="checkin-body">
          {!started ? (
            <main className="chat-area">
              <div className="start-container">
                <div className="didi-select-group">
                  <label htmlFor="didi-select" className="didi-select-label">
                    Select Didi:
                  </label>
                  <select
                    id="didi-select"
                    className="didi-select"
                    value={selectedDidi}
                    onChange={(e) => setSelectedDidi(e.target.value)}
                    disabled={sending}
                  >
                    {DIDIS.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name} ({d.id})
                      </option>
                    ))}
                  </select>
                </div>
                <p className="start-text">
                  Start today&apos;s production check-in with{" "}
                  {DIDIS.find((d) => d.id === selectedDidi)?.name || "Didi"}.
                </p>
                <button
                  className="start-btn"
                  onClick={handleStart}
                  disabled={sending}
                >
                  {sending ? "Starting…" : "Start Check-in"}
                </button>
              </div>
            </main>
          ) : (
            <>
              <ChatWindow messages={messages} />

              {state === "CONFIRM" && !duplicateRejected && (
                <div className="confirmation-panel" role="status">
                  <p className="confirmation-status">
                    {confirmationChoice
                      ? confirmationChoice === "Yes, correct"
                        ? "Confirmation selected"
                        : "Change requested"
                      : "Please confirm the details above."}
                  </p>
                  {showConfirmationButtons && (
                    <div className="confirmation-actions">
                      <button
                        className="confirmation-btn confirmation-btn-primary"
                        type="button"
                        onClick={() => handleConfirmationChoice("yes")}
                      >
                        Yes, correct
                      </button>
                      <button
                        className="confirmation-btn confirmation-btn-secondary"
                        type="button"
                        onClick={() => handleConfirmationChoice("no")}
                      >
                        No, change
                      </button>
                    </div>
                  )}
                </div>
              )}

              {(state === "COMPLETE" || duplicateRejected) && (
                <div className="complete-actions">
                  <button
                    type="button"
                    className="start-new-btn"
                    onClick={handleReset}
                  >
                    Start Another Check-in
                  </button>
                </div>
              )}

              {state !== "CONFIRM" &&
                state !== "COMPLETE" &&
                !duplicateRejected && (
                  <ChatInput onSend={handleSend} disabled={sending} />
                )}
            </>
          )}

          {error && (
            <div className="error-bar" role="alert">
              {error}
            </div>
          )}

          <div className="status-bar" role="status">
            <span className="status-dot" aria-hidden="true"></span>
            <span className="status-text">
              {sending
                ? "Sending…"
                : duplicateRejected
                  ? "Check-in already recorded for today"
                  : state === "CONFIRM"
                    ? "Waiting for confirmation"
                    : state === "AWAITING_CORRECTION"
                      ? "Waiting for correction"
                      : state === "COMPLETE"
                        ? sheetSaved === true
                          ? "Saved to today's check-in record."
                          : sheetSaved === false
                            ? "Check-in confirmed (save pending)"
                            : "Check-in complete"
                        : state === "ASK_PRODUCTION"
                          ? "Awaiting production details"
                          : state === "ASK_ISSUE"
                            ? "Awaiting issue details"
                            : "Ready"}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
