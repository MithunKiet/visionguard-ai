import { useState } from "react";
import { Alert, Button, Checkbox, Chip, FormControlLabel, Paper, Stack, Table, TableBody, TableCell, TableHead, TablePagination, TableRow, Typography } from "@mui/material";
import { useDetectionHealth } from "../hooks/useDetectionHealth";
import { DetectionHealthNotice } from "../components/DetectionHealthNotice";

const LABELS: Record<string, string> = {
  Detecting: "Recent detection", Paused: "Paused", Maintenance: "Maintenance", Unassigned: "No worker assigned",
  WorkerUnavailable: "Worker unavailable", LeaseExpired: "Ownership expired", ConfigPending: "Settings unconfirmed",
  TelemetryMissing: "Health report missing or stale", StreamOffline: "Stream offline", InferenceStale: "No recent inference",
};

export function DetectionHealth() {
  const [page, setPage] = useState(0);
  const [problemsOnly, setProblemsOnly] = useState(false);
  const health = useDetectionHealth(page, problemsOnly);
  const current = health.current;
  return <Stack spacing={3}>
    <Typography variant="h5" fontWeight={700}>Detection health</Typography>
    <DetectionHealthNotice data={current?.data} />
    <Typography variant="body2">Camera activation and a live dashboard connection do not confirm AI detection. Recent inference is checked against worker availability, current ownership and settings.</Typography>
    {!current && <Alert severity="warning" action={<Button onClick={() => health.refetch()}>Refresh health</Button>}>
      {health.isLoading ? "Checking detection health…" : "A fresh health snapshot is required. Previous camera readings are hidden."}
    </Alert>}
    {current && <Typography variant="caption">Checked: {new Date(current.data.checked_at).toLocaleString()}. Historical monitoring coverage is not measured; a safety score is unavailable.</Typography>}
    <FormControlLabel label="Show detection gaps only" control={<Checkbox checked={problemsOnly} onChange={e => { setProblemsOnly(e.target.checked); setPage(0); }} />} />
    <Paper variant="outlined" sx={{ overflowX: "auto" }}>
      <Table size="small"><TableHead><TableRow>
        <TableCell>Camera</TableCell><TableCell>Factory / zone</TableCell><TableCell>Detection status</TableCell><TableCell>Last reported inference (estimate)</TableCell>
      </TableRow></TableHead><TableBody>
        {current?.data.cameras.map(camera => <TableRow key={camera.camera_id}>
          <TableCell>{camera.camera_name}</TableCell><TableCell>{camera.factory_name} / {camera.zone_name}</TableCell>
          <TableCell><Chip size="small" label={LABELS[camera.state] ?? camera.state} color={camera.state === "Detecting" || ["Paused", "Maintenance"].includes(camera.state) ? "default" : "warning"} /></TableCell>
          <TableCell>{camera.last_inference_at ? new Date(camera.last_inference_at).toLocaleString() : "Not confirmed"}</TableCell>
        </TableRow>)}
        {current?.data.cameras.length === 0 && <TableRow><TableCell colSpan={4}>No cameras match this page and filter.</TableCell></TableRow>}
      </TableBody></Table>
      <TablePagination component="div" count={current?.total ?? 0} page={page} rowsPerPage={20} rowsPerPageOptions={[20]} onPageChange={(_, next) => setPage(next)} />
    </Paper>
  </Stack>;
}
