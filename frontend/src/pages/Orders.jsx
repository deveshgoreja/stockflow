import { useState } from "react";
import { api } from "../api.js";
import Badge from "../components/Badge.jsx";
import Pager from "../components/Pager.jsx";
import { dateTime, money } from "../format.js";
import { useApi } from "../hooks.js";

const PAGE_SIZE = 10;

const newIdempotencyKey = () =>
  globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;

function OrderForm({ onPlaced, notify }) {
  const { data: products } = useApi(
    () => api.listProducts({ is_active: true, limit: 200 }),
    [],
    notify.error,
  );
  const [lines, setLines] = useState([{ product_id: "", quantity: 1 }]);
  // One key per checkout attempt: a double-click or a retry after a network
  // error re-sends the same key, so the server creates the order only once.
  const [idempotencyKey, setIdempotencyKey] = useState(newIdempotencyKey);
  const [submitting, setSubmitting] = useState(false);

  const byId = Object.fromEntries((products?.items || []).map((p) => [String(p.id), p]));
  const estimate = lines.reduce(
    (sum, line) => sum + (byId[line.product_id] ? Number(byId[line.product_id].price) * line.quantity : 0),
    0,
  );

  const updateLine = (index, field, value) =>
    setLines(lines.map((line, i) => (i === index ? { ...line, [field]: value } : line)));

  async function submit(e) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const order = await api.createOrder(
        lines.map((l) => ({ product_id: Number(l.product_id), quantity: Number(l.quantity) })),
        idempotencyKey,
      );
      notify.success(`Order #${order.id} placed — ${money(order.total_amount)}`);
      setLines([{ product_id: "", quantity: 1 }]);
      setIdempotencyKey(newIdempotencyKey());
      onPlaced();
    } catch (error) {
      notify.error(error);
      // A business rejection means the basket must change, so the next attempt
      // is a different request and gets a fresh key. Network errors keep it.
      if (error.status) setIdempotencyKey(newIdempotencyKey());
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="card form" onSubmit={submit}>
      <h2>New order</h2>
      {lines.map((line, index) => {
        const product = byId[line.product_id];
        return (
          <div className="order-line" key={index}>
            <select
              value={line.product_id}
              onChange={(e) => updateLine(index, "product_id", e.target.value)}
              required
            >
              <option value="">Select a product…</option>
              {(products?.items || []).map((p) => (
                <option
                  key={p.id}
                  value={p.id}
                  disabled={lines.some((l, i) => i !== index && l.product_id === String(p.id))}
                >
                  {p.sku} — {p.name} · {money(p.price)} · {p.quantity} in stock
                </option>
              ))}
            </select>
            <input
              type="number"
              min="1"
              value={line.quantity}
              onChange={(e) => updateLine(index, "quantity", e.target.value)}
              required
            />
            <span className="num muted line-total">
              {product ? money(Number(product.price) * line.quantity) : "—"}
            </span>
            <button
              type="button"
              className="link"
              disabled={lines.length === 1}
              onClick={() => setLines(lines.filter((_, i) => i !== index))}
            >
              Remove
            </button>
          </div>
        );
      })}
      <div className="actions spread">
        <button
          type="button"
          className="secondary"
          onClick={() => setLines([...lines, { product_id: "", quantity: 1 }])}
        >
          + Add line
        </button>
        <span>
          Estimated total: <strong>{money(estimate)}</strong>
        </span>
        <button type="submit" disabled={submitting}>
          {submitting ? "Placing…" : "Place order"}
        </button>
      </div>
      <p className="muted small">
        Idempotency-Key: <span className="mono">{idempotencyKey}</span>. Prices are captured when
        the order is placed.
      </p>
    </form>
  );
}

function OrderRow({ order, onCancel }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr className="clickable" onClick={() => setOpen(!open)}>
        <td>{open ? "▾" : "▸"} {order.id}</td>
        <td>{dateTime(order.created_at)}</td>
        <td>{order.items.length}</td>
        <td>
          <Badge value={order.status} />
        </td>
        <td className="num">{money(order.total_amount)}</td>
        <td className="num">
          {order.status === "CONFIRMED" && (
            <button
              className="link danger"
              onClick={(e) => {
                e.stopPropagation();
                onCancel(order);
              }}
            >
              Cancel
            </button>
          )}
        </td>
      </tr>
      {open && (
        <tr className="details">
          <td colSpan={6}>
            <table className="nested">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Product</th>
                  <th className="num">Qty</th>
                  <th className="num">Unit price</th>
                  <th className="num">Line total</th>
                </tr>
              </thead>
              <tbody>
                {order.items.map((item) => (
                  <tr key={item.product_id}>
                    <td className="mono">{item.product_sku}</td>
                    <td>{item.product_name}</td>
                    <td className="num">{item.quantity}</td>
                    <td className="num">{money(item.unit_price)}</td>
                    <td className="num">{money(item.line_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted small">
              Last updated {dateTime(order.updated_at)}
              {order.idempotency_key && (
                <>
                  {" "}· key <span className="mono">{order.idempotency_key}</span>
                </>
              )}
            </p>
          </td>
        </tr>
      )}
    </>
  );
}

export default function Orders({ notify }) {
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);
  // Remounting the form after an order reloads product stock levels in its picker.
  const [formKey, setFormKey] = useState(0);
  const refresh = () => setRefreshKey((k) => k + 1);

  const { data } = useApi(
    () => api.listOrders({ status, limit: PAGE_SIZE, offset }),
    [status, offset, refreshKey],
    notify.error,
  );

  async function cancel(order) {
    if (!window.confirm(`Cancel order #${order.id}? Its stock will be returned to inventory.`)) {
      return;
    }
    try {
      await api.cancelOrder(order.id);
      notify.success(`Order #${order.id} cancelled; stock restored`);
      refresh();
    } catch (error) {
      notify.error(error);
      refresh();
    }
  }

  return (
    <>
      <OrderForm
        key={formKey}
        onPlaced={() => {
          setFormKey((k) => k + 1);
          refresh();
        }}
        notify={notify}
      />
      <section className="card">
        <div className="toolbar">
          <h2>Orders</h2>
          <select
            value={status}
            onChange={(e) => {
              setOffset(0);
              setStatus(e.target.value);
            }}
          >
            <option value="">All statuses</option>
            <option value="CONFIRMED">Confirmed</option>
            <option value="CANCELLED">Cancelled</option>
          </select>
        </div>
        {!data ? (
          <p className="muted">Loading…</p>
        ) : data.items.length === 0 ? (
          <p className="muted">No orders.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Placed</th>
                <th>Items</th>
                <th>Status</th>
                <th className="num">Total</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((order) => (
                <OrderRow key={order.id} order={order} onCancel={cancel} />
              ))}
            </tbody>
          </table>
        )}
        <Pager page={data} onChange={setOffset} />
      </section>
    </>
  );
}
