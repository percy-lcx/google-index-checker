import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

function formatDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;

  const data = payload[0]?.payload;
  return (
    <div className="trend-tooltip">
      <p className="trend-tooltip-date">{label}</p>
      <p className="trend-tooltip-total">Total URLs: {data.total}</p>
      {payload.map((entry) => (
        <p key={entry.dataKey} style={{ color: entry.color }}>
          {entry.name}: {entry.value.toFixed(1)}% ({data[entry.dataKey.replace("_pct", "_count")] ?? "–"} URLs)
        </p>
      ))}
    </div>
  );
}

export default function TrendChart({ checks }) {
  const completed = checks
    .filter((c) => c.status === "completed")
    .sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

  if (completed.length < 2) return null;

  const data = completed.map((c) => {
    const total = c.url_count || 1;
    return {
      date: formatDate(c.created_at),
      indexed_pct: (c.indexed_count / total) * 100,
      not_indexed_pct: (c.not_indexed_count / total) * 100,
      error_pct: (c.error_count / total) * 100,
      indexed_count: c.indexed_count,
      not_indexed_count: c.not_indexed_count,
      error_count: c.error_count,
      total,
    };
  });

  return (
    <div className="card trend-chart-card">
      <h2>Indexing Status Trend</h2>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="date" tick={{ fontSize: 12 }} />
          <YAxis
            yAxisId="left"
            domain={[0, 100]}
            tickFormatter={(v) => `${v}%`}
            tick={{ fontSize: 12 }}
            width={48}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            tick={{ fontSize: 12 }}
            width={48}
            label={{ value: "URLs", angle: 90, position: "insideRight", fontSize: 11, fill: "#9ca3af" }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="indexed_pct"
            name="Indexed %"
            stroke="#059669"
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
          />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="not_indexed_pct"
            name="Not Indexed %"
            stroke="#dc2626"
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
          />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="error_pct"
            name="Error %"
            stroke="#6b7280"
            strokeWidth={1.5}
            strokeDasharray="4 2"
            dot={{ r: 2 }}
          />
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="total"
            name="Total URLs"
            stroke="#9ca3af"
            strokeWidth={1}
            strokeDasharray="6 3"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
