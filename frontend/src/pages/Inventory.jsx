import { useState } from "react";
import { api } from "../api.js";
import Badge from "../components/Badge.jsx";
import Pager from "../components/Pager.jsx";
import { dateTime, signed } from "../format.js";
import { useApi } from "../hooks.js";

const PAGE_SIZE = 15;

function AdjustForm({ products, productId, onProductChange, onDone, notify }) {
  const [type, setType] = useState("RESTOCK");
  const [quantity, setQuantity] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(e) {
    e.preventDefault();
    const amount = Math.abs(Number(quantity));
    // RESTOCK always adds; "Remove" adjustments are sent as negative changes.
    const change = type === "REMOVE" ? -amount : amount;
    setSaving(true);
    try {
      const movement = await api.adjustInventory({
        product_id: Number(productId),
        change_quantity: change,
        movement_type: type === "RESTOCK" ? "RESTOCK" : "ADJUSTMENT",
        note: note || null,
      });
      notify.success(
        `${movement.product_sku}: ${signed(movement.change_quantity)} → ${movement.resulting_quantity} on hand`,
      );
      setQuantity("");
      setNote("");
      onDone();
    } catch (error) {
      notify.error(error);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="card form" onSubmit={submit}>
      <h2>Restock / adjust</h2>
      <div className="form-grid">
        <label>
          Product
          <select value={productId} onChange={(e) => onProductChange(e.target.value)} required>
            <option value="">Select a product…</option>
            {products.map((p) => (
              <option key={p.product_id} value={p.product_id}>
                {p.sku} — {p.name} ({p.quantity} on hand)
              </option>
            ))}
          </select>
        </label>
        <label>
          Action
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="RESTOCK">Restock (receive goods)</option>
            <option value="ADD">Adjustment: add (e.g. count correction)</option>
            <option value="REMOVE">Adjustment: remove (e.g. damaged)</option>
          </select>
        </label>
        <label>
          Quantity
          <input
            type="number"
            min="1"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            required
          />
        </label>
        <label>
          Note
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. PO-1042, water damage"
            maxLength={500}
          />
        </label>
      </div>
      <div className="actions">
        <button type="submit" disabled={saving}>
          {saving ? "Saving…" : "Apply"}
        </button>
      </div>
    </form>
  );
}

function Movements({ productId, products, refreshKey, notify }) {
  const [filter, setFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const { data } = useApi(
    () => api.listMovements({ product_id: filter, limit: PAGE_SIZE, offset }),
    [filter, offset, refreshKey],
    notify.error,
  );

  return (
    <section className="card">
      <div className="toolbar">
        <h2>Movement history</h2>
        <select
          value={filter}
          onChange={(e) => {
            setOffset(0);
            setFilter(e.target.value);
          }}
        >
          <option value="">All products</option>
          {products.map((p) => (
            <option key={p.product_id} value={p.product_id}>
              {p.sku} — {p.name}
            </option>
          ))}
        </select>
        {productId && productId !== filter && (
          <button
            className="link"
            onClick={() => {
              setOffset(0);
              setFilter(String(productId));
            }}
          >
            Show selected product
          </button>
        )}
      </div>
      {!data ? (
        <p className="muted">Loading…</p>
      ) : data.items.length === 0 ? (
        <p className="muted">No movements recorded.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>When</th>
              <th>Product</th>
              <th>Type</th>
              <th className="num">Change</th>
              <th className="num">Resulting</th>
              <th>Reference / note</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((m) => (
              <tr key={m.id}>
                <td className="muted">{m.id}</td>
                <td>{dateTime(m.created_at)}</td>
                <td>
                  <span className="mono">{m.product_sku}</span> {m.product_name}
                </td>
                <td>
                  <Badge value={m.movement_type} />
                </td>
                <td className={`num ${m.change_quantity < 0 ? "danger" : "good"}`}>
                  {signed(m.change_quantity)}
                </td>
                <td className="num">{m.resulting_quantity}</td>
                <td className="muted">
                  {[m.order_id && `Order #${m.order_id}`, m.note].filter(Boolean).join(" · ") || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <Pager page={data} onChange={setOffset} />
    </section>
  );
}

export default function Inventory({ notify }) {
  const [lowOnly, setLowOnly] = useState(false);
  const [selected, setSelected] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const { data: all } = useApi(
    () => api.listInventory({ limit: 200 }),
    [refreshKey],
    notify.error,
  );
  const rows = all ? all.items.filter((row) => !lowOnly || (row.is_active && row.is_low_stock)) : [];

  return (
    <>
      <AdjustForm
        products={all?.items || []}
        productId={selected}
        onProductChange={setSelected}
        onDone={() => setRefreshKey((k) => k + 1)}
        notify={notify}
      />

      <section className="card">
        <div className="toolbar">
          <h2>Stock levels</h2>
          <label className="checkbox">
            <input type="checkbox" checked={lowOnly} onChange={(e) => setLowOnly(e.target.checked)} />
            Low stock only
          </label>
        </div>
        {!all ? (
          <p className="muted">Loading…</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>SKU</th>
                <th>Product</th>
                <th>Category</th>
                <th className="num">On hand</th>
                <th className="num">Threshold</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.product_id} className={String(row.product_id) === selected ? "selected" : ""}>
                  <td className="mono">{row.sku}</td>
                  <td>{row.name}</td>
                  <td>{row.category || "—"}</td>
                  <td className={`num ${row.is_low_stock ? "danger" : ""}`}>{row.quantity}</td>
                  <td className="num">{row.low_stock_threshold}</td>
                  <td>
                    {!row.is_active ? (
                      <Badge value="INACTIVE" label="Inactive" />
                    ) : row.is_low_stock ? (
                      <Badge value="LOW" label="Low stock" />
                    ) : (
                      <Badge value="OK" label="OK" />
                    )}
                  </td>
                  <td className="num">
                    <button className="link" onClick={() => setSelected(String(row.product_id))}>
                      Adjust
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <Movements
        productId={selected}
        products={all?.items || []}
        refreshKey={refreshKey}
        notify={notify}
      />
    </>
  );
}
