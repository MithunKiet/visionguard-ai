import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Dropdown } from "semantic-ui-react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { api } from "../api/client";
import { SearchableSelect } from "./SearchableSelect";

interface ZoneOption {
  id: string;
  name: string;
  code: string;
  factory_id: string;
  factory_name: string;
  department_name: string;
}

interface AddCameraDialogProps {
  open: boolean;
  onClose: () => void;
}

const CAMERA_TYPES = ["Fixed", "PTZ", "Fisheye"];

const EMPTY_FORM = {
  zone_id: "",
  name: "",
  code: "",
  rtsp_url: "",
  camera_type: "Fixed",
  position_desc: "",
};

export function AddCameraDialog({ open, onClose }: AddCameraDialogProps) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ reachable: boolean; latency_ms: number } | null>(null);

  const { data: zones } = useQuery({
    queryKey: ["zones"],
    queryFn: async () => (await api.get("/zones")).data.data as ZoneOption[],
    enabled: open,
  });

  const testMutation = useMutation({
    mutationFn: async (rtsp_url: string) =>
      (await api.post("/cameras/test-connection", { rtsp_url })).data.data,
    onSuccess: (data) => setTestResult(data),
    onError: () => setTestResult({ reachable: false, latency_ms: 0 }),
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      const zone = zones?.find((z) => z.id === form.zone_id);
      if (!zone) throw new Error("Select a zone");
      const payload = {
        factory_id: zone.factory_id,
        zone_id: form.zone_id,
        name: form.name.trim(),
        code: form.code.trim(),
        rtsp_url: form.rtsp_url.trim(),
        camera_type: form.camera_type,
        position_desc: form.position_desc.trim() || null,
      };
      return (await api.post("/cameras", payload)).data.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      handleClose();
    },
    onError: (err: any) =>
      setError(err?.response?.data?.error?.message ?? err?.message ?? "Failed to create camera"),
  });

  const set = (field: keyof typeof EMPTY_FORM) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setForm((f) => ({ ...f, [field]: e.target.value }));
      if (field === "rtsp_url") setTestResult(null);
    };

  const setField = (field: keyof typeof EMPTY_FORM) => (value: string) =>
    setForm((f) => ({ ...f, [field]: value }));

  const handleClose = () => {
    setForm(EMPTY_FORM);
    setError(null);
    setTestResult(null);
    onClose();
  };

  const canSubmit =
    form.zone_id && form.name.trim() && form.code.trim() && form.rtsp_url.trim() &&
    !createMutation.isPending;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Add Camera</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}

          <SearchableSelect
            label="Zone"
            value={form.zone_id}
            onChange={setField("zone_id")}
            required
            options={(zones ?? []).map((z) => ({
              id: z.id,
              label: `${z.factory_name} / ${z.department_name} / ${z.name} (${z.code})`,
            }))}
            helperText={!zones?.length ? "No zones found — create one via the Setup Wizard first" : undefined}
          />

          <Stack direction="row" spacing={2}>
            <TextField label="Name" value={form.name} onChange={set("name")} required fullWidth />
            <TextField label="Code" value={form.code} onChange={set("code")} required sx={{ width: 180 }} placeholder="CAM-002" />
          </Stack>

          <Stack direction="row" spacing={1} alignItems="flex-start">
            <TextField
              label="RTSP URL"
              value={form.rtsp_url}
              onChange={set("rtsp_url")}
              required
              fullWidth
              placeholder="rtsp://192.168.1.50:554/stream1"
              InputProps={{ sx: { fontFamily: "monospace", fontSize: 13 } }}
            />
            <Button
              variant="outlined"
              onClick={() => testMutation.mutate(form.rtsp_url.trim())}
              disabled={!form.rtsp_url.trim() || testMutation.isPending}
              sx={{ whiteSpace: "nowrap", mt: 1 }}
            >
              {testMutation.isPending ? "Testing…" : "Test"}
            </Button>
          </Stack>

          {testResult && (
            <Alert severity={testResult.reachable ? "success" : "warning"}>
              {testResult.reachable
                ? `Stream reachable (${testResult.latency_ms} ms)`
                : "Stream not reachable — you can still save and fix connectivity later"}
            </Alert>
          )}

          <Stack direction="row" spacing={2}>
            <div style={{ width: 180 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6, color: "#374151" }}>
                Camera type
              </label>
              <Dropdown
                fluid
                selection
                options={CAMERA_TYPES.map((t) => ({ key: t, text: t, value: t }))}
                value={form.camera_type}
                onChange={(_, data) => setField("camera_type")((data.value as string) ?? "Fixed")}
              />
            </div>
            <TextField
              label="Position (optional)"
              value={form.position_desc}
              onChange={set("position_desc")}
              fullWidth
              placeholder="North wall, 4m height, 40° tilt"
            />
          </Stack>

          <Alert severity="info">
            The camera is auto-assigned to the least-loaded AI worker. Restart the AI
            worker (<code>docker compose restart ai-worker</code>) for it to start processing.
          </Alert>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Cancel</Button>
        <Button variant="contained" onClick={() => createMutation.mutate()} disabled={!canSubmit}>
          {createMutation.isPending ? "Creating…" : "Create Camera"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
