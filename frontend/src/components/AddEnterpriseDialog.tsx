import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../api/client";

interface AddEnterpriseDialogProps {
  open: boolean;
  onClose: () => void;
}

const EMPTY_FORM = {
  name: "",
  code: "",
  industry: "",
  admin_name: "",
  admin_email: "",
};

interface CreatedResult {
  name: string;
  admin_email: string;
  temp_password: string;
  welcome_email_sent: boolean;
}

export function AddEnterpriseDialog({ open, onClose }: AddEnterpriseDialogProps) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CreatedResult | null>(null);

  const createMutation = useMutation({
    mutationFn: async () =>
      (await api.post("/enterprises", {
        name: form.name.trim(),
        code: form.code.trim().toUpperCase(),
        industry: form.industry.trim() || null,
        admin_name: form.admin_name.trim(),
        admin_email: form.admin_email.trim(),
      })).data.data,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["enterprises"] });
      setResult(data);
    },
    onError: (err: any) =>
      setError(err?.response?.data?.error?.message ?? err?.message ?? "Failed to create enterprise"),
  });

  const set = (field: keyof typeof EMPTY_FORM) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [field]: e.target.value }));

  const handleClose = () => {
    setForm(EMPTY_FORM);
    setError(null);
    setResult(null);
    onClose();
  };

  const canSubmit =
    form.name.trim() && form.code.trim() && form.admin_name.trim() && form.admin_email.trim() &&
    !createMutation.isPending;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>{result ? "Enterprise Created" : "Onboard New Enterprise"}</DialogTitle>
      <DialogContent>
        {result ? (
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="success">
              <b>{result.name}</b> is ready, with {result.admin_email} as its first HO Admin.
            </Alert>

            {!result.welcome_email_sent && (
              <Alert severity="warning">
                No email server is configured in this environment, so the welcome email was not
                sent — share these credentials with the admin yourself.
              </Alert>
            )}

            <Divider />

            <Stack spacing={0.5}>
              <Typography variant="caption" color="text.secondary">Admin email</Typography>
              <Typography variant="body1" sx={{ fontFamily: "monospace" }}>{result.admin_email}</Typography>
            </Stack>
            <Stack spacing={0.5}>
              <Typography variant="caption" color="text.secondary">
                Temporary password — shown only once, copy it now
              </Typography>
              <Typography variant="body1" sx={{ fontFamily: "monospace", fontWeight: 700 }}>
                {result.temp_password}
              </Typography>
            </Stack>

            <Typography variant="caption" color="text.secondary">
              They'll be forced to set a new password on first login, then walked through the
              setup wizard (factory → department → zone → camera).
            </Typography>
          </Stack>
        ) : (
          <Stack spacing={2} sx={{ mt: 1 }}>
            {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}

            <Typography variant="body2" fontWeight={600}>Enterprise</Typography>
            <Stack direction="row" spacing={2}>
              <TextField label="Name" value={form.name} onChange={set("name")} required fullWidth placeholder="Acme Manufacturing" />
              <TextField label="Code" value={form.code} onChange={set("code")} required sx={{ width: 140 }} placeholder="ACME" />
            </Stack>
            <TextField label="Industry (optional)" value={form.industry} onChange={set("industry")} fullWidth placeholder="Automotive" />

            <Divider />

            <Typography variant="body2" fontWeight={600}>First HO Admin</Typography>
            <Stack direction="row" spacing={2}>
              <TextField label="Admin name" value={form.admin_name} onChange={set("admin_name")} required fullWidth />
              <TextField label="Admin email" value={form.admin_email} onChange={set("admin_email")} required fullWidth type="email" />
            </Stack>

            <Alert severity="info">
              A secure temporary password is generated automatically — the admin sets their own
              on first login.
            </Alert>
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        {result ? (
          <Button variant="contained" onClick={handleClose}>Done</Button>
        ) : (
          <>
            <Button onClick={handleClose}>Cancel</Button>
            <Button variant="contained" onClick={() => createMutation.mutate()} disabled={!canSubmit}>
              {createMutation.isPending ? "Creating…" : "Create Enterprise"}
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
}
