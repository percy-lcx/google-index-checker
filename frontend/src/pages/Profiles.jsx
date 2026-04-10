import { useState, useEffect } from "react";
import { getProfiles, createProfile, updateProfile, deleteProfile } from "../api/client";

const emptyForm = { name: "", path_pattern: "", credentials_path: "", token_path: "", sort_order: 0 };

export default function Profiles() {
  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);

  const fetchProfiles = () => {
    getProfiles()
      .then(setProfiles)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchProfiles(); }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      if (editingId) {
        await updateProfile(editingId, form);
      } else {
        await createProfile(form);
      }
      setForm(emptyForm);
      setEditingId(null);
      setShowForm(false);
      fetchProfiles();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleEdit = (p) => {
    setForm({
      name: p.name,
      path_pattern: p.path_pattern,
      credentials_path: p.credentials_path,
      token_path: p.token_path,
      sort_order: p.sort_order,
    });
    setEditingId(p.id);
    setShowForm(true);
    setError(null);
  };

  const handleDelete = async (p) => {
    if (!window.confirm(`Delete profile "${p.name}"?`)) return;
    try {
      await deleteProfile(p.id);
      fetchProfiles();
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
          <h2 style={{ margin: 0 }}>Credential Profiles</h2>
          {!showForm && (
            <button className="btn btn-primary" onClick={() => { setShowForm(true); setEditingId(null); setForm(emptyForm); }}>
              Add Profile
            </button>
          )}
        </div>

        <p style={{ color: "#999", fontSize: 14, marginBottom: 16 }}>
          Each profile uses a separate Google Cloud project credential, giving you an additional 2,000 inspections/day per profile.
          URLs are matched to profiles by path pattern (sorted by priority order).
        </p>

        {profiles.length === 0 && !showForm ? (
          <p style={{ color: "#999" }}>
            No profiles configured. The tool will use the default credentials from .env.
          </p>
        ) : (
          <div className="results-table-wrapper">
            <table className="results-table">
              <thead>
                <tr>
                  <th>Priority</th>
                  <th>Name</th>
                  <th>Path Pattern</th>
                  <th>Credentials File</th>
                  <th>Token File</th>
                  <th style={{ width: 120 }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map((p) => (
                  <tr key={p.id}>
                    <td>{p.sort_order}</td>
                    <td><strong>{p.name}</strong></td>
                    <td><code>{p.path_pattern}</code></td>
                    <td><code>{p.credentials_path}</code></td>
                    <td><code>{p.token_path}</code></td>
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
                {profiles.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: "center", color: "#999" }}>
                      No profiles yet.
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
          <h3>{editingId ? "Edit Profile" : "Add Profile"}</h3>
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
                <label>Credentials File</label>
                <input
                  type="text"
                  value={form.credentials_path}
                  onChange={(e) => setForm({ ...form, credentials_path: e.target.value })}
                  placeholder="e.g. ./credentials-en.json"
                  required
                />
              </div>
              <div className="form-field">
                <label>Token File</label>
                <input
                  type="text"
                  value={form.token_path}
                  onChange={(e) => setForm({ ...form, token_path: e.target.value })}
                  placeholder="e.g. ./token-en.json"
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
