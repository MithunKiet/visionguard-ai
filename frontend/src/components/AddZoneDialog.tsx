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

interface AddZoneDialogProps {
  open: boolean;
  onClose: () => void;
}

const ZONE_TYPES = ["Production", "Storage", "Restricted", "Entry-Exit"];

const EMPTY_FORM = {
  factory_id: "",
  department_id: "",
  name: "",
  code: "",
  max_occupancy: "10",
  zone_type: "Production",
  is_restricted: false,
};

export function AddZoneDialog({ open, onClose }: AddZoneDialogProps) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  const { data: factories } = useQuery({
    queryKey: ["factories"],
    queryFn: async () => (await api.get("/factories")).data.data as any[],
    enabled: open,
  });

  const { data: departments } = useQuery({
    queryKey: ["departments", form.factory_id],
    queryFn: async () => (await api.get("/departments", { params: { factory_id: form.factory_id } })).data.data as any[],
    enabled: open && !!form.factory_id,
  });

  const createMutation = useMutation({
    mutationFn: async () =>
      (await api.post("/zones", {
        factory_id: form.factory_id,
        department_id: form.department_id,
        name: form.name.trim(),
        code: form.code.trim(),
        max_occupancy: Number(form.max_occupancy),
        zone_type: form.zone_type,
        is_restricted: form.is_restricted,
      })).data.data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["zones"] });
      handleClose();
    },
    onError: (err: any) =>
      setError(err?.response?.data?.error?.message ?? err?.message ?? "Failed to create zone"),
  });

  const set = (field: keyof typeof EMPTY_FORM) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setForm((f) => ({
      ...f,
      [field]: value,
      // Changing factory invalidates whatever department was picked for the old one
      ...(field === "factory_id" ? { department_id: "" } : {}),
    }));
  };

  const handleClose = () => {
    setForm(EMPTY_FORM);
    setError(null);
    onClose();
  };

  const canSubmit =
    form.factory_id && form.department_id && form.name.trim() && form.code.trim() &&
    Number(form.max_occupancy) > 0 && !createMutation.isPending;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Add Zone</DialogTitle>
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

          <TextField
            select
            label="Department"
            value={form.department_id}
            onChange={set("department_id")}
            required
            disabled={!form.factory_id}
            helperText={form.factory_id && !departments?.length ? "No departments in this factory — create one first" : undefined}
          >
            {(departments ?? []).map((d) => (
              <MenuItem key={d.id} value={d.id}>
                {d.name} ({d.code})
              </MenuItem>
            ))}
          </TextField>

          <Stack direction="row" spacing={2}>
            <TextField label="Name" value={form.name} onChange={set("name")} required fullWidth />
            <TextField label="Code" value={form.code} onChange={set("code")} required sx={{ width: 140 }} placeholder="ZA" />
          </Stack>

          <Stack direction="row" spacing={2}>
            <TextField
              label="Max Occupancy"
              type="number"
              value={form.max_occupancy}
              onChange={set("max_occupancy")}
              required
              sx={{ width: 160 }}
              slotProps={{ htmlInput: { min: 1 } }}
            />
            <TextField select label="Zone type" value={form.zone_type} onChange={set("zone_type")} fullWidth>
              {ZONE_TYPES.map((t) => (
                <MenuItem key={t} value={t}>{t}</MenuItem>
              ))}
            </TextField>
          </Stack>

          <Alert severity="info">
            A default PPE config (helmet + vest required) is created automatically for this zone —
            adjust thresholds later from Config.
          </Alert>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Cancel</Button>
        <Button variant="contained" onClick={() => createMutation.mutate()} disabled={!canSubmit}>
          {createMutation.isPending ? "Creating…" : "Create Zone"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
