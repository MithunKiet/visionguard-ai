import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { api } from "../api/client";

interface AddFactoryDialogProps {
  open: boolean;
  onClose: () => void;
}

const EMPTY_FORM = { name: "", code: "", location: "" };

export function AddFactoryDialog({ open, onClose }: AddFactoryDialogProps) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: async () =>
      (await api.post("/factories", {
        name: form.name.trim(),
        code: form.code.trim(),
        location: form.location.trim() || null,
      })).data.data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["factories"] });
      handleClose();
    },
    onError: (err: any) =>
      setError(err?.response?.data?.error?.message ?? err?.message ?? "Failed to create factory"),
  });

  const set = (field: keyof typeof EMPTY_FORM) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [field]: e.target.value }));

  const handleClose = () => {
    setForm(EMPTY_FORM);
    setError(null);
    onClose();
  };

  const canSubmit = form.name.trim() && form.code.trim() && !createMutation.isPending;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Add Factory</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}
          <Stack direction="row" spacing={2}>
            <TextField label="Name" value={form.name} onChange={set("name")} required fullWidth />
            <TextField label="Code" value={form.code} onChange={set("code")} required sx={{ width: 160 }} placeholder="WMF" />
          </Stack>
          <TextField label="Location (optional)" value={form.location} onChange={set("location")} fullWidth placeholder="Chennai" />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Cancel</Button>
        <Button variant="contained" onClick={() => createMutation.mutate()} disabled={!canSubmit}>
          {createMutation.isPending ? "Creating…" : "Create Factory"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
