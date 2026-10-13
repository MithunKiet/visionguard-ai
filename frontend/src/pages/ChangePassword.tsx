import { useState } from "react";
import { Alert, Box, Button, TextField, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuthStore } from "../store/authStore";

export function ChangePassword() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const navigate = useNavigate();
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      await api.post("/auth/change-password", { current_password: currentPassword, new_password: newPassword });
      useAuthStore.getState().clearSession();
      navigate("/login", { replace: true });
    } catch (err: any) {
      setError(err.response?.data?.error?.message || "Unable to change password. Check your current password and try again.");
    } finally {
      setPending(false);
    }
  };
  return <Box component="form" onSubmit={submit} sx={{ maxWidth: 420, mx: "auto", mt: 10, display: "grid", gap: 2 }}>
    <Typography variant="h5">Change your password</Typography>
    <Typography>Replace your temporary password before continuing. Sign in again after saving.</Typography>
    {error && <Alert severity="error">{error}</Alert>}
    <TextField required label="Current password" type="password" autoComplete="current-password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} />
    <TextField required label="New password" type="password" autoComplete="new-password" inputProps={{ minLength: 8 }} value={newPassword} onChange={e => setNewPassword(e.target.value)} />
    <Button type="submit" variant="contained" disabled={pending}>Save password</Button>
  </Box>;
}
