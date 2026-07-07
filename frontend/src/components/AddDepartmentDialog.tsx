import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { api } from "../api/client";

interface AddDepartmentDialogProps {
  open: boolean;
  onClose: () => void;
}

const EMPTY_FORM = { factory_id: "", name: "", code: "" };

export function AddDepartmentDialog({ open, onClose }: AddDepartmentDialogProps) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  const { data: factories } = useQuery({
    queryKey: ["factories"],
    queryFn: async () => (await api.get("/factories")).data.data as any[],
    enabled: open,
  });

  const createMutation = useMutation({
    mutationFn: async () =>
      (await api.post("/departments", {
        factory_id: form.factory_id,
        name: form.name.trim(),
        code: form.code.trim(),
      })).data.data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["departments"] });
      handleClose();
    },
    onError: (err: any) =>
      setError(err?.response?.data?.error?.message ?? err?.message ?? "Failed to create department"),
  });

  const set = (field: keyof typeof EMPTY_FORM) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [field]: e.target.value }));

  const handleClose = () => {
    setForm(EMPTY_FORM);
    setError(null);
    onClose();
  };

  const canSubmit = form.factory_id && form.name.trim() && form.code.trim() && !createMutation.isPending;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Add Department</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}
          <TextField
            select
            label="Factory"
            value={form.factory_id}
            onChange={set("factory_id")}
            required
            helperText={!factories?.length ? "No factories found — create one first" : undefined}
          >
            {(factories ?? []).map((f) => (
              <MenuItem key={f.id} value={f.id}>
                {f.name} ({f.code})
              </MenuItem>
            ))}
          </TextField>
          <Stack direction="row" spacing={2}>
            <TextField label="Name" value={form.name} onChange={set("name")} required fullWidth />
            <TextField label="Code" value={form.code} onChange={set("code")} required sx={{ width: 160 }} placeholder="WLD" />
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Cancel</Button>
        <Button variant="contained" onClick={() => createMutation.mutate()} disabled={!canSubmit}>
          {createMutation.isPending ? "Creating…" : "Create Department"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
