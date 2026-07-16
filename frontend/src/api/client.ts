import axios, { AxiosError } from "axios";
import { useAuthStore } from "../store/authStore";

export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
export const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000";
// mediamtx's own host:port for its built-in per-path WebRTC viewer page —
// used by the Live Grid to embed each camera's feed directly, no backend
// video proxying needed.
export const MEDIAMTX_WEBRTC_URL = import.meta.env.VITE_MEDIAMTX_WEBRTC_URL ?? "http://localhost:8889";

export const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  withCredentials: true, // send the HttpOnly refresh cookie
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

async function doRefresh(): Promise<string> {
  const { user } = useAuthStore.getState();
  // No body at all — the backend's RefreshRequest schema requires
  // refresh_token if a body is sent, so `{}` would 422. Sending nothing lets
  // FastAPI fall through to the httpOnly cookie the backend set on
  // login/refresh, forwarded automatically via withCredentials.
  const resp = await axios.post(
    `${API_URL}/api/v1/auth/refresh`,
    undefined,
    { withCredentials: true }
  );
  const data = resp.data.data;
  useAuthStore.getState().setSession({
    access_token: data.access_token,
    user: user!,
    is_master_session: useAuthStore.getState().isMasterSession,
  });
  return data.access_token;
}

let refreshPromise: Promise<string> | null = null;

// The refresh cookie is single-use/rotating (backend revokes it and issues a
// new one on every call) — two concurrent callers would otherwise race, with
// the second getting a 401 on the now-revoked cookie and clearing the
// session the first call just established. Every caller (the 401 retry
// below, and AuthBootstrap's boot-time silent refresh, which React
// StrictMode can double-invoke in dev) shares one in-flight request instead.
export function refreshAccessToken(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as (typeof error.config & { _retry?: boolean });
    if (error.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      try {
        const token = await refreshAccessToken();
        original.headers = original.headers ?? {};
        (original.headers as any).Authorization = `Bearer ${token}`;
        return api(original);
      } catch {
        useAuthStore.getState().clearSession();
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);
