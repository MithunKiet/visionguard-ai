import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import AddIcon from "@mui/icons-material/Add";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import { Alert, TablePagination } from "@mui/material";
import { Link } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { CameraImportDialog } from "../components/CameraImportDialog";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { api } from "../api/client";
import { AddCameraDialog } from "../components/AddCameraDialog";
import { formatEnforcedPpe, usePpeTypes } from "../components/ppeItems";

async function fetchCameras() {
  const resp = await api.get("/cameras");
  return resp.data.data as any[];
}

async function testConnection(camera_id: string) {
  const resp = await api.get(`/cameras/${camera_id}/health`);
  return resp.data.data;
}

const STATUS_COLOR: Record<string, "success" | "error" | "warning" | "default"> = {
  Active: "success",
  Offline: "error",
  Degraded: "warning",
  Maintenance: "default",
};

export function Cameras() {
  const queryClient = useQueryClient();
  const canManage = useAuthStore(s => s.user?.roles.some(role => ["SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER"].includes(role)));
  const [importOpen, setImportOpen] = useState(false);
  const [page, setPage] = useState(0);
  const [checks, setChecks] = useState<Record<string, string>>({});
  const [actionError, setActionError] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [editCamera, setEditCamera] = useState<any | null>(null);
  const { data: cameras, isLoading, isError, refetch } = useQuery({
    queryKey: ["cameras"],
    queryFn: fetchCameras,
    refetchInterval: 15000,
  });
  const visiblePage = Math.min(page, Math.max(0, Math.ceil((isError ? 0 : cameras?.length ?? 0) / 50) - 1));
  const { data: ppeTypes } = usePpeTypes();

  const testMutation = useMutation({
    mutationFn: testConnection,
    onSuccess: (result, id) => setChecks(old => ({ ...old, [id]: `${result.rtsp_reachable ? "Frame received" : "No frame received"} — checked ${new Date().toLocaleTimeString()}` })),
    onError: (_err, id) => setChecks(old => ({ ...old, [id]: "Connection check could not complete; retry." })),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["cameras"] }),
  });

  const activate = useMutation({
    mutationFn: async (id: string) => api.patch(`/cameras/${id}/status`, { status: "Active" }),
    onMutate: () => setActionError(""),
    onError: () => setActionError("Activation could not be confirmed. Refresh the camera status before retrying."),
    onSettled: () => { void queryClient.invalidateQueries({ queryKey: ["cameras"] }); void queryClient.invalidateQueries({ queryKey: ["detection-health"] }); },
  });

  return (
    <Stack spacing={3}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h5" fontWeight={700}>
          Cameras
        </Typography>
        {canManage && <Stack direction="row" spacing={1}>
          <Button variant="outlined" onClick={() => setImportOpen(true)}>Import CSV</Button>
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setAddOpen(true)}>Add Camera</Button>
        </Stack>}
      </Stack>

      {importOpen && canManage && <CameraImportDialog onClose={() => setImportOpen(false)} />}
      {isError && <Alert severity="error" action={<Button onClick={() => refetch()}>Retry</Button>}>Camera inventory unavailable. Previous results are hidden.</Alert>}
      {actionError && <Alert severity="error">{actionError}</Alert>}
      <Button component={Link} to="/detection-health">Review detection health</Button>
      <AddCameraDialog open={addOpen} onClose={() => setAddOpen(false)} />
      <AddCameraDialog open={!!editCamera} onClose={() => setEditCamera(null)} camera={editCamera} />

      <Paper variant="outlined">
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Code</TableCell>
              <TableCell>RTSP URL</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>This camera enforces</TableCell>
              <TableCell>Worker / connection check</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(!isError ? cameras ?? [] : []).slice(visiblePage * 50, visiblePage * 50 + 50).map((cam) => (
              <TableRow key={cam.id} hover>
                <TableCell>{cam.name}</TableCell>
                <TableCell>{cam.code}</TableCell>
                <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>{cam.rtsp_url}</TableCell>
                <TableCell>
                  <Chip size="small" label={cam.status} color={STATUS_COLOR[cam.status] ?? "default"} />
                </TableCell>
                <TableCell>{formatEnforcedPpe(cam.enforces, ppeTypes)}</TableCell>
                <TableCell>{cam.worker_id ? "Worker assigned" : "No worker assigned"}<Typography variant="caption" display="block">{checks[cam.id] ?? "Connection not checked in this session"}</Typography></TableCell>
                <TableCell align="right">
                  {canManage && <>
                  {cam.status === "Inactive" && <Button size="small" disabled={activate.isPending} onClick={() => activate.mutate(cam.id)}>Activate</Button>}
                  <Button
                    size="small"
                    onClick={() => testMutation.mutate(cam.id)}
                    disabled={testMutation.isPending}
                  >
                    Test Connection
                  </Button>
                  <Tooltip title="Edit camera">
                    <IconButton size="small" onClick={() => setEditCamera(cam)}>
                      <EditOutlinedIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  </>}
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && !isError && (cameras ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={7}>
                  <Typography variant="body2" color="text.secondary">
                    No cameras registered yet.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        <TablePagination component="div" count={isError ? 0 : cameras?.length ?? 0} page={visiblePage} rowsPerPage={50} rowsPerPageOptions={[50]} onPageChange={(_, next) => setPage(next)} />
      </Paper>
    </Stack>
  );
}
