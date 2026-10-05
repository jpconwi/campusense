/* api.js - the only place that talks to the FastAPI backend. */

let csrfToken = "";
let onUnauthorized = () => {};

export const setCsrfToken = (token) => { csrfToken = token || ""; };
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn; };

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

/**
 * api("/api/ask", { method: "POST", json: {...} })
 * api("/api/concerns", { method: "POST", form: formData })
 * Errors from the server look like {"error": "message"} and become ApiError.
 */
export async function api(path, { method = "GET", json, form } = {}) {
  const headers = {};
  let body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form) {
    body = form;                      // the browser sets the multipart boundary itself
  }
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken;

  const response = await fetch(path, { method, headers, body, credentials: "same-origin" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) onUnauthorized();
    throw new ApiError(response.status, data.error || "Something went wrong. Please try again.");
  }
  return data;
}

export const slug = (value) => String(value || "").toLowerCase().replace(/ /g, "-");

export const padId = (id) => String(id).padStart(4, "0");
