import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api } from "../api/client";
import { DEFAULT_ZONE_PPE_CODES, usePpeTypes } from "./ppeItems";

interface ZoneToEdit {
  id: string;
  name: string;
}

interface EditZonePpeDialogProps {
  open: boolean;
  onClose: () => void;
  zone: ZoneToEdit | null;
}

export function EditZonePpeDialog({ open, onClose, zone }: EditZonePpeDialogProps) {
  const queryClient = useQueryClient();
  const [codes, setCodes] = useState<string[]>(DEFAULT_ZONE_PPE_CODES);
  const [error, setError] = useState<string | null>(null);
  const [savedVersion, setSavedVersion] = useState<number | null>(null);

  const { data: ppeTypes } = usePpeTypes();

  const { data: config, isLoading, isError, refetch } = useQuery({
    queryKey: ["zone-config", zone?.id],
    queryFn: async () => (await api.get(`/config/zone/${zone!.id}`)).data.data,
    enabled: open && !!zone,
  });

  const delivery = useQuery({
    queryKey: ["zone-config-delivery", zone?.id],
    queryFn: async () => (await api.get(`/config/zone/${zone!.id}/delivery`)).data.data,
    enabled: open && !!zone,
    refetchInterval: open ? 5000 : false,
  });
  useEffect(() => { setSavedVersion(null); setError(null); }, [open, zone?.id]);

  // Prefill from the zone's current config once it loads for this zone.
  useEffect(() => {
    if (config) setCodes(config.required_ppe_types ?? []);
  }, [config]);

  const saveMutation = useMutation({
    mutationFn: async () =>
      (await api.put(`/config/zone/${zone!.id}`, { required_ppe_types: codes })).data.data,
    onSuccess: (saved) => {
      setError(null);
      setSavedVersion(saved.version);
      queryClient.setQueryData(["zone-config", zone?.id], saved);
      queryClient.invalidateQueries({ queryKey: ["zones"] });
      queryClient.invalidateQueries({ queryKey: ["zone-config-delivery", zone?.id] });
    },
    onError: (err: any) =>
      setError(err?.response?.data?.error?.message ?? err?.message ?? "Failed to update zone config"),
  });

  const handleClose = () => {
    if (saveMutation.isPending) return;
    setError(null);
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="xs" fullWidth>
      <DialogTitle>Mandatory PPE — {zone?.name}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}
          {isError && <Alert severity="error" action={<Button onClick={() => refetch()}>Retry</Button>}>
            Settings could not be loaded. Retry before saving.
          </Alert>}
          {savedVersion !== null && <Alert severity="info">
            Version {savedVersion} saved. Worker application is tracked below.
          </Alert>}
          {delivery.isError ? <Alert severity="warning" action={<Button onClick={() => delivery.refetch()}>Refresh status</Button>}>
            Application status is unavailable. Saved settings may still be pending.
          </Alert> : delivery.data && delivery.data.version >= (savedVersion ?? 0) ? (
            <Alert severity={delivery.data.status === "Applied" ? "success" : "info"}>
              {delivery.data.status === "Applied"
                ? `Version ${delivery.data.version} applied on ${delivery.data.applied_cameras} of ${delivery.data.active_cameras} active cameras.`
                : delivery.data.status === "NoActiveCameras"
                  ? `Version ${delivery.data.version}: no active cameras to confirm application.`
                  : `Version ${delivery.data.version}: ${delivery.data.applied_cameras} of ${delivery.data.active_cameras} active cameras confirmed; ${delivery.data.pending_cameras} pending.`}
              {delivery.data.status !== "Applied" && delivery.data.publication.status === "Retrying" &&
                " Delivery is retrying automatically."}
              {delivery.data.status !== "Applied" && delivery.data.publication.status === "Published" &&
                " Update published; waiting for worker confirmation."}
              {delivery.data.unassigned_cameras > 0 && ` ${delivery.data.unassigned_cameras} cameras need a worker assignment.`}
              {delivery.data.last_applied_at && ` Last application confirmed: ${new Date(delivery.data.last_applied_at).toLocaleString()}.`}
            </Alert>
          ) : <Typography variant="body2">Checking worker application…</Typography>}

          <Typography variant="caption" color="text.secondary">
            Cameras in this zone are only flagged for missing items checked here — a camera can
            still override this individually from its own edit dialog.
            {" "}Applied confirms installation of this zone policy; check camera health separately.
          </Typography>

          {isLoading ? (
            <Stack alignItems="center" sx={{ py: 2 }}>
              <CircularProgress size={24} />
            </Stack>
          ) : isError ? null : (
            <Stack direction="row" flexWrap="wrap">
              {(ppeTypes ?? []).map((t) => (
                <FormControlLabel
                  key={t.code}
                  control={
                    <Checkbox
                      size="small"
                      checked={codes.includes(t.code)}
                      onChange={(e) =>
                        setCodes((c) =>
                          e.target.checked ? [...c, t.code] : c.filter((x) => x !== t.code)
                        )
                      }
                    />
                  }
                  label={t.name}
                />
              ))}
            </Stack>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={saveMutation.isPending}>Close</Button>
        <Button
          variant="contained"
          onClick={() => saveMutation.mutate()}
          disabled={isLoading || isError || !config || saveMutation.isPending}
        >
          {saveMutation.isPending ? "Saving…" : "Save"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
