import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Dropdown } from "semantic-ui-react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../api/client";
import { SearchableSelect } from "./SearchableSelect";
import { DEFAULT_ZONE_PPE_CODES, usePpeTypes } from "./ppeItems";

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
  required_ppe_types: DEFAULT_ZONE_PPE_CODES as string[],
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

  const { data: ppeTypes } = usePpeTypes();

  const createMutation = useMutation({
    mutationFn: async () =>
      (await api.post("/zones", {
        // factory_id is derived server-side from department_id — not sent.
        department_id: form.department_id,
        name: form.name.trim(),
        code: form.code.trim(),
        max_occupancy: Number(form.max_occupancy),
        zone_type: form.zone_type,
        is_restricted: form.is_restricted,
        required_ppe_types: form.required_ppe_types,
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

  const setField = (field: keyof typeof EMPTY_FORM) => (value: string) =>
    setForm((f) => ({
      ...f,
      [field]: value,
      ...(field === "factory_id" ? { department_id: "" } : {}),
    }));

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

          <SearchableSelect
            label="Factory"
            value={form.factory_id}
            onChange={setField("factory_id")}
            required
            options={(factories ?? []).map((f) => ({ id: f.id, label: `${f.name} (${f.code})` }))}
            helperText={!factories?.length ? "No factories found — create one first" : undefined}
          />

          <SearchableSelect
            label="Department"
            value={form.department_id}
            onChange={setField("department_id")}
            required
            disabled={!form.factory_id}
            options={(departments ?? []).map((d) => ({ id: d.id, label: `${d.name} (${d.code})` }))}
            helperText={form.factory_id && !departments?.length ? "No departments in this factory — create one first" : undefined}
          />

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
            <div style={{ flex: 1 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6, color: "#374151" }}>
                Zone type
              </label>
              <Dropdown
                fluid
                selection
                options={ZONE_TYPES.map((t) => ({ key: t, text: t, value: t }))}
                value={form.zone_type}
                onChange={(_, data) => setField("zone_type")((data.value as string) ?? "Production")}
              />
            </div>
          </Stack>

          <div>
            <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
              Mandatory PPE
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
              Cameras in this zone will only be flagged for missing items checked here — a camera
              can still override this individually later.
            </Typography>
            <Stack direction="row" flexWrap="wrap">
              {(ppeTypes ?? []).map((t) => (
                <FormControlLabel
                  key={t.code}
                  control={
                    <Checkbox
                      size="small"
                      checked={form.required_ppe_types.includes(t.code)}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          required_ppe_types: e.target.checked
                            ? [...f.required_ppe_types, t.code]
                            : f.required_ppe_types.filter((c) => c !== t.code),
                        }))
                      }
                    />
                  }
                  label={t.name}
                />
              ))}
              {ppeTypes && ppeTypes.length === 0 && (
                <Typography variant="body2" color="text.secondary">
                  No PPE types defined yet — add one from the Zones page.
                </Typography>
              )}
            </Stack>
          </div>

          <Alert severity="info">
            Detection thresholds (confidence, cooldown, etc.) can be adjusted later from Config.
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
