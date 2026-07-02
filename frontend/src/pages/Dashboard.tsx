import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardMedia from "@mui/material/CardMedia";
import Grid from "@mui/material/Grid";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api } from "../api/client";
import { StatCard } from "../components/StatCard";
import { SeverityChip } from "../components/SeverityChip";
import { useLiveFeed } from "../hooks/useWebSocket";

async function fetchOpenAlertCounts() {
  const resp = await api.get("/alerts", { params: { status: "Open", page_size: 100 } });
  const alerts: any[] = resp.data.data;
  return {
    total: alerts.length,
    critical: alerts.filter((a) => a.severity === "Critical").length,
    high: alerts.filter((a) => a.severity === "High").length,
  };
}

async function fetchRecentViolations() {
  const resp = await api.get("/violations", { params: { page_size: 8 } });
  return resp.data.data as any[];
}

// Occupancy readings are telemetry, not activity — they get their own stat
// card instead of flooding the activity feed.
const FEED_LABELS: Record<string, string> = {
  "violation.created": "Violation detected",
  "alert.created": "Alert created",
  "camera.status_changed": "Camera status changed",
};

export function Dashboard() {
  const queryClient = useQueryClient();
  const { events, connected } = useLiveFeed(50);

  const feedEvents = events.filter((e) => e.type !== "occupancy.updated").slice(0, 20);
  const latestOccupancy = events.find((e) => e.type === "occupancy.updated");

  const { data: counts } = useQuery({
    queryKey: ["open-alert-counts"],
    queryFn: fetchOpenAlertCounts,
    refetchInterval: 30000,
  });

  const { data: violations } = useQuery({
    queryKey: ["recent-violations"],
    queryFn: fetchRecentViolations,
    refetchInterval: 30000,
  });

  // Meaningful live events invalidate the summary queries so counters/lists
  // stay fresh; occupancy ticks alone shouldn't trigger refetch storms.
  useEffect(() => {
    if (feedEvents.length === 0) return;
    queryClient.invalidateQueries({ queryKey: ["open-alert-counts"] });
    queryClient.invalidateQueries({ queryKey: ["recent-violations"] });
  }, [feedEvents.length, queryClient]);

  return (
    <Stack spacing={3}>
      <Typography variant="h5" fontWeight={700}>
        Dashboard
      </Typography>

      <Stack direction="row" spacing={2} flexWrap="wrap">
        <StatCard label="Open Alerts" value={counts?.total ?? "-"} />
        <StatCard label="Critical" value={counts?.critical ?? "-"} accent="#DC2626" />
        <StatCard label="High" value={counts?.high ?? "-"} accent="#F59E0B" />
        <StatCard
          label="Live Occupancy"
          value={latestOccupancy?.data?.current_count ?? "-"}
          accent="#2563EB"
        />
        <StatCard label="Live Connection" value={connected ? "Connected" : "Reconnecting..."} />
      </Stack>

      <Grid container spacing={3}>
        <Grid item xs={12} md={7}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="subtitle1" fontWeight={600} gutterBottom>
              Recent Violations
            </Typography>
            <Grid container spacing={2}>
              {(violations ?? []).map((v) => (
                <Grid item xs={6} sm={4} md={3} key={v.id}>
                  <Card variant="outlined">
                    {v.snapshot_url ? (
                      <CardMedia component="img" height="90" image={v.snapshot_url} alt={v.violation_type} />
                    ) : (
                      <Box sx={{ height: 90, bgcolor: "grey.100" }} />
                    )}
                    <Box sx={{ p: 1 }}>
                      <Typography variant="caption" display="block" fontWeight={600}>
                        {v.violation_type.replace("_", " ")}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {(v.confidence * 100).toFixed(0)}% conf.
                      </Typography>
                    </Box>
                  </Card>
                </Grid>
              ))}
              {(violations ?? []).length === 0 && (
                <Grid item xs={12}>
                  <Typography variant="body2" color="text.secondary">
                    No violations recorded yet.
                  </Typography>
                </Grid>
              )}
            </Grid>
          </Paper>
        </Grid>

        <Grid item xs={12} md={5}>
          <Paper variant="outlined" sx={{ p: 2, height: "100%" }}>
            <Typography variant="subtitle1" fontWeight={600} gutterBottom>
              Live Feed
            </Typography>
            <List dense sx={{ maxHeight: 420, overflowY: "auto" }}>
              {feedEvents.map((e, idx) => (
                <ListItem key={idx} divider>
                  <ListItemText
                    primary={
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="body2" fontWeight={600}>
                          {FEED_LABELS[e.type] ?? e.type}
                        </Typography>
                        {e.data?.severity && <SeverityChip severity={e.data.severity} />}
                      </Stack>
                    }
                    secondary={
                      e.data?.alert_number ??
                      e.data?.violation_type?.replace(/_/g, " ") ??
                      (e.data?.status ? `Camera ${e.data.status}` : null)
                    }
                  />
                </ListItem>
              ))}
              {feedEvents.length === 0 && (
                <Typography variant="body2" color="text.secondary" sx={{ p: 1 }}>
                  Waiting for activity — violations, alerts, and camera status changes appear here.
                </Typography>
              )}
            </List>
          </Paper>
        </Grid>
      </Grid>
    </Stack>
  );
}
