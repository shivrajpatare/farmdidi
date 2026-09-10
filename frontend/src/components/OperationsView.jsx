import { useState, useEffect } from "react";

function OperationsView({ apiBase }) {
  const [issues, setIssues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedIssueId, setSelectedIssueId] = useState(null);

  // Resolution state
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [resolving, setResolving] = useState(false);
  const [resolveError, setResolveError] = useState(null);

  useEffect(() => {
    let ignore = false;
    fetch(`${apiBase}/api/issues`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load issues (${res.status})`);
        return res.json();
      })
      .then((data) => {
        if (!ignore) {
          setIssues(data);
          if (data.length > 0) {
            setSelectedIssueId((prev) =>
              prev && data.some((iss) => iss.issue_id === prev) ? prev : data[0].issue_id
            );
          }
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(err.message || "Could not retrieve issues.");
          setLoading(false);
        }
      });
    return () => {
      ignore = true;
    };
  }, [apiBase]);

  async function handleRefresh() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/api/issues`);
      if (!res.ok) {
        throw new Error(`Failed to load issues (${res.status})`);
      }
      const data = await res.json();
      setIssues(data);
      if (data.length > 0) {
        setSelectedIssueId((prev) =>
          prev && data.some((iss) => iss.issue_id === prev) ? prev : data[0].issue_id
        );
      }
    } catch (err) {
      setError(err.message || "Could not retrieve issues.");
    } finally {
      setLoading(false);
    }
  }

  const selectedIssue = issues.find((i) => i.issue_id === selectedIssueId) || null;

  async function handleResolve() {
    if (!selectedIssue || resolving) return;

    setResolving(true);
    setResolveError(null);

    try {
      const res = await fetch(`${apiBase}/api/issues/${selectedIssue.issue_id}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resolution_notes: resolutionNotes.trim() || undefined,
        }),
      });

      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `Resolution failed (${res.status})`);
      }

      const updated = await res.json();

      // Update in local state
      setIssues((prev) =>
        prev.map((iss) => (iss.issue_id === updated.issue_id ? updated : iss))
      );
      setResolutionNotes("");
    } catch (err) {
      setResolveError(err.message || "Failed to resolve issue.");
    } finally {
      setResolving(false);
    }
  }

  function handleSelectIssue(issueId) {
    setSelectedIssueId(issueId);
    setResolutionNotes("");
    setResolveError(null);
  }

  return (
    <main className="ops-container">
      <div className="ops-header">
        <div>
          <h2>Operations — Issues</h2>
          <p className="ops-subtitle">Review bottlenecks and record resolutions.</p>
        </div>
        <button
          type="button"
          className="ops-refresh-btn"
          onClick={handleRefresh}
          disabled={loading}
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="ops-error-banner" role="alert">
          {error}
        </div>
      )}

      {loading && issues.length === 0 ? (
        <div className="ops-status-msg">Loading issues…</div>
      ) : issues.length === 0 ? (
        <div className="ops-empty-state">
          <p>No issues reported yet.</p>
        </div>
      ) : (
        <div className="ops-content">
          {/* Issue List */}
          <section className="ops-list" aria-label="Reported issues list">
            {issues.map((iss) => {
              const isSelected = iss.issue_id === selectedIssueId;
              const isOpen = iss.status === "open";
              return (
                <button
                  key={iss.issue_id}
                  type="button"
                  className={`ops-card ${isSelected ? "ops-card-selected" : ""}`}
                  onClick={() => handleSelectIssue(iss.issue_id)}
                >
                  <div className="ops-card-top">
                    <span className="ops-card-name">{iss.didi_name}</span>
                    <span
                      className={`ops-badge ${
                        isOpen ? "ops-badge-open" : "ops-badge-resolved"
                      }`}
                    >
                      {iss.status.toUpperCase()}
                    </span>
                  </div>
                  <p className="ops-card-issue">{iss.issue}</p>
                  <div className="ops-card-bottom">
                    <span className="ops-card-type">{iss.issue_type}</span>
                    <span className="ops-card-date">{iss.date}</span>
                  </div>
                </button>
              );
            })}
          </section>

          {/* Issue Detail */}
          <section className="ops-detail" aria-label="Issue details">
            {selectedIssue ? (
              <div className="ops-detail-card">
                <div className="ops-detail-header">
                  <div>
                    <h3>{selectedIssue.didi_name}</h3>
                    <p className="ops-detail-meta">
                      {selectedIssue.date} • {selectedIssue.issue_id}
                    </p>
                  </div>
                  <span
                    className={`ops-badge ${
                      selectedIssue.status === "open"
                        ? "ops-badge-open"
                        : "ops-badge-resolved"
                    }`}
                  >
                    {selectedIssue.status.toUpperCase()}
                  </span>
                </div>

                <div className="ops-detail-fields">
                  <div className="ops-field">
                    <span className="ops-label">Issue</span>
                    <p className="ops-value-highlight">{selectedIssue.issue}</p>
                  </div>
                  <div className="ops-field">
                    <span className="ops-label">Type</span>
                    <p className="ops-value">{selectedIssue.issue_type}</p>
                  </div>
                  <div className="ops-field">
                    <span className="ops-label">Details</span>
                    <p className="ops-value">
                      {selectedIssue.issue_details || "None reported"}
                    </p>
                  </div>
                </div>

                {selectedIssue.status === "open" ? (
                  <div className="ops-resolution-form">
                    <label htmlFor="resolution-notes" className="ops-label">
                      Resolution notes
                    </label>
                    <textarea
                      id="resolution-notes"
                      className="ops-textarea"
                      placeholder="Enter resolution notes (e.g. Delivered 50 bottles to Meena ji.)"
                      value={resolutionNotes}
                      onChange={(e) => setResolutionNotes(e.target.value)}
                      disabled={resolving}
                      rows={3}
                    />

                    {resolveError && (
                      <p className="ops-error-text" role="alert">
                        {resolveError}
                      </p>
                    )}

                    <button
                      type="button"
                      className="ops-resolve-btn"
                      onClick={handleResolve}
                      disabled={resolving}
                    >
                      {resolving ? "Resolving…" : "Mark as resolved"}
                    </button>
                  </div>
                ) : (
                  <div className="ops-resolved-info">
                    <div className="ops-resolved-badge-bar">
                      <span className="ops-resolved-icon" aria-hidden="true">✓</span>
                      <span>This issue is resolved.</span>
                    </div>
                    {selectedIssue.resolved_at && (
                      <div className="ops-field">
                        <span className="ops-label">Resolved At</span>
                        <p className="ops-value">
                          {new Date(selectedIssue.resolved_at).toLocaleString()}
                        </p>
                      </div>
                    )}
                    <div className="ops-field">
                      <span className="ops-label">Resolution Notes</span>
                      <p className="ops-value">
                        {selectedIssue.resolution_notes || "No notes provided."}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="ops-empty-detail">
                <p>Select an issue from the list to view details.</p>
              </div>
            )}
          </section>
        </div>
      )}
    </main>
  );
}

export default OperationsView;
