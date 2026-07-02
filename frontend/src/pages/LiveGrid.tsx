import { useQuery } from "@tanstack/react-query";
import Chip from "@mui/material/Chip";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api, MEDIAMTX_WEBRTC_URL } from "../api/client";

async function fetchCameras() {
  const resp = await api.get("/cameras");
  return resp.data.data as any[];
}

/** Pulls the mediamtx path out of an rtsp_url like rtsp://mediamtx:8554/factory-cam-01 */
function mediamtxPath(rtspUrl: string): string {
  return rtspUrl.split("/").pop() ?? "";
}

const STATUS_COLOR: Record<string, "success" | "error" | "warning" | "default"> = {
  Active: "success",
  Offline: "error",
  Degraded: "warning",
  Maintenance: "default",
};

export function LiveGrid() {
  const { data: cameras, isLoading } = useQuery({
    queryKey: ["cameras-live-grid"],
    queryFn: fetchCameras,
    refetchInterval: 30000,
  });

  return (
    <Stack spacing={3}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h5" fontWeight={700}>
          Live Grid
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {cameras?.length ?? 0} camera{(cameras?.length ?? 0) === 1 ? "" : "s"}
        </Typography>
      </Stack>

      <Grid container spacing={2}>
        {(cameras ?? []).map((cam) => (
          <Grid item xs={12} sm={6} md={4} key={cam.id}>
            <Paper variant="outlined" sx={{ overflow: "hidden" }}>
              <Stack
                direction="row"
                justifyContent="space-between"
                alignItems="center"
                sx={{ px: 1.5, py: 1 }}
              >
                <Typography variant="body2" fontWeight={600}>
                  {cam.name}
                </Typography>
                <Chip size="small" label={cam.status} color={STATUS_COLOR[cam.status] ?? "default"} />
              </Stack>
              <div style={{ aspectRatio: "4 / 3", background: "#000" }}>
                <iframe
                  key={cam.id}
                  title={cam.name}
                  src={`${MEDIAMTX_WEBRTC_URL}/${mediamtxPath(cam.rtsp_url)}/`}
                  style={{ width: "100%", height: "100%", border: 0 }}
                  allow="autoplay"
                />
              </div>
            </Paper>
          </Grid>
        ))}

        {!isLoading && (cameras ?? []).length === 0 && (
          <Grid item xs={12}>
            <Typography variant="body2" color="text.secondary">
              No cameras registered yet.
            </Typography>
          </Grid>
        )}
      </Grid>
    </Stack>
  );
}
