import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import { refreshAccessToken } from "../api/client";
import { useAuthStore } from "../store/authStore";

/**
 * The access token now lives in memory only (see store/authStore.ts) — a
 * fresh page load always starts with `accessToken: null`. If a previous
 * session was persisted, silently mint a new access token from the httpOnly
 * refresh cookie before rendering any routes, so a reload doesn't bounce a
 * still-logged-in user to /login.
 */
export function AuthBootstrap({ children }: { children: React.ReactNode }) {
  const hasPersistedSession = useAuthStore((s) => s.hasPersistedSession);
  const clearSession = useAuthStore((s) => s.clearSession);
  const [ready, setReady] = useState(!hasPersistedSession);

  useEffect(() => {
    if (!hasPersistedSession) return;
    refreshAccessToken()
      .catch(() => clearSession())
      .finally(() => setReady(true));
    // Runs once on mount only — re-running on store changes would refresh in a loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!ready) {
    return (
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  return <>{children}</>;
}
