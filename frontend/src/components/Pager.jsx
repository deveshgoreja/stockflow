export default function Pager({ page, onChange }) {
  if (!page || page.total <= page.limit) return null;
  const { total, limit, offset } = page;
  const last = Math.min(offset + limit, total);
  return (
    <div className="pager">
      <button disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
        ← Prev
      </button>
      <span>
        {offset + 1}–{last} of {total}
      </span>
      <button disabled={last >= total} onClick={() => onChange(offset + limit)}>
        Next →
      </button>
    </div>
  );
}
