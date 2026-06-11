import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { createCheck, uploadCheck, getQuota, getProperties, previewProperties } from "../api/client";

function isValidUrl(str) {
  try {
    const u = new URL(str);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

function parseUrlsFromText(raw) {
  if (!raw.trim()) return [];
  const lines = raw.split("\n").map((l) => l.trim()).filter(Boolean);
  const unique = [...new Set(lines)];
  return unique.filter(isValidUrl);
}

export default function NewCheck() {
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [fileUrls, setFileUrls] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [quota, setQuota] = useState(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [properties, setProperties] = useState([]);
  const [propertyPreview, setPropertyPreview] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    getQuota().then(setQuota).catch(() => {});
    getProperties().then(setProperties).catch(() => {});
  }, []);

  const validUrls = useMemo(() => parseUrlsFromText(text), [text]);

  const handleFileChange = (e) => {
    const f = e.target.files[0] || null;
    setFile(f);
    if (f) {
      const reader = new FileReader();
      reader.onload = (ev) => {
        setFileUrls(parseUrlsFromText(ev.target.result));
      };
      reader.readAsText(f);
    } else {
      setFileUrls([]);
    }
  };

  const urlsToCheck = file ? fileUrls : validUrls;

  useEffect(() => {
    if (properties.length === 0 || urlsToCheck.length === 0) {
      setPropertyPreview(null);
      return;
    }
    const timer = setTimeout(() => {
      previewProperties(urlsToCheck).then(setPropertyPreview).catch(() => setPropertyPreview(null));
    }, 500);
    return () => clearTimeout(timer);
  }, [urlsToCheck, properties]);

  const handleStartClick = async () => {
    setError(null);
    if (!file && validUrls.length === 0) {
      setError("No valid URLs to submit.");
      return;
    }
    try {
      const q = await getQuota();
      setQuota(q);
    } catch {
      // use stale quota if refresh fails
    }
    setShowConfirm(true);
  };

  const handleConfirm = async () => {
    setShowConfirm(false);
    setLoading(true);
    try {
      let result;
      if (file) {
        result = await uploadCheck(file);
      } else {
        result = await createCheck(validUrls);
      }
      navigate(`/checks/${result.check_id}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const propertySummary = useMemo(() => {
    if (!propertyPreview) return null;
    const groups = {};
    let unmatched = 0;
    for (const item of propertyPreview) {
      if (item.property_name) {
        groups[item.property_name] = (groups[item.property_name] || 0) + 1;
      } else {
        unmatched++;
      }
    }
    return { groups, unmatched };
  }, [propertyPreview]);

  const quotaRemaining = quota ? (quota.total_remaining ?? quota.remaining) : null;
  const quotaWarning = quota && urlsToCheck.length > quotaRemaining;
  const previewUrls = urlsToCheck.slice(0, 5);
  const moreCount = urlsToCheck.length - previewUrls.length;

  return (
    <div>
      <div className="card">
        <h2>Check URL Indexation Status</h2>
        <textarea
          placeholder="Paste URLs here, one per line..."
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        {validUrls.length > 0 && (
          <p className="url-count">
            {validUrls.length} valid URL{validUrls.length !== 1 ? "s" : ""} ready
          </p>
        )}
        <div className="or-divider">or</div>
        <div className="file-upload">
          <input
            type="file"
            accept=".txt"
            onChange={handleFileChange}
          />
        </div>
        {file && fileUrls.length > 0 && (
          <p className="url-count">
            {fileUrls.length} valid URL{fileUrls.length !== 1 ? "s" : ""} found in file
          </p>
        )}

        {propertySummary && (
          <div className="profile-preview" style={{ marginTop: 12, padding: 12, background: "#f8f9fa", borderRadius: 8 }}>
            <p style={{ fontWeight: 600, marginBottom: 6, fontSize: 14 }}>Property routing:</p>
            {Object.entries(propertySummary.groups).map(([name, count]) => (
              <span key={name} className="badge badge-green" style={{ marginRight: 6, marginBottom: 4 }}>
                {name}: {count} URL{count !== 1 ? "s" : ""}
              </span>
            ))}
            {propertySummary.unmatched > 0 && (
              <span className="badge badge-red">
                Unmatched: {propertySummary.unmatched} URL{propertySummary.unmatched !== 1 ? "s" : ""} (will be skipped)
              </span>
            )}
          </div>
        )}

        {quota && (
          <div style={{ marginTop: 8 }}>
            {quota.properties ? (
              <div className={`quota-info ${quotaWarning ? "quota-warning" : ""}`}>
                <p style={{ margin: "4px 0" }}>
                  Total quota: {quota.total_used}/{quota.total_limit} used ({quota.total_remaining} remaining)
                </p>
                <div style={{ fontSize: 13, color: "#777" }}>
                  {quota.properties.map((pq) => (
                    <span key={pq.property_id} style={{ marginRight: 12 }}>
                      {pq.name}: {pq.used}/{pq.limit}
                    </span>
                  ))}
                </div>
              </div>
            ) : (
              <p className={`quota-info ${quotaWarning ? "quota-warning" : ""}`}>
                Daily quota: {quota.used}/{quota.limit} used ({quota.remaining} remaining)
                {quotaWarning && " — batch exceeds remaining quota!"}
              </p>
            )}
          </div>
        )}
        <div className="form-row">
          <button
            className="btn btn-primary"
            onClick={handleStartClick}
            disabled={loading || (!file && validUrls.length === 0)}
          >
            {loading ? "Starting..." : "Start Inspection"}
          </button>
        </div>
        {error && <div className="error-msg">{error}</div>}
      </div>

      {showConfirm && (
        <div className="confirm-overlay" onClick={() => setShowConfirm(false)}>
          <div className="confirm-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Confirm Inspection</h3>
            <p className="confirm-summary">
              You are about to inspect <strong>{urlsToCheck.length} URL{urlsToCheck.length !== 1 ? "s" : ""}</strong>
              {file ? <> from file <strong>{file.name}</strong></> : " from text input"}.
            </p>

            <div className="confirm-urls-preview">
              <p className="confirm-label">URLs to check:</p>
              <ul>
                {previewUrls.map((u, i) => (
                  <li key={i} title={u}>{u}</li>
                ))}
              </ul>
              {moreCount > 0 && (
                <p className="confirm-more">and {moreCount} more...</p>
              )}
            </div>

            {propertySummary && (
              <div style={{ marginBottom: 12 }}>
                <p className="confirm-label">Property distribution:</p>
                {Object.entries(propertySummary.groups).map(([name, count]) => (
                  <div key={name} style={{ fontSize: 14, color: "#555" }}>
                    {name}: {count} URL{count !== 1 ? "s" : ""}
                  </div>
                ))}
                {propertySummary.unmatched > 0 && (
                  <div style={{ fontSize: 14, color: "#c0392b" }}>
                    Unmatched: {propertySummary.unmatched} (will be rejected)
                  </div>
                )}
              </div>
            )}

            {quota && (
              <div className="confirm-quota">
                {quota.properties ? (
                  <p>
                    This will consume <strong>{urlsToCheck.length}</strong> quota from a pool of{" "}
                    <strong>{quota.total_remaining}</strong> remaining across{" "}
                    {quota.properties.length} propert{quota.properties.length !== 1 ? "ies" : "y"}.
                  </p>
                ) : (
                  <p>
                    This will consume <strong>{urlsToCheck.length}</strong> quota.
                    You have <strong>{quota.remaining}</strong> remaining out of {quota.limit} daily limit.
                  </p>
                )}
                {quotaWarning && (
                  <p className="confirm-quota-warning">
                    Warning: This batch exceeds your remaining daily quota!
                  </p>
                )}
              </div>
            )}

            <div className="confirm-actions">
              <button className="btn btn-secondary" onClick={() => setShowConfirm(false)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleConfirm}>
                Confirm &amp; Start
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
