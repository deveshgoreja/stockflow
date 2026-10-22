// The API sends money as decimal strings ("19.99") so no precision is lost in
// transit; they are only turned into numbers here, for display.
const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export const money = (value) => currency.format(Number(value || 0));

export const dateTime = (value) =>
  new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

export const signed = (value) => (value > 0 ? `+${value}` : String(value));
