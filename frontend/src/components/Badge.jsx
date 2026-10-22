const TONES = {
  CONFIRMED: "green",
  CANCELLED: "grey",
  RESTOCK: "green",
  CANCELLATION: "blue",
  PURCHASE: "amber",
  ADJUSTMENT: "purple",
  LOW: "red",
  OK: "green",
  INACTIVE: "grey",
};

export default function Badge({ value, label }) {
  return <span className={`badge ${TONES[value] || "grey"}`}>{label || value}</span>;
}
