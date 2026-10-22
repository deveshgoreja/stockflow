function ErrorDetails({ details }) {
  if (!details) return null;
  if (details.shortages) {
    return (
      <ul className="notice-details">
        {details.shortages.map((s) => (
          <li key={s.product_id}>
            {s.sku || `Product #${s.product_id}`}: requested {s.requested}, available{" "}
            {s.available}
          </li>
        ))}
      </ul>
    );
  }
  if (details.errors) {
    return (
      <ul className="notice-details">
        {details.errors.map((e, i) => (
          <li key={i}>
            {e.loc.slice(1).join(".") || e.loc.join(".")}: {e.msg}
          </li>
        ))}
      </ul>
    );
  }
  return null;
}

export default function Notices({ notices, onDismiss }) {
  if (!notices.length) return null;
  return (
    <div className="notices" role="status">
      {notices.map((n) => (
        <div key={n.id} className={`notice ${n.kind}`}>
          <div>
            {n.code && <span className="notice-code">{n.code}</span>}
            <span>{n.message}</span>
            <ErrorDetails details={n.details} />
          </div>
          <button className="link" aria-label="Dismiss" onClick={() => onDismiss(n.id)}>
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
