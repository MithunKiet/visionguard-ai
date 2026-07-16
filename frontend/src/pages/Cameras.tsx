import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import AddIcon from "@mui/icons-material/Add";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
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

async function testConnection(rtsp_url: string) {
  const resp = await api.post("/cameras/test-connection", { rtsp_url });
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
  const [addOpen, setAddOpen] = useState(false);
  const [editCamera, setEditCamera] = useState<any | null>(null);
  const { data: cameras, isLoading } = useQuery({
    queryKey: ["cameras"],
    queryFn: fetchCameras,
    refetchInterval: 15000,
  });
  const { data: ppeTypes } = usePpeTypes();

  const testMutation = useMutation({
    mutationFn: testConnection,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["cameras"] }),
  });

  return (
    <Stack spacing={3}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h5" fontWeight={700}>
          Cameras
        </Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setAddOpen(true)}>
          Add Camera
        </Button>
      </Stack>

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
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(cameras ?? []).map((cam) => (
              <TableRow key={cam.id} hover>
                <TableCell>{cam.name}</TableCell>
                <TableCell>{cam.code}</TableCell>
                <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>{cam.rtsp_url}</TableCell>
                <TableCell>
                  <Chip size="small" label={cam.status} color={STATUS_COLOR[cam.status] ?? "default"} />
                </TableCell>
                <TableCell>{formatEnforcedPpe(cam.enforces, ppeTypes)}</TableCell>
                <TableCell align="right">
                  <Button
                    size="small"
                    onClick={() => testMutation.mutate(cam.rtsp_url)}
                    disabled={testMutation.isPending}
                  >
                    Test Connection
                  </Button>
                  <Tooltip title="Edit camera">
                    <IconButton size="small" onClick={() => setEditCamera(cam)}>
                      <EditOutlinedIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && (cameras ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography variant="body2" color="text.secondary">
                    No cameras registered yet.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>
    </Stack>
  );
}
