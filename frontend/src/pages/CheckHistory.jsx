import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { listChecks, deleteChecksBulk } from "../api/client";
import TrendChart from "../components/TrendChart";

function formatElapsed(seconds) {
  if (seconds == null) return null;
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}m ${rem}s`;
}

export default function CheckHistory() {
  const [checks, setChecks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(() => new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    listChecks()
      .then(setChecks)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const deletableIds = checks.filter((c) => c.status !== "running").map((c) => c.id);
  const allSelected = deletableIds.length > 0 && deletableIds.every((id) => selected.has(id));

  const toggleOne = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    setSelected(allSelected ? new Set() : new Set(deletableIds));
  };

  const clearSelection = () => setSelected(new Set());

  const handleBulkDelete = async () => {
    const ids = [...selected];
    if (ids.length === 0) return;
    if (!window.confirm(`Delete ${ids.length} check${ids.length > 1 ? "s" : ""}? This removes all their results.`)) return;
    setBulkDeleting(true);
    try {
      const { deleted } = await deleteChecksBulk(ids);
      const idSet = new Set(ids);
      setChecks((prev) => prev.filter((c) => !idSet.has(c.id)));
      clearSelection();
      if (deleted < ids.length) {
        window.alert(`Deleted ${deleted} of ${ids.length} (running checks were skipped).`);
      }
    } catch (err) {
      window.alert(err.message || "Failed to delete checks");
    } finally {
      setBulkDeleting(false);
    }
  };

  if (loading) return <div className="card">Loading...</div>;

  return (
    <div>
      <TrendChart checks={checks} />
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ margin: 0 }}>Check History</h2>
          {selected.size > 0 && (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button className="btn btn-secondary btn-sm" onClick={clearSelection}>
                Clear
              </button>
              <button
                className="btn btn-danger btn-sm"
                disabled={bulkDeleting}
                onClick={handleBulkDelete}
              >
                {bulkDeleting ? "Deleting..." : `Delete ${selected.size} selected`}
              </button>
            </div>
          )}
        </div>
        {checks.length === 0 ? (
          <p style={{ color: "#999", marginTop: 12 }}>No checks yet.</p>
        ) : (
          <>
            <label
              style={{
                display: "flex",
                gap: 8,
                alignItems: "center",
                margin: "12px 0 8px",
                color: "#888",
                fontSize: 13,
              }}
            >
              <input
                type="checkbox"
                checked={allSelected}
                onChange={toggleAll}
                disabled={deletableIds.length === 0}
              />
              Select all
            </label>
            <ul className="check-list">
              {checks.map((c) => (
                <li key={c.id} onClick={() => navigate(`/checks/${c.id}`)}>
                  <label
                    onClick={(e) => e.stopPropagation()}
                    style={{ display: "flex", alignItems: "center", marginRight: 12 }}
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(c.id)}
                      disabled={c.status === "running"}
                      title={c.status === "running" ? "Cannot delete a running check" : ""}
                      aria-label={`Select check from ${new Date(c.created_at).toLocaleString()}`}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => {
                        e.stopPropagation();
                        toggleOne(c.id);
                      }}
                    />
                  </label>
                  <div style={{ flex: 1 }}>
                    <strong>{new Date(c.created_at).toLocaleString()}</strong>
                    {c.source === "scheduled" && (
                      <span className="badge badge-gray" style={{ marginLeft: 8 }}>
                        scheduled
                      </span>
                    )}
                    <div className="check-meta">
                      <span>{c.url_count} URLs</span>
                      {c.elapsed_seconds != null && (
                        <span style={{ color: "#888" }}>{formatElapsed(c.elapsed_seconds)}</span>
                      )}
                      <span className="badge badge-green">{c.indexed_count} indexed</span>
                      <span className="badge badge-red">{c.not_indexed_count} not indexed</span>
                      {c.error_count > 0 && (
                        <span className="badge badge-gray">{c.error_count} errors</span>
                      )}
                    </div>
                  </div>
                  <span
                    className={`badge ${
                      c.status === "completed"
                        ? "badge-green"
                        : c.status === "running"
                        ? "badge-orange"
                        : "badge-gray"
                    }`}
                  >
                    {c.status}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
