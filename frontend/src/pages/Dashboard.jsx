import { api } from "../api.js";
import Badge from "../components/Badge.jsx";
import { dateTime, money, signed } from "../format.js";
import { useApi } from "../hooks.js";

function Stat({ label, value, tone }) {
  return (
    <div className={`stat ${tone || ""}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

export default function Dashboard({ notify }) {
  const { data } = useApi(
    () =>
      Promise.all([
        api.summary(),
        api.listInventory({ low_stock: true, limit: 10 }),
        api.listOrders({ limit: 6 }),
        api.listMovements({ limit: 8 }),
      ]),
    [],
    notify.error,
  );

  if (!data) return <p className="muted">Loading dashboard…</p>;
  const [summary, lowStock, orders, movements] = data;

  return (
    <>
      <section className="stats">
        <Stat label="Active products" value={summary.active_products} />
        <Stat label="Units in stock" value={summary.total_units_in_stock} />
        <Stat
          label="Low-stock items"
          value={summary.low_stock_count}
          tone={summary.low_stock_count ? "warn" : ""}
        />
        <Stat label="Confirmed orders" value={summary.confirmed_orders} />
        <Stat label="Cancelled orders" value={summary.cancelled_orders} />
        <Stat label="Units sold" value={summary.units_sold} />
        <Stat label="Sales (confirmed)" value={money(summary.total_sales)} tone="good" />
      </section>

      <div className="grid-2">
        <section className="card">
          <h2>Low stock</h2>
          {lowStock.items.length === 0 ? (
            <p className="muted">Everything is above its threshold.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Product</th>
                  <th className="num">On hand</th>
                  <th className="num">Threshold</th>
                </tr>
              </thead>
              <tbody>
                {lowStock.items.map((row) => (
                  <tr key={row.product_id}>
                    <td className="mono">{row.sku}</td>
                    <td>{row.name}</td>
                    <td className="num danger">{row.quantity}</td>
                    <td className="num">{row.low_stock_threshold}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="card">
          <h2>Recent orders</h2>
          {orders.items.length === 0 ? (
            <p className="muted">No orders yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Placed</th>
                  <th>Status</th>
                  <th className="num">Total</th>
                </tr>
              </thead>
              <tbody>
                {orders.items.map((order) => (
                  <tr key={order.id}>
                    <td>{order.id}</td>
                    <td>{dateTime(order.created_at)}</td>
                    <td>
                      <Badge value={order.status} />
                    </td>
                    <td className="num">{money(order.total_amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>

      <section className="card">
        <h2>Latest stock movements</h2>
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Product</th>
              <th>Type</th>
              <th className="num">Change</th>
              <th className="num">Resulting</th>
              <th>Reference</th>
            </tr>
          </thead>
          <tbody>
            {movements.items.map((m) => (
              <tr key={m.id}>
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
                <td className="muted">{m.order_id ? `Order #${m.order_id}` : m.note || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
