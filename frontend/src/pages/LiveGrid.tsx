import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import FullscreenExitIcon from "@mui/icons-material/FullscreenExit";
import FullscreenIcon from "@mui/icons-material/Fullscreen";
import PauseCircleOutlineIcon from "@mui/icons-material/PauseCircleOutline";
import PowerSettingsNewIcon from "@mui/icons-material/PowerSettingsNew";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { api, MEDIAMTX_WEBRTC_URL } from "../api/client";

async function fetchCameras() {
  const resp = await api.get("/cameras");
  return resp.data.data as any[];
}

async function setCameraStatus(id: string, status: "Active" | "Inactive") {
  await api.patch(`/cameras/${id}/status`, { status });
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
  Inactive: "default",
};

export function LiveGrid() {
  const queryClient = useQueryClient();
  const [fullscreenId, setFullscreenId] = useState<string | null>(null);
  const tileRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const { data: cameras, isLoading } = useQuery({
    queryKey: ["cameras-live-grid"],
    queryFn: fetchCameras,
    refetchInterval: 30000,
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "Active" | "Inactive" }) =>
      setCameraStatus(id, status),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["cameras-live-grid"] });
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
    },
  });

  // Esc, browser back-gesture, or clicking the exit-fullscreen button all
  // fire this — keep fullscreenId in sync so the tile's own layout/icon
  // revert without needing a separate "am I still fullscreen?" poll.
  useEffect(() => {
    const onChange = () => {
      if (!document.fullscreenElement) setFullscreenId(null);
    };
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  function toggleFullscreen(id: string) {
    if (fullscreenId === id) {
      document.exitFullscreen();
      return;
    }
    tileRefs.current[id]?.requestFullscreen();
    setFullscreenId(id);
  }

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
        {(cameras ?? []).map((cam) => {
          const isOff = cam.status === "Inactive";
          const isFullscreen = fullscreenId === cam.id;
          return (
            <Grid item xs={12} sm={6} md={4} key={cam.id}>
              <Paper
                ref={(el: HTMLDivElement | null) => {
                  tileRefs.current[cam.id] = el;
                }}
                variant="outlined"
                sx={{
                  overflow: "hidden",
                  ...(isFullscreen && {
                    height: "100vh",
                    display: "flex",
                    flexDirection: "column",
                    bgcolor: "black",
                  }),
                }}
              >
                <Stack
                  direction="row"
                  justifyContent="space-between"
                  alignItems="center"
                  sx={{ px: 1.5, py: 1 }}
                >
                  <Typography variant="body2" fontWeight={600}>
                    {cam.name}
                  </Typography>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Chip size="small" label={cam.status} color={STATUS_COLOR[cam.status] ?? "default"} />
                    <Button
                      size="small"
                      variant="outlined"
                      color={isOff ? "success" : "error"}
                      startIcon={<PowerSettingsNewIcon fontSize="small" />}
                      disabled={toggleMutation.isPending}
                      onClick={() =>
                        toggleMutation.mutate({ id: cam.id, status: isOff ? "Active" : "Inactive" })
                      }
                    >
                      {isOff ? "Turn On" : "Turn Off"}
                    </Button>
                  </Stack>
                </Stack>
                <Box
                  onClick={() => toggleFullscreen(cam.id)}
                  sx={{
                    position: "relative",
                    background: "#000",
                    cursor: "pointer",
                    ...(isFullscreen
                      ? { flex: 1, minHeight: 0 }
                      : { aspectRatio: "4 / 3" }),
                    "&:hover .fullscreen-overlay": { opacity: 1 },
                  }}
                >
                  {isOff ? (
                    <Stack
                      alignItems="center"
                      justifyContent="center"
                      spacing={1}
                      sx={{ height: "100%", color: "grey.400" }}
                    >
                      <PauseCircleOutlineIcon fontSize="large" />
                      <Typography variant="body2">Camera turned off</Typography>
                    </Stack>
                  ) : (
                    <iframe
                      key={cam.id}
                      title={cam.name}
                      src={`${MEDIAMTX_WEBRTC_URL}/${mediamtxPath(cam.rtsp_url)}/`}
                      style={{ width: "100%", height: "100%", border: 0, pointerEvents: "none" }}
                      allow="autoplay"
                    />
                  )}
                  <Tooltip title={isFullscreen ? "Exit full screen" : "Full screen"}>
                    <Box
                      className="fullscreen-overlay"
                      sx={{
                        position: "absolute",
                        top: 8,
                        right: 8,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        width: 32,
                        height: 32,
                        borderRadius: 1,
                        bgcolor: "rgba(0,0,0,0.55)",
                        color: "white",
                        opacity: isFullscreen ? 1 : 0,
                        transition: "opacity 0.15s",
                      }}
                    >
                      {isFullscreen ? (
                        <FullscreenExitIcon fontSize="small" />
                      ) : (
                        <FullscreenIcon fontSize="small" />
                      )}
                    </Box>
                  </Tooltip>
                </Box>
              </Paper>
            </Grid>
          );
        })}

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
