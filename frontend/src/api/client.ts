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

let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const { refreshToken, user } = useAuthStore.getState();
  const resp = await axios.post(
    `${API_URL}/api/v1/auth/refresh`,
    refreshToken ? { refresh_token: refreshToken } : {},
    { withCredentials: true }
  );
  const data = resp.data.data;
  useAuthStore.getState().setSession({
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    user: user!,
    is_master_session: useAuthStore.getState().isMasterSession,
  });
  return data.access_token;
}

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as (typeof error.config & { _retry?: boolean });
    if (error.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      try {
        if (!refreshPromise) {
          refreshPromise = refreshAccessToken().finally(() => {
            refreshPromise = null;
          });
        }
        const token = await refreshPromise;
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
