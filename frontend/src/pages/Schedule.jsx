import { useState, useEffect } from "react";
import { getSchedule, saveSchedule } from "../api/client";

const REGION_TIMEZONES = [
  "Asia/Hong_Kong",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Asia/Kolkata",
  "Australia/Sydney",
  "Europe/London",
  "Europe/Paris",
  "America/New_York",
  "America/Los_Angeles",
];

// UTC offsets from -12 to +14. IANA Etc/GMT signs are reversed from common
// usage: Etc/GMT-8 actually means UTC+8. We store the IANA name but show
// the human-readable label.
const GMT_OFFSETS = (() => {
  const list = [{ value: "UTC", label: "UTC" }];
  for (let offset = -12; offset <= 14; offset++) {
    if (offset === 0) continue;
    const sign = offset > 0 ? "+" : "-";
    const label = `GMT${sign}${Math.abs(offset)}`;
    const value = `Etc/GMT${offset > 0 ? "-" : "+"}${Math.abs(offset)}`;
    list.push({ value, label });
  }
  return list;
})();

function formatRegionLabel(tz) {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: tz,
      timeZoneName: "shortOffset",
    }).formatToParts(new Date());
    const offset = parts.find((p) => p.type === "timeZoneName")?.value;
    return offset ? `${tz} (${offset})` : tz;
  } catch {
    return tz;
  }
}

export default function Schedule() {
  const [enabled, setEnabled] = useState(true);
  const [times, setTimes] = useState([]);
  const [timezone, setTimezone] = useState("Asia/Hong_Kong");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getSchedule()
      .then((s) => {
        setEnabled(s.enabled);
        setTimes(s.times || []);
        setTimezone(s.timezone || "Asia/Hong_Kong");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const addTime = () => setTimes([...times, "09:00"]);
  const removeTime = (i) => setTimes(times.filter((_, idx) => idx !== i));
  const updateTime = (i, v) =>
    setTimes(times.map((t, idx) => (idx === i ? v : t)));

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setStatus(null);
    try {
      const result = await saveSchedule({ times, timezone, enabled });
      setTimes(result.times || []);
      setTimezone(result.timezone);
      setEnabled(result.enabled);
      setStatus(
        result.enabled
          ? `Schedule saved. ${result.times.length} run${result.times.length !== 1 ? "s" : ""} per day, jobs reloaded.`
          : "Schedule saved. Scheduler is currently disabled."
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="card">Loading...</div>;

  const knownValues = new Set([
    ...REGION_TIMEZONES,
    ...GMT_OFFSETS.map((o) => o.value),
  ]);
  const showCustom = !knownValues.has(timezone);

  return (
    <div>
      <div className="card">
        <h2>Schedule</h2>
        <p style={{ fontSize: 14, color: "#666", marginBottom: 16 }}>
          Configure when the watchlist is checked automatically. Changes apply
          immediately without a restart.
        </p>

        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: 14, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              style={{ marginRight: 8 }}
            />
            Scheduler enabled
          </label>
        </div>

        <div className="form-field" style={{ marginBottom: 20, maxWidth: 320 }}>
          <label>Timezone</label>
          <select
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            style={{
              padding: "8px 10px",
              border: "1px solid #ddd",
              borderRadius: 6,
              fontSize: 14,
              background: "white",
            }}
          >
            {showCustom && (
              <option value={timezone}>{formatRegionLabel(timezone)}</option>
            )}
            <optgroup label="Regions">
              {REGION_TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {formatRegionLabel(tz)}
                </option>
              ))}
            </optgroup>
            <optgroup label="UTC Offsets">
              {GMT_OFFSETS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </optgroup>
          </select>
        </div>

        <div style={{ marginBottom: 20 }}>
          <label
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: "#555",
              display: "block",
              marginBottom: 6,
            }}
          >
            Run times
          </label>
          {times.length === 0 && (
            <p style={{ fontSize: 13, color: "#999", marginBottom: 8 }}>
              No times configured. Scheduling is effectively paused.
            </p>
          )}
          {times.map((t, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                gap: 8,
                alignItems: "center",
                marginBottom: 6,
              }}
            >
              <input
                type="time"
                value={t}
                onChange={(e) => updateTime(i, e.target.value)}
                style={{
                  padding: "6px 10px",
                  border: "1px solid #ddd",
                  borderRadius: 6,
                  fontSize: 14,
                }}
              />
              <button
                className="btn btn-sm btn-secondary"
                onClick={() => removeTime(i)}
              >
                Remove
              </button>
            </div>
          ))}
          <button
            className="btn btn-sm btn-secondary"
            onClick={addTime}
            style={{ marginTop: 4 }}
          >
            + Add time
          </button>
        </div>

        <div className="form-row">
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? "Saving..." : "Save Schedule"}
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
