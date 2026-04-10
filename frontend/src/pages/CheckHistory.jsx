import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { listChecks } from "../api/client";
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
  const navigate = useNavigate();

  useEffect(() => {
    listChecks()
      .then(setChecks)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="card">Loading...</div>;

  return (
    <div>
      <TrendChart checks={checks} />
      <div className="card">
      <h2>Check History</h2>
      {checks.length === 0 ? (
        <p style={{ color: "#999", marginTop: 12 }}>No checks yet.</p>
      ) : (
        <ul className="check-list">
          {checks.map((c) => (
            <li key={c.id} onClick={() => navigate(`/checks/${c.id}`)}>
              <div>
                <strong>{new Date(c.created_at).toLocaleString()}</strong>
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
              <span className={`badge ${c.status === "completed" ? "badge-green" : c.status === "running" ? "badge-orange" : "badge-gray"}`}>
                {c.status}
              </span>
            </li>
          ))}
        </ul>
      )}
      </div>
    </div>
  );
}
