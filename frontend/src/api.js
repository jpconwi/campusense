/* api.js - the only place that talks to the FastAPI backend. */

const API_BASE = import.meta.env.VITE_API_URL || "";

export const apiUrl = (path) => `${API_BASE}${path}`;

let csrfToken = "";
let onUnauthorized = () => {};

export const setCsrfToken = (token) => {
  csrfToken = token || "";
};

export const setUnauthorizedHandler = (fn) => {
  onUnauthorized = fn;
};

export class ApiError extends Error {
  constructor(status, message, missing = []) {
    super(message);
    this.status = status;
    this.missing = missing;
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

  const url = apiUrl(path);

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
      data.message || data.error || "Something went wrong. Please try again.",
      Array.isArray(data.missing) ? data.missing : []
    );
  }

  return data;
}

export async function downloadApi(path, { method = "POST" } = {}) {
  const response = await fetch(apiUrl(path), {
    method,
    headers: method === "GET" ? {} : { "X-CSRF-Token": csrfToken },
    credentials: "include",
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) onUnauthorized();
    throw new ApiError(response.status,
      data.detail || data.message || data.error || "The file could not be downloaded.",
      Array.isArray(data.missing) ? data.missing : []);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") || "";
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || "nemsai-export.zip";
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  return blob.size;
}

export const slug = (value) =>
  String(value || "").toLowerCase().replace(/ /g, "-");

export const padId = (id) =>
  String(id).padStart(4, "0");
