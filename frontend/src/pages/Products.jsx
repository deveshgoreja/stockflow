import { useState } from "react";
import { api } from "../api.js";
import Badge from "../components/Badge.jsx";
import Pager from "../components/Pager.jsx";
import { money } from "../format.js";
import { useApi } from "../hooks.js";

const PAGE_SIZE = 15;
const EMPTY_FORM = {
  sku: "",
  name: "",
  description: "",
  price: "",
  category: "",
  low_stock_threshold: 5,
  is_active: true,
};

function ProductForm({ product, onSaved, onCancel, notify }) {
  const [form, setForm] = useState(() =>
    product
      ? {
          ...EMPTY_FORM,
          ...product,
          description: product.description || "",
          category: product.category || "",
        }
      : EMPTY_FORM,
  );
  const [saving, setSaving] = useState(false);
  const set = (field) => (e) =>
    setForm({ ...form, [field]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  async function submit(e) {
    e.preventDefault();
    setSaving(true);
    const body = {
      sku: form.sku,
      name: form.name,
      description: form.description || null,
      price: form.price,
      category: form.category || null,
      low_stock_threshold: Number(form.low_stock_threshold),
      is_active: form.is_active,
    };
    try {
      const saved = product
        ? await api.updateProduct(product.id, body)
        : await api.createProduct(body);
      notify.success(`${product ? "Updated" : "Created"} ${saved.sku}`);
      onSaved();
    } catch (error) {
      notify.error(error);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="card form" onSubmit={submit}>
      <h2>{product ? `Edit ${product.sku}` : "New product"}</h2>
      <div className="form-grid">
        <label>
          SKU
          <input value={form.sku} onChange={set("sku")} required maxLength={64} />
        </label>
        <label>
          Name
          <input value={form.name} onChange={set("name")} required maxLength={200} />
        </label>
        <label>
          Price
          <input
            type="number"
            min="0"
            step="0.01"
            value={form.price}
            onChange={set("price")}
            required
          />
        </label>
        <label>
          Category
          <input value={form.category} onChange={set("category")} maxLength={100} />
        </label>
        <label>
          Low-stock threshold
          <input
            type="number"
            min="0"
            value={form.low_stock_threshold}
            onChange={set("low_stock_threshold")}
            required
          />
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={form.is_active} onChange={set("is_active")} />
          Active (can be ordered)
        </label>
        <label className="wide">
          Description
          <textarea rows={2} value={form.description} onChange={set("description")} />
        </label>
      </div>
      {!product && (
        <p className="muted small">New products start with 0 units. Restock them from Inventory.</p>
      )}
      <div className="actions">
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save product"}
        </button>
      </div>
    </form>
  );
}

export default function Products({ notify }) {
  const [filters, setFilters] = useState({ search: "", category: "", is_active: "" });
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState(null);

  const { data, reload } = useApi(
    () => api.listProducts({ ...filters, limit: PAGE_SIZE, offset }),
    [filters, offset],
    notify.error,
  );

  const setFilter = (field) => (e) => {
    setOffset(0);
    setFilters({ ...filters, [field]: e.target.value });
  };

  return (
    <>
      {editing && (
        <ProductForm
          key={editing === "new" ? "new" : editing.id}
          product={editing === "new" ? null : editing}
          notify={notify}
          onCancel={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}

      <section className="card">
        <div className="toolbar">
          <h2>Products</h2>
          <input
            placeholder="Search name or SKU"
            value={filters.search}
            onChange={setFilter("search")}
          />
          <input placeholder="Category" value={filters.category} onChange={setFilter("category")} />
          <select value={filters.is_active} onChange={setFilter("is_active")}>
            <option value="">All statuses</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
          <button onClick={() => setEditing("new")}>+ New product</button>
        </div>

        {!data ? (
          <p className="muted">Loading…</p>
        ) : data.items.length === 0 ? (
          <p className="muted">No products match.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>SKU</th>
                <th>Name</th>
                <th>Category</th>
                <th className="num">Price</th>
                <th className="num">Stock</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((p) => (
                <tr key={p.id}>
                  <td className="mono">{p.sku}</td>
                  <td>{p.name}</td>
                  <td>{p.category || "—"}</td>
                  <td className="num">{money(p.price)}</td>
                  <td className={`num ${p.quantity <= p.low_stock_threshold ? "danger" : ""}`}>
                    {p.quantity}
                  </td>
                  <td>
                    <Badge value={p.is_active ? "OK" : "INACTIVE"} label={p.is_active ? "Active" : "Inactive"} />
                  </td>
                  <td className="num">
                    <button className="link" onClick={() => setEditing(p)}>
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <Pager page={data} onChange={setOffset} />
      </section>
    </>
  );
}
