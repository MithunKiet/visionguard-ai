import { create } from "zustand";

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  role: string;
  enterprise_id: string;
  is_first_login: boolean;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: AuthUser | null;
  isMasterSession: boolean;
  setSession: (data: {
    access_token: string;
    refresh_token: string;
    user: AuthUser;
    is_master_session: boolean;
  }) => void;
  clearSession: () => void;
}

const STORAGE_KEY = "vg_auth";

function loadInitial(): Pick<AuthState, "accessToken" | "refreshToken" | "user" | "isMasterSession"> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) throw new Error("empty");
    const parsed = JSON.parse(raw);
    return {
      accessToken: parsed.accessToken ?? null,
      refreshToken: parsed.refreshToken ?? null,
      user: parsed.user ?? null,
      isMasterSession: parsed.isMasterSession ?? false,
    };
  } catch {
    return { accessToken: null, refreshToken: null, user: null, isMasterSession: false };
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  ...loadInitial(),
  setSession: ({ access_token, refresh_token, user, is_master_session }) => {
    const next = {
      accessToken: access_token,
      refreshToken: refresh_token,
      user,
      isMasterSession: is_master_session,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    set(next);
  },
  clearSession: () => {
    localStorage.removeItem(STORAGE_KEY);
    set({ accessToken: null, refreshToken: null, user: null, isMasterSession: false });
  },
}));
