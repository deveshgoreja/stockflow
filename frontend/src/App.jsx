import { useCallback, useMemo, useState } from "react";
import Notices from "./components/Notices.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Inventory from "./pages/Inventory.jsx";
import Orders from "./pages/Orders.jsx";
import Products from "./pages/Products.jsx";

const TABS = [
  { id: "dashboard", label: "Dashboard", Page: Dashboard },
  { id: "products", label: "Products", Page: Products },
  { id: "inventory", label: "Inventory", Page: Inventory },
  { id: "orders", label: "Orders", Page: Orders },
];

let nextNoticeId = 1;

export default function App() {
  const [tab, setTab] = useState("dashboard");
  const [notices, setNotices] = useState([]);

  const dismiss = useCallback((id) => setNotices((list) => list.filter((n) => n.id !== id)), []);

  const notify = useMemo(() => {
    const push = (notice) => {
      const id = nextNoticeId++;
      setNotices((list) => [...list.slice(-3), { id, ...notice }]);
      if (notice.kind === "success") setTimeout(() => dismiss(id), 4000);
    };
    return {
      success: (message) => push({ kind: "success", message }),
      error: (error) =>
        push({
          kind: "error",
          code: error.code,
          message: error.message,
          details: error.details,
        }),
    };
  }, [dismiss]);

  const { Page } = TABS.find((t) => t.id === tab);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">▣</span> StockFlow
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={t.id === tab ? "tab active" : "tab"}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      <Notices notices={notices} onDismiss={dismiss} />
      <main className="content">
        <Page notify={notify} />
      </main>
    </div>
  );
}
