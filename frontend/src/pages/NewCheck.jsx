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

export default function NewCheck() {
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [quota, setQuota] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    getQuota().then(setQuota).catch(() => {});
  }, []);

  const validUrls = useMemo(() => {
    if (!text.trim()) return [];
    const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
    const unique = [...new Set(lines)];
    return unique.filter(isValidUrl);
  }, [text]);

  const handleSubmit = async () => {
    setError(null);
    setLoading(true);
    try {
      let result;
      if (file) {
        result = await uploadCheck(file);
      } else {
        if (validUrls.length === 0) {
          setError("No valid URLs to submit.");
          setLoading(false);
          return;
        }
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
    quota && validUrls.length > quota.remaining;

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
            onChange={(e) => setFile(e.target.files[0] || null)}
          />
        </div>
        {quota && (
          <p className={`quota-info ${quotaWarning ? "quota-warning" : ""}`}>
            Daily quota: {quota.used}/{quota.limit} used ({quota.remaining} remaining)
            {quotaWarning && " — batch exceeds remaining quota!"}
          </p>
        )}
        <div className="form-row">
          <button
            className="btn btn-primary"
            onClick={handleSubmit}
            disabled={loading || (!file && validUrls.length === 0)}
          >
            {loading ? "Starting..." : "Start Inspection"}
          </button>
        </div>
        {error && <div className="error-msg">{error}</div>}
      </div>
    </div>
  );
}
