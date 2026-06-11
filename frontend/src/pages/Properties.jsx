import { useState, useEffect } from "react";
import { getProperties, createProperty, updateProperty, deleteProperty } from "../api/client";

const emptyForm = { name: "", site_url: "", path_pattern: "", sort_order: 0 };

export default function Properties() {
  const [properties, setProperties] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);

  const fetchProperties = () => {
    getProperties()
      .then(setProperties)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchProperties(); }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      if (editingId) {
        await updateProperty(editingId, form);
      } else {
        await createProperty(form);
      }
      setForm(emptyForm);
      setEditingId(null);
      setShowForm(false);
      fetchProperties();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleEdit = (p) => {
    setForm({
      name: p.name,
      site_url: p.site_url,
      path_pattern: p.path_pattern,
      sort_order: p.sort_order,
    });
    setEditingId(p.id);
    setShowForm(true);
    setError(null);
  };

  const handleDelete = async (p) => {
    if (!window.confirm(`Delete property "${p.name}"?`)) return;
    try {
      await deleteProperty(p.id);
      fetchProperties();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleCancel = () => {
    setForm(emptyForm);
    setEditingId(null);
    setShowForm(false);
    setError(null);
  };

  if (loading) return <div className="card">Loading...</div>;

  return (
    <div>
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h2 style={{ margin: 0 }}>Search Console Properties</h2>
          {!showForm && (
            <button className="btn btn-primary" onClick={() => { setShowForm(true); setEditingId(null); setForm(emptyForm); }}>
              Add Property
            </button>
          )}
        </div>

        <p style={{ color: "#999", fontSize: 14, marginBottom: 16 }}>
          Each verified Search Console property has its own 2,000/day URL Inspection quota. Configure one row per property and route URLs via path pattern — URLs for <code>/en/*</code> use the <code>/en/</code> property's quota, <code>/th/*</code> uses the <code>/th/</code> property's, etc. Lower priority = matched first (use it to put more specific patterns before broader ones).
        </p>

        {properties.length === 0 && !showForm ? (
          <p style={{ color: "#999" }}>
            No properties configured. The tool will fall back to the single property set in <code>GSC_PROPERTY_URL</code>.
          </p>
        ) : (
          <div className="results-table-wrapper">
            <table className="results-table">
              <thead>
                <tr>
                  <th>Priority</th>
                  <th>Name</th>
                  <th>Site URL</th>
                  <th>Path Pattern</th>
                  <th style={{ width: 120 }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {properties.map((p) => (
                  <tr key={p.id}>
                    <td>{p.sort_order}</td>
                    <td><strong>{p.name}</strong></td>
                    <td><code>{p.site_url}</code></td>
                    <td><code>{p.path_pattern}</code></td>
                    <td>
                      <button className="btn btn-secondary btn-sm" onClick={() => handleEdit(p)} style={{ marginRight: 4 }}>
                        Edit
                      </button>
                      <button className="btn btn-danger btn-sm" onClick={() => handleDelete(p)}>
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
                {properties.length === 0 && (
                  <tr>
                    <td colSpan={5} style={{ textAlign: "center", color: "#999" }}>
                      No properties yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showForm && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>{editingId ? "Edit Property" : "Add Property"}</h3>
          <form onSubmit={handleSubmit}>
            <div className="form-grid">
              <div className="form-field">
                <label>Name</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="e.g. English"
                  required
                />
              </div>
              <div className="form-field">
                <label>Site URL (GSC property identifier)</label>
                <input
                  type="text"
                  value={form.site_url}
                  onChange={(e) => setForm({ ...form, site_url: e.target.value })}
                  placeholder="e.g. https://www.tmgm.com/en/ or sc-domain:tmgm.com"
                  required
                />
              </div>
              <div className="form-field">
                <label>Path Pattern</label>
                <input
                  type="text"
                  value={form.path_pattern}
                  onChange={(e) => setForm({ ...form, path_pattern: e.target.value })}
                  placeholder="e.g. /en/*"
                  required
                />
              </div>
              <div className="form-field">
                <label>Priority (lower = matched first)</label>
                <input
                  type="number"
                  value={form.sort_order}
                  onChange={(e) => setForm({ ...form, sort_order: parseInt(e.target.value) || 0 })}
                />
              </div>
            </div>
            {error && <div className="error-msg">{error}</div>}
            <div className="form-row" style={{ marginTop: 12 }}>
              <button type="submit" className="btn btn-primary">
                {editingId ? "Update" : "Create"}
              </button>
              <button type="button" className="btn btn-secondary" onClick={handleCancel} style={{ marginLeft: 8 }}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
