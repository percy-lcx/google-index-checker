import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { createCheck, uploadCheck, getQuota } from "../api/client";

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
  const navigate = useNavigate();

  useEffect(() => {
    getQuota().then(setQuota).catch(() => {});
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

  const quotaWarning =
    quota && urlsToCheck.length > quota.remaining;
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
        {quota && (
          <p className={`quota-info ${quotaWarning ? "quota-warning" : ""}`}>
            Daily quota: {quota.used}/{quota.limit} used ({quota.remaining} remaining)
            {quotaWarning && " — batch exceeds remaining quota!"}
          </p>
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

            {quota && (
              <div className="confirm-quota">
                <p>
                  This will consume <strong>{urlsToCheck.length}</strong> quota.
                  You have <strong>{quota.remaining}</strong> remaining out of {quota.limit} daily limit.
                </p>
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
