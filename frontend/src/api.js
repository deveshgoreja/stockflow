const BASE_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function request(path, { method = "GET", body, headers = {}, params } = {}) {
  const url = new URL(BASE_URL + path);
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  });

  let response;
  try {
    response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json", ...headers },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", `Cannot reach the API at ${BASE_URL}`);
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = data?.error;
    throw new ApiError(
      response.status,
      error?.code || "HTTP_ERROR",
      error?.message || `Request failed with status ${response.status}`,
      error?.details,
    );
  }
  return data;
}

export const api = {
  summary: () => request("/reports/summary"),

  listProducts: (params) => request("/products", { params }),
  createProduct: (body) => request("/products", { method: "POST", body }),
  updateProduct: (id, body) => request(`/products/${id}`, { method: "PATCH", body }),

  listInventory: (params) => request("/inventory", { params }),
  adjustInventory: (body) => request("/inventory/adjustments", { method: "POST", body }),
  listMovements: (params) => request("/inventory/movements", { params }),

  listOrders: (params) => request("/orders", { params }),
  createOrder: (items, idempotencyKey) =>
    request("/orders", {
      method: "POST",
      body: { items },
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  cancelOrder: (id) => request(`/orders/${id}/cancel`, { method: "POST" }),
};
