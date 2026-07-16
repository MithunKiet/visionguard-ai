import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import AddIcon from "@mui/icons-material/Add";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../api/client";
import { usePpeTypes } from "./ppeItems";

interface ManagePpeTypesDialogProps {
  open: boolean;
  onClose: () => void;
}

export function ManagePpeTypesDialog({ open, onClose }: ManagePpeTypesDialogProps) {
  const queryClient = useQueryClient();
  const [newName, setNewName] = useState("");
  const [error, setError] = useState<string | null>(null);

  // include_inactive so admins can reactivate a previously-deactivated type
  const { data: types } = usePpeTypes(true);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["ppe-types"] });

  const createMutation = useMutation({
    mutationFn: async (name: string) => (await api.post("/ppe-types", { name })).data.data,
    onSuccess: () => {
      setNewName("");
      invalidate();
    },
    onError: (err: any) =>
      setError(err?.response?.data?.error?.message ?? err?.message ?? "Failed to add PPE type"),
  });

  const toggleMutation = useMutation({
    mutationFn: async ({ id, is_active }: { id: string; is_active: boolean }) =>
      (await api.patch(`/ppe-types/${id}`, { is_active })).data.data,
    onSuccess: invalidate,
  });

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Manage PPE Types</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}

          <Typography variant="caption" color="text.secondary">
            These are the PPE items available to check off when configuring a zone or camera.
            Deactivating one hides it from new selections but doesn't affect zones/cameras that
            already reference it.
          </Typography>

          <Stack spacing={1}>
            {(types ?? []).map((t) => (
              <Stack key={t.id} direction="row" alignItems="center" justifyContent="space-between">
                <Stack direction="row" spacing={1} alignItems="center">
                  <Typography variant="body2">{t.name}</Typography>
                  <Chip size="small" variant="outlined" label={t.code} sx={{ fontFamily: "monospace" }} />
                </Stack>
                <Switch
                  size="small"
                  checked={t.is_active}
                  disabled={toggleMutation.isPending}
                  onChange={(e) => toggleMutation.mutate({ id: t.id, is_active: e.target.checked })}
                />
              </Stack>
            ))}
            {types && types.length === 0 && (
              <Typography variant="body2" color="text.secondary">No PPE types yet.</Typography>
            )}
          </Stack>

          <Stack direction="row" spacing={1}>
            <TextField
              size="small"
              label="New PPE type"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              fullWidth
              placeholder="e.g. Ear Protection"
            />
            <Button
              variant="outlined"
              startIcon={<AddIcon />}
              disabled={!newName.trim() || createMutation.isPending}
              onClick={() => createMutation.mutate(newName.trim())}
            >
              Add
            </Button>
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
