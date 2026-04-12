import { useState, useEffect, useMemo } from "react";
import { getWatchlist, saveWatchlist, getSchedule } from "../api/client";

function formatTimezone(tz) {
  if (!tz || tz === "UTC") return "UTC";
  const match = tz.match(/^Etc\/GMT([+-])(\d+)$/);
  if (match) {
    const sign = match[1] === "+" ? "-" : "+";
    return `GMT${sign}${match[2]}`;
  }
  return tz;
}

function summarizeSchedule(schedule) {
  if (!schedule) return "Loading schedule...";
  if (!schedule.enabled) return "Automatic checking is currently disabled.";
  const n = (schedule.times || []).length;
  if (n === 0) return "No run times configured.";
  const freq =
    n === 1 ? "once a day" : n === 2 ? "twice a day" : `${n} times a day`;
  return `Checked automatically ${freq}.`;
}

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
  return [...new Set(lines)];
}

export default function Watchlist() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedCount, setSavedCount] = useState(null);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [schedule, setSchedule] = useState(null);
  const [tooltipOpen, setTooltipOpen] = useState(false);

  useEffect(() => {
    Promise.all([
      getWatchlist()
        .then((data) => {
          setText((data.urls || []).join("\n"));
          setSavedCount(data.count || 0);
        })
        .catch((e) => setError(e.message)),
      getSchedule()
        .then(setSchedule)
        .catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []);

  const parsed = useMemo(() => parseUrlsFromText(text), [text]);
  const validCount = useMemo(
    () => parsed.filter(isValidUrl).length,
    [parsed]
  );
  const invalidCount = parsed.length - validCount;

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const existing = parseUrlsFromText(text);
      const incoming = parseUrlsFromText(ev.target.result);
      const merged = [...new Set([...existing, ...incoming])];
      setText(merged.join("\n"));
      setStatus(
        `Loaded ${incoming.length} URL${incoming.length !== 1 ? "s" : ""} from ${file.name}. Review and click Save Watchlist to persist.`
      );
    };
    reader.readAsText(file);
    e.target.value = "";
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setStatus(null);
    try {
      const result = await saveWatchlist(parsed);
      setSavedCount(result.count);
      setText((result.urls || []).join("\n"));
      const rejected = result.rejected || 0;
      setStatus(
        rejected > 0
          ? `Saved ${result.count} URLs. ${rejected} duplicate or invalid URL${rejected !== 1 ? "s" : ""} removed.`
          : `Saved ${result.count} URLs.`
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="card">Loading...</div>;

  return (
    <div>
      <div className="card">
        <h2>Scheduled Watchlist</h2>
        <p style={{ fontSize: 14, color: "#666", marginBottom: 12 }}>
          {summarizeSchedule(schedule)}{" "}
          {schedule && (
            <span
              className="schedule-link-wrapper"
              onMouseEnter={() => setTooltipOpen(true)}
              onMouseLeave={() => setTooltipOpen(false)}
            >
              <span
                className="schedule-link"
                onClick={() => setTooltipOpen((v) => !v)}
                onFocus={() => setTooltipOpen(true)}
                onBlur={() => setTooltipOpen(false)}
                role="button"
                tabIndex={0}
                aria-expanded={tooltipOpen}
              >
                See schedule
              </span>
              {tooltipOpen && (
                <span className="schedule-tooltip" role="tooltip">
                  {schedule.enabled && (schedule.times || []).length > 0 ? (
                    <>
                      <span className="schedule-tooltip-header">
                        Run times ({formatTimezone(schedule.timezone)})
                      </span>
                      {schedule.times.map((t) => (
                        <span key={t} className="schedule-tooltip-row">
                          {t}
                        </span>
                      ))}
                    </>
                  ) : (
                    <span className="schedule-tooltip-row">
                      {!schedule.enabled
                        ? "Scheduler is disabled"
                        : "No run times configured"}
                    </span>
                  )}
                </span>
              )}
            </span>
          )}{" "}
          One URL per line. Invalid URLs are rejected on save.
        </p>
        <textarea
          placeholder="https://example.com/page-1&#10;https://example.com/page-2"
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={saving}
        />
        <div className="file-upload" style={{ marginTop: 8 }}>
          <label style={{ fontSize: 13, color: "#666", marginRight: 8 }}>
            Or upload a .txt file to append:
          </label>
          <input
            type="file"
            accept=".txt"
            onChange={handleFileUpload}
            disabled={saving}
          />
        </div>
        <p className="url-count" style={{ marginTop: 8 }}>
          {validCount} valid URL{validCount !== 1 ? "s" : ""}
          {invalidCount > 0 && (
            <span style={{ color: "#d97706" }}>
              {" "}
              · {invalidCount} invalid (will be dropped)
            </span>
          )}
          {savedCount != null && (
            <span style={{ color: "#999" }}>
              {" "}
              · currently saved: {savedCount}
            </span>
          )}
        </p>
        <div className="form-row">
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? "Saving..." : "Save Watchlist"}
          </button>
        </div>
        {status && (
          <p style={{ marginTop: 12, fontSize: 14, color: "#065f46" }}>
            {status}
          </p>
        )}
        {error && <div className="error-msg">{error}</div>}
      </div>
    </div>
  );
}
