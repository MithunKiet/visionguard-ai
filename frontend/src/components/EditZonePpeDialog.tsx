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

  const { data: ppeTypes } = usePpeTypes();

  const { data: config, isLoading } = useQuery({
    queryKey: ["zone-config", zone?.id],
    queryFn: async () => (await api.get(`/config/zone/${zone!.id}`)).data.data,
    enabled: open && !!zone,
  });

  // Prefill from the zone's current config once it loads for this zone.
  useEffect(() => {
    if (config) setCodes(config.required_ppe_types ?? []);
  }, [config]);

  const saveMutation = useMutation({
    mutationFn: async () =>
      (await api.put(`/config/zone/${zone!.id}`, { required_ppe_types: codes })).data.data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["zones"] });
      queryClient.invalidateQueries({ queryKey: ["zone-config", zone?.id] });
      handleClose();
    },
    onError: (err: any) =>
      setError(err?.response?.data?.error?.message ?? err?.message ?? "Failed to update zone config"),
  });

  const handleClose = () => {
    setError(null);
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="xs" fullWidth>
      <DialogTitle>Mandatory PPE — {zone?.name}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}

          <Typography variant="caption" color="text.secondary">
            Cameras in this zone are only flagged for missing items checked here — a camera can
            still override this individually from its own edit dialog.
          </Typography>

          {isLoading ? (
            <Stack alignItems="center" sx={{ py: 2 }}>
              <CircularProgress size={24} />
            </Stack>
          ) : (
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
        <Button onClick={handleClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={() => saveMutation.mutate()}
          disabled={isLoading || saveMutation.isPending}
        >
          {saveMutation.isPending ? "Saving…" : "Save"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
