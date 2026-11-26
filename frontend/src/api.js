// Base URL for every backend request. Override it per environment with
// VITE_API_BASE_URL (for example, http://127.0.0.1:8000/api/v1).
const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, details = {}) { super(message); Object.assign(this, details); }
}

/**
 * Shared client for all backend endpoints.
 * The backend always returns { success, data, error, request_id }; this helper
 * unwraps `data` and converts backend errors into ApiError instances.
 */
export async function api(path, { method = "GET", body, timeoutMs = 20000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(API_BASE + path, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const envelope = await response.json().catch(() => null);
    if (!response.ok || !envelope?.success) {
      const error = envelope?.error;
      throw new ApiError(error?.message || `Request failed (${response.status})`, { code: error?.code, details: error?.details || [], status: response.status, requestId: envelope?.request_id });
    }
    return envelope.data;
  } catch (error) {
    if (error.name === "AbortError") throw new ApiError("The backend took too long to respond.", { code: "TIMEOUT" });
    throw error;
  } finally { clearTimeout(timer); }
}

export const SESSION_KEY = "red-thread-session-v1";

/**
 * GET /sessions/{session_id} resumes the session stored by this browser.
 * POST /sessions creates a new session when none exists or the backend returns
 * SESSION_NOT_FOUND after an in-memory backend restart.
 */
export async function getOrCreateSession(caseId) {
  const stored = localStorage.getItem(SESSION_KEY);
  if (stored) {
    try { return await api(`/sessions/${encodeURIComponent(stored)}`); }
    catch (error) { if (error.status !== 404) throw error; }
  }
  const created = await api("/sessions", { method: "POST", body: { case_id: caseId } });
  localStorage.setItem(SESSION_KEY, created.session_id);
  return created.state;
}
