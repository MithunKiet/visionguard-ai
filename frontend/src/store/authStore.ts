import { create } from "zustand";

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  // A user can hold more than one role at once (e.g. FACTORY_MANAGER + SAFETY_OFFICER).
  roles: string[];
  enterprise_id: string;
  is_first_login: boolean;
}

interface AuthState {
  // Never persisted to localStorage/sessionStorage — held in memory only, so
  // an XSS bug reading browser storage can't exfiltrate it. Re-minted on
  // every fresh page load via the httpOnly refresh cookie (see
  // components/AuthBootstrap.tsx + api/client.ts refreshAccessToken).
  accessToken: string | null;
  user: AuthUser | null;
  isMasterSession: boolean;
  // True if a prior login was persisted (i.e. `user` came from localStorage
  // on boot) — tells AuthBootstrap whether it's worth attempting a silent
  // refresh before deciding the user is logged out.
  hasPersistedSession: boolean;
  // Note: the refresh token is intentionally never stored here either. The
  // backend sets it as an httpOnly cookie (see api/client.ts
  // refreshAccessToken) — keeping it out of JS-readable storage means an XSS
  // bug can't exfiltrate the long-lived (7-day) credential.
  setSession: (data: {
    access_token: string;
    user: AuthUser;
    is_master_session: boolean;
  }) => void;
  clearSession: () => void;
}

const STORAGE_KEY = "vg_auth";

function loadInitial(): Pick<AuthState, "user" | "isMasterSession" | "hasPersistedSession"> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) throw new Error("empty");
    const parsed = JSON.parse(raw);
    return {
      user: parsed.user ?? null,
      isMasterSession: parsed.isMasterSession ?? false,
      hasPersistedSession: !!parsed.user,
    };
  } catch {
    return { user: null, isMasterSession: false, hasPersistedSession: false };
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  ...loadInitial(),
  setSession: ({ access_token, user, is_master_session }) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ user, isMasterSession: is_master_session }));
    set({ accessToken: access_token, user, isMasterSession: is_master_session, hasPersistedSession: true });
  },
  clearSession: () => {
    localStorage.removeItem(STORAGE_KEY);
    set({ accessToken: null, user: null, isMasterSession: false, hasPersistedSession: false });
  },
}));
