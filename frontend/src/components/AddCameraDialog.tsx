import { useEffect, useState } from "react";
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
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { api } from "../api/client";
import { usePpeTypes } from "./ppeItems";
import { SearchableSelect } from "./SearchableSelect";

interface ZoneOption {
  id: string;
  name: string;
  code: string;
  factory_id: string;
  factory_name: string;
  department_name: string;
}

type PpeOverrides = Record<string, boolean | null>;

interface CameraToEdit {
  id: string;
  zone_id: string;
  name: string;
  code: string;
  rtsp_url: string;
  camera_type: string;
  position_desc: string | null;
  ppe_overrides: Record<string, boolean>;
}

interface AddCameraDialogProps {
  open: boolean;
  onClose: () => void;
  /** When set, the dialog edits this camera (PUT) instead of creating one (POST). */
  camera?: CameraToEdit | null;
}

const CAMERA_TYPES = ["Fixed", "PTZ", "Fisheye"];

type StringField = "zone_id" | "name" | "code" | "rtsp_url" | "camera_type" | "position_desc";

const EMPTY_FORM = {
  zone_id: "",
  name: "",
  code: "",
  rtsp_url: "",
  camera_type: "Fixed",
  position_desc: "",
  ppeOverrides: {} as PpeOverrides,
};

function formFromCamera(camera: CameraToEdit) {
  return {
    zone_id: camera.zone_id,
    name: camera.name,
    code: camera.code,
    rtsp_url: camera.rtsp_url,
    camera_type: camera.camera_type,
    position_desc: camera.position_desc ?? "",
    ppeOverrides: { ...camera.ppe_overrides } as PpeOverrides,
  };
}

export function AddCameraDialog({ open, onClose, camera }: AddCameraDialogProps) {
  const isEdit = !!camera;
  const queryClient = useQueryClient();
  const [form, setForm] = useState(camera ? formFromCamera(camera) : EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ reachable: boolean; latency_ms: number } | null>(null);

  const { data: ppeTypes } = usePpeTypes();

  // Dialog is kept mounted between opens (parent toggles `open`), so reset
  // the form to match whichever camera (or blank) it was opened for.
  useEffect(() => {
    if (open) setForm(camera ? formFromCamera(camera) : EMPTY_FORM);
  }, [open, camera]);

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

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (isEdit) {
        // Full merge-patch: every code the user could see gets an explicit
        // value (true/false to override, null to clear back to inherit) —
        // the backend merges this into the camera's existing overrides.
        const payload = {
          name: form.name.trim(),
          rtsp_url: form.rtsp_url.trim(),
          camera_type: form.camera_type,
          position_desc: form.position_desc.trim() || null,
          ppe_overrides: form.ppeOverrides,
        };
        return (await api.put(`/cameras/${camera!.id}`, payload)).data.data;
      }
      if (!zones?.some((z) => z.id === form.zone_id)) throw new Error("Select a zone");
      const payload = {
        // factory_id is derived server-side from zone_id — not sent.
        zone_id: form.zone_id,
        name: form.name.trim(),
        code: form.code.trim(),
        rtsp_url: form.rtsp_url.trim(),
        camera_type: form.camera_type,
        position_desc: form.position_desc.trim() || null,
        // Creation has nothing to clear — only send actual true/false overrides.
        ppe_overrides: Object.fromEntries(
          Object.entries(form.ppeOverrides).filter(([, v]) => v !== null)
        ),
      };
      return (await api.post("/cameras", payload)).data.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      handleClose();
    },
    onError: (err: any) =>
      setError(err?.response?.data?.error?.message ?? err?.message ?? `Failed to ${isEdit ? "update" : "create"} camera`),
  });

  const set = (field: StringField) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setForm((f) => ({ ...f, [field]: e.target.value }));
      if (field === "rtsp_url") setTestResult(null);
    };

  const setField = (field: StringField) => (value: string) =>
    setForm((f) => ({ ...f, [field]: value }));

  const setPpe = (code: string) => (_: unknown, value: "inherit" | "yes" | "no" | null) => {
    if (value === null) return; // re-clicking the already-selected option
    setForm((f) => ({
      ...f,
      ppeOverrides: { ...f.ppeOverrides, [code]: value === "inherit" ? null : value === "yes" },
    }));
  };

  const handleClose = () => {
    setError(null);
    setTestResult(null);
    onClose();
  };

  const canSubmit =
    form.zone_id && form.name.trim() && form.code.trim() && form.rtsp_url.trim() &&
    !saveMutation.isPending;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>{isEdit ? "Edit Camera" : "Add Camera"}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}

          <SearchableSelect
            label="Zone"
            value={form.zone_id}
            onChange={setField("zone_id")}
            required
            disabled={isEdit}
            options={(zones ?? []).map((z) => ({
              id: z.id,
              label: `${z.factory_name} / ${z.department_name} / ${z.name} (${z.code})`,
            }))}
            helperText={
              isEdit
                ? "Zone can't be changed after creation"
                : !zones?.length ? "No zones found — create one via the Setup Wizard first" : undefined
            }
          />

          <Stack direction="row" spacing={2}>
            <TextField label="Name" value={form.name} onChange={set("name")} required fullWidth />
            <TextField
              label="Code"
              value={form.code}
              onChange={set("code")}
              required
              disabled={isEdit}
              sx={{ width: 180 }}
              placeholder="CAM-002"
            />
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

          <div>
            <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
              Mandatory PPE override
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
              "Inherit" uses this camera's zone setting. Override only the items that need to
              differ for this specific camera.
            </Typography>
            <Stack spacing={1}>
              {(ppeTypes ?? []).map((t) => {
                const current = form.ppeOverrides[t.code];
                return (
                  <Stack key={t.code} direction="row" spacing={2} alignItems="center">
                    <Typography variant="body2" sx={{ width: 90 }}>{t.name}</Typography>
                    <ToggleButtonGroup
                      size="small"
                      exclusive
                      value={current === undefined || current === null ? "inherit" : current ? "yes" : "no"}
                      onChange={setPpe(t.code)}
                    >
                      <ToggleButton value="inherit">Inherit</ToggleButton>
                      <ToggleButton value="yes">Required</ToggleButton>
                      <ToggleButton value="no">Not required</ToggleButton>
                    </ToggleButtonGroup>
                  </Stack>
                );
              })}
            </Stack>
          </div>

          {!isEdit && (
            <Alert severity="info">
              The camera is auto-assigned to the least-loaded AI worker. Restart the AI
              worker (<code>docker compose restart ai-worker</code>) for it to start processing.
            </Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Cancel</Button>
        <Button variant="contained" onClick={() => saveMutation.mutate()} disabled={!canSubmit}>
          {saveMutation.isPending ? "Saving…" : isEdit ? "Save Changes" : "Create Camera"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
