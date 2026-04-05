import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getCheck, subscribeProgress, getExportUrl } from "../api/client";

function VerdictBadge({ verdict, error }) {
  if (error) return <span className="badge badge-gray">Error</span>;
  if (verdict === "PASS") return <span className="badge badge-green">Indexed</span>;
  if (verdict) return <span className="badge badge-red">Not Indexed</span>;
  return <span className="badge badge-gray">Unknown</span>;
}

export default function CheckResult() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [check, setCheck] = useState(null);
  const [progress, setProgress] = useState(null);
  const [loading, setLoading] = useState(true);

  // Filters
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [changedOnly, setChangedOnly] = useState(false);
  const [sortField, setSortField] = useState(null);
  const [sortDir, setSortDir] = useState("asc");

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => setSearch(searchInput), 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const handleCardClick = (filter) => {
    if (filter === "changed") {
      if (changedOnly) {
        setChangedOnly(false);
      } else {
        setChangedOnly(true);
        setStatusFilter("all");
      }
    } else {
      setChangedOnly(false);
      if (statusFilter === filter) {
        setStatusFilter("all");
      } else {
        setStatusFilter(filter);
      }
    }
  };

  const isCardActive = (filter) => {
    if (filter === "changed") return changedOnly;
    return statusFilter === filter && !changedOnly;
  };

  const fetchCheck = useCallback(async () => {
    try {
      const data = await getCheck(id);
      setCheck(data);
      setLoading(false);
    } catch {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchCheck();
    const es = subscribeProgress(id, (p) => {
      setProgress(p);
      if (p.status === "completed" || p.status === "error") {
        fetchCheck();
      }
    });
    return () => es.close();
  }, [id, fetchCheck]);

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("asc");
    }
  };

  if (loading) return <div className="card">Loading...</div>;
  if (!check) return <div className="card">Check not found.</div>;

  const isRunning = check.status === "running";
  const results = check.results || [];

  // Summary
  const indexed = results.filter((r) => r.verdict === "PASS").length;
  const notIndexed = results.filter((r) => r.verdict && r.verdict !== "PASS" && !r.error).length;
  const errors = results.filter((r) => r.error).length;
  const changed = results.filter((r) => r.status_changed).length;
  const total = results.length;

  // Filter
  let filtered = results.filter((r) => {
    if (search && !r.url.toLowerCase().includes(search.toLowerCase())) return false;
    if (statusFilter === "indexed" && r.verdict !== "PASS") return false;
    if (statusFilter === "not_indexed" && (r.verdict === "PASS" || r.error)) return false;
    if (statusFilter === "error" && !r.error) return false;
    if (changedOnly && !r.status_changed) return false;
    return true;
  });

  // Sort
  if (sortField) {
    filtered.sort((a, b) => {
      let va = a[sortField] ?? "";
      let vb = b[sortField] ?? "";
      if (typeof va === "number" && typeof vb === "number") {
        return sortDir === "asc" ? va - vb : vb - va;
      }
      va = String(va).toLowerCase();
      vb = String(vb).toLowerCase();
      if (va < vb) return sortDir === "asc" ? -1 : 1;
      if (va > vb) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
  }

  const sortArrow = (field) => {
    if (sortField !== field) return "";
    return sortDir === "asc" ? " \u25B2" : " \u25BC";
  };

  return (
    <div>
      {/* Progress */}
      {isRunning && progress && (
        <div className="card">
          <div className="progress-text">
            Inspecting: {progress.completed}/{progress.total} URLs
          </div>
          <div className="progress-bar-container">
            <div
              className="progress-bar-fill"
              style={{ width: `${(progress.completed / progress.total) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Summary */}
      <div className="summary-bar">
        <div className={`summary-card clickable${statusFilter === "all" && !changedOnly ? " active" : ""}`} onClick={() => { setStatusFilter("all"); setChangedOnly(false); }}>
          <div className="label">Total</div>
          <div className="value">{total}</div>
        </div>
        <div className={`summary-card clickable${isCardActive("indexed") ? " active" : ""}`} onClick={() => handleCardClick("indexed")}>
          <div className="label">Indexed</div>
          <div className="value green">
            {indexed} {total > 0 && <small>({((indexed / total) * 100).toFixed(1)}%)</small>}
          </div>
        </div>
        <div className={`summary-card clickable${isCardActive("not_indexed") ? " active" : ""}`} onClick={() => handleCardClick("not_indexed")}>
          <div className="label">Not Indexed</div>
          <div className="value red">
            {notIndexed} {total > 0 && <small>({((notIndexed / total) * 100).toFixed(1)}%)</small>}
          </div>
        </div>
        <div className={`summary-card clickable${isCardActive("changed") ? " active" : ""}`} onClick={() => handleCardClick("changed")}>
          <div className="label">Status Changed</div>
          <div className="value orange">{changed}</div>
        </div>
        <div className={`summary-card clickable${isCardActive("error") ? " active" : ""}`} onClick={() => handleCardClick("error")}>
          <div className="label">Errors</div>
          <div className="value gray">{errors}</div>
        </div>
        <div className="summary-card">
          <div className="label">Checked</div>
          <div className="value" style={{ fontSize: 14 }}>
            {new Date(check.created_at).toLocaleString()}
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="card">
        <div className="table-controls">
          <input
            type="text"
            placeholder="Search URLs..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="all">All statuses</option>
            <option value="indexed">Indexed</option>
            <option value="not_indexed">Not Indexed</option>
            <option value="error">Errors</option>
          </select>
          <label>
            <input
              type="checkbox"
              checked={changedOnly}
              onChange={(e) => setChangedOnly(e.target.checked)}
            />
            Status changes only
          </label>
          {!isRunning && (
            <a href={getExportUrl(id)} className="btn btn-secondary" download>
              Export CSV
            </a>
          )}
        </div>

        <div className="results-table-wrapper">
          <table className="results-table">
            <thead>
              <tr>
                <th style={{ width: "35%" }} onClick={() => handleSort("url")}>URL{sortArrow("url")}</th>
                <th style={{ width: "8%" }} onClick={() => handleSort("verdict")}>Status{sortArrow("verdict")}</th>
                <th style={{ width: "12%" }} onClick={() => handleSort("coverage_state")}>Coverage{sortArrow("coverage_state")}</th>
                <th style={{ width: "10%" }} onClick={() => handleSort("last_crawl_time")}>Last Crawl{sortArrow("last_crawl_time")}</th>
                <th style={{ width: "8%" }} onClick={() => handleSort("crawled_as")}>Agent{sortArrow("crawled_as")}</th>
                <th style={{ width: "9%" }} onClick={() => handleSort("deindex_count")}>Deindex #{sortArrow("deindex_count")}</th>
                <th style={{ width: "9%" }}>Canonical</th>
                <th style={{ width: "9%" }}>Changed</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => {
                const mismatch =
                  r.google_canonical && r.user_canonical && r.google_canonical !== r.user_canonical;
                return (
                  <tr
                    key={r.id}
                    className="clickable"
                    onClick={() => navigate(`/urls/${encodeURIComponent(r.url)}`)}
                  >
                    <td title={r.url}>{r.url}</td>
                    <td>
                      <VerdictBadge verdict={r.verdict} error={r.error} />
                    </td>
                    <td>{r.coverage_state || "—"}</td>
                    <td>
                      {r.last_crawl_time
                        ? new Date(r.last_crawl_time).toLocaleDateString()
                        : "—"}
                    </td>
                    <td>{r.crawled_as || "—"}</td>
                    <td>{r.deindex_count}</td>
                    <td>
                      {mismatch ? (
                        <span className="canonical-mismatch" title={`Google: ${r.google_canonical}\nUser: ${r.user_canonical}`}>
                          Mismatch
                        </span>
                      ) : (
                        "OK"
                      )}
                    </td>
                    <td>
                      {r.status_changed ? (
                        <span className="badge badge-orange">Yes</span>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={8} style={{ textAlign: "center", color: "#999" }}>
                    No results match filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
