import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { lookupUrl, getUrlHistory } from "../api/client";

function VerdictBadge({ verdict, error }) {
  if (error) return <span className="badge badge-gray">Error</span>;
  if (verdict === "PASS") return <span className="badge badge-green">Indexed</span>;
  if (verdict) return <span className="badge badge-red">Not Indexed</span>;
  return <span className="badge badge-gray">Unknown</span>;
}

export default function UrlDetail() {
  const { urlString } = useParams();
  const decodedUrl = decodeURIComponent(urlString);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function load() {
      try {
        const lookup = await lookupUrl(decodedUrl);
        const history = await getUrlHistory(lookup.url_id);
        setData(history);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [decodedUrl]);

  if (loading) return <div className="card">Loading...</div>;
  if (error) return <div className="card error-msg">{error}</div>;
  if (!data) return <div className="card">Not found.</div>;

  return (
    <div>
      <div className="card">
        <h2>URL History</h2>
        <p style={{ wordBreak: "break-all", marginBottom: 8 }}>
          <a href={data.url} target="_blank" rel="noreferrer">{data.url}</a>
        </p>
        <div className="summary-bar">
          <div className="summary-card">
            <div className="label">First Seen</div>
            <div className="value" style={{ fontSize: 14 }}>
              {new Date(data.first_seen).toLocaleDateString()}
            </div>
          </div>
          <div className="summary-card">
            <div className="label">Deindex Count</div>
            <div className="value red">{data.deindex_count}</div>
          </div>
          <div className="summary-card">
            <div className="label">Total Checks</div>
            <div className="value">{data.history.length}</div>
          </div>
        </div>
      </div>

      <div className="card">
        <h2>Check Timeline</h2>
        <div className="timeline">
          {data.history.map((h) => {
            const mismatch =
              h.google_canonical && h.user_canonical && h.google_canonical !== h.user_canonical;
            return (
              <div key={h.id} className="timeline-item">
                <div className="timeline-date">
                  {new Date(h.checked_at).toLocaleString()}
                </div>
                <div className="timeline-status">
                  <VerdictBadge verdict={h.verdict} error={h.error} />
                  {h.status_changed && (
                    <span className="badge badge-orange" style={{ marginLeft: 8 }}>
                      Changed
                    </span>
                  )}
                  <div style={{ fontSize: 13, color: "#666", marginTop: 4 }}>
                    {h.coverage_state || "—"}
                    {h.crawled_as && ` · ${h.crawled_as}`}
                    {h.last_crawl_time && ` · Crawled ${new Date(h.last_crawl_time).toLocaleDateString()}`}
                  </div>
                  {mismatch && (
                    <div className="canonical-mismatch" style={{ fontSize: 12, marginTop: 4 }}>
                      Canonical mismatch: Google={h.google_canonical}, User={h.user_canonical}
                    </div>
                  )}
                  {h.error && (
                    <div style={{ color: "#dc2626", fontSize: 12, marginTop: 4 }}>
                      Error: {h.error}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          {data.history.length === 0 && (
            <p style={{ color: "#999" }}>No check history for this URL.</p>
          )}
        </div>
      </div>

      <Link to="/" className="btn btn-secondary">Back</Link>
    </div>
  );
}
