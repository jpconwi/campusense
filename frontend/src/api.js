/* api.js - the only place that talks to the FastAPI backend. */

const API_BASE = import.meta.env.VITE_API_URL || "";

let csrfToken = "";
let onUnauthorized = () => {};

export const setCsrfToken = (token) => {
  csrfToken = token || "";
};

export const setUnauthorizedHandler = (fn) => {
  onUnauthorized = fn;
};

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

/**
 * Example:
 * api("/api/auth/me")
 *
 * The request will be sent to:
 * VITE_API_URL + /api/auth/me
 */
export async function api(path, { method = "GET", json, form } = {}) {
  const headers = {};
  let body;

  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form) {
    body = form;
  }

  if (method !== "GET") {
    headers["X-CSRF-Token"] = csrfToken;
  }

  const url = `${API_BASE}${path}`;

  const response = await fetch(url, {
    method,
    headers,
    body,
    credentials: "include",
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    if (response.status === 401) {
      onUnauthorized();
    }

    throw new ApiError(
      response.status,
      data.error || "Something went wrong. Please try again."
    );
  }

  return data;
}

export const slug = (value) =>
  String(value || "").toLowerCase().replace(/ /g, "-");

export const padId = (id) =>
  String(id).padStart(4, "0");