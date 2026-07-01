import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { api } from "../api/client";

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
  const { data: cameras, isLoading } = useQuery({
    queryKey: ["cameras"],
    queryFn: fetchCameras,
    refetchInterval: 15000,
  });

  const testMutation = useMutation({
    mutationFn: testConnection,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["cameras"] }),
  });

  return (
    <Stack spacing={3}>
      <Typography variant="h5" fontWeight={700}>
        Cameras
      </Typography>

      <Paper variant="outlined">
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Code</TableCell>
              <TableCell>RTSP URL</TableCell>
              <TableCell>Status</TableCell>
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
                <TableCell align="right">
                  <Button
                    size="small"
                    onClick={() => testMutation.mutate(cam.rtsp_url)}
                    disabled={testMutation.isPending}
                  >
                    Test Connection
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && (cameras ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>
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
