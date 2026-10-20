import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Paper, Stack, TextField, Typography } from "@mui/material";
import { api } from "../api/client";
import { useAuthStore } from "../store/authStore";

export function AccountSecurity() {
  const navigate = useNavigate();
  const status = useQuery({ queryKey: ["mfa-status"], queryFn: async () => (await api.get("/auth/mfa")).data.data });
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [finished, setFinished] = useState(false);
  const run = async (operation: string) => {
    setBusy(true); setError("");
    try {
      const response = await api.post(`/auth/mfa/${operation}`, { password, ...(code ? { otp_code: code } : {}) });
      if (operation === "setup") { setSecret(response.data.data.secret); setCode(""); }
      else {
        setSecret(""); setPassword(""); setCode(""); setFinished(true);
        useAuthStore.getState().clearSession();
        navigate("/login", { replace: true });
      }
    } catch (err: any) { setError(err?.response?.data?.error?.message ?? "Security update failed. Check status before retrying."); }
    finally { setBusy(false); }
  };
  return <Paper variant="outlined" sx={{ p: 3, maxWidth: 600 }}><Stack spacing={2}>
    <Typography variant="h5">Account security</Typography>
    <Typography>Use an authenticator app for a second sign-in factor. Enabling or disabling MFA signs out all your sessions.</Typography>
    {error && <Alert severity="error">{error}</Alert>}
    {status.isError && <Alert severity="error">Security status unavailable. Retry before making changes.</Alert>}
    <Typography>{status.data ? `Authenticator: ${status.data.enabled ? "Enabled" : "Disabled"}` : "Loading security status..."}</Typography>
    <TextField label="Current password" type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" />
    {secret && <Alert severity="info">Enter this setup key in your authenticator app (VisionGuard AI). Keep it private. Setup expires in 10 minutes.<Typography sx={{ overflowWrap: "anywhere" }}>{secret}</Typography></Alert>}
    {(status.data?.enabled || secret) && <TextField label="Authenticator code" value={code} onChange={e => setCode(e.target.value)} inputProps={{ inputMode: "numeric", maxLength: 6, autoComplete: "one-time-code" }} />}
    <Button variant="contained" disabled={busy || finished || !password || !status.data || status.isError || ((!!secret || status.data.enabled) && !/^[0-9]{6}$/.test(code))} onClick={() => run(status.data?.enabled ? "disable" : secret ? "enable" : "setup")}>{busy ? "Updating..." : status.data?.enabled ? "Disable authenticator" : secret ? "Confirm authenticator" : "Set up authenticator"}</Button>
    {secret && <Button disabled={busy || finished} onClick={() => run("setup")}>Restart setup</Button>}
    <Typography variant="body2">After enrollment, wait for the next code before signing in. If you lose the authenticator, contact your deployment administrator; self-service recovery is not available.</Typography>
  </Stack></Paper>;
}
