import { useEffect, useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import Avatar from "@mui/material/Avatar";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import DashboardIcon from "@mui/icons-material/SpaceDashboard";
import VideocamIcon from "@mui/icons-material/Videocam";
import GridViewIcon from "@mui/icons-material/GridView";
import WarningIcon from "@mui/icons-material/WarningAmber";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive";
import LogoutIcon from "@mui/icons-material/Logout";
import CircleIcon from "@mui/icons-material/Circle";
import { api } from "../api/client";
import { useAuthStore } from "../store/authStore";
import { useLiveFeed } from "../hooks/useWebSocket";

const DRAWER_WIDTH = 220;

async function fetchBranding() {
  const resp = await api.get("/enterprise/branding");
  return resp.data.data as { name: string; tagline: string | null; logo_url: string | null };
}

const NAV = [
  { to: "/", label: "Dashboard", icon: <DashboardIcon /> },
  { to: "/cameras", label: "Cameras", icon: <VideocamIcon /> },
  { to: "/live", label: "Live Grid", icon: <GridViewIcon /> },
  { to: "/violations", label: "Violations", icon: <WarningIcon /> },
  { to: "/alerts", label: "Alerts", icon: <NotificationsActiveIcon /> },
];

export function AppShell() {
  const navigate = useNavigate();
  const { user, isMasterSession, clearSession } = useAuthStore();
  const { connected, events } = useLiveFeed(10);
  const lastNotifiedRef = useRef<string | null>(null);

  // Dynamic branding (master context rule #1/#2 — no hardcoded company
  // names anywhere). Rarely changes, so cache it for the session.
  const { data: branding } = useQuery({
    queryKey: ["enterprise-branding"],
    queryFn: fetchBranding,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });

  // Request permission once so the browser can show OS-level popups.
  useEffect(() => {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  // Desktop notification: only for alerts whose backend-configured
  // recipients (notifications.notification_recipients) include this user.
  useEffect(() => {
    const latest = events[0];
    if (!latest || latest.type !== "alert.created") return;
    const targets: string[] = latest.data?.notify_user_ids ?? [];
    if (!user || !targets.includes(user.id)) return;

    const key = latest.data?.id;
    if (!key || lastNotifiedRef.current === key) return;
    lastNotifiedRef.current = key;

    if ("Notification" in window && Notification.permission === "granted") {
      new Notification(`VisionGuard Alert — ${latest.data.severity}`, {
        body: `${latest.data.alert_type?.replace("PPE_VIOLATION_", "").replace("_", " ")} · ${latest.data.alert_number}`,
        tag: key,
      });
    }
  }, [events, user]);

  const initials = useMemo(() => {
    if (!user?.name) return "?";
    return user.name
      .split(" ")
      .map((p) => p[0])
      .slice(0, 2)
      .join("")
      .toUpperCase();
  }, [user]);

  const handleLogout = () => {
    clearSession();
    navigate("/login");
  };

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <Drawer
        variant="permanent"
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          [`& .MuiDrawer-paper`]: {
            width: DRAWER_WIDTH,
            boxSizing: "border-box",
            bgcolor: "#F8FAF9",
            borderRight: "1px solid #E5E7EB",
            display: "flex",
            flexDirection: "column",
          },
        }}
      >
        <Toolbar>
          <Typography variant="h6" fontWeight={700} color="primary">
            VisionGuard
          </Typography>
        </Toolbar>
        <List sx={{ px: 1 }}>
          {NAV.map((item) => (
            <ListItemButton
              key={item.to}
              component={NavLink}
              to={item.to}
              end={item.to === "/"}
              sx={{
                borderRadius: 1.5,
                mb: 0.5,
                "&.active": {
                  bgcolor: "primary.main",
                  color: "white",
                  "& .MuiListItemIcon-root": { color: "white" },
                  "&:hover": { bgcolor: "primary.main" },
                },
              }}
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.label} />
            </ListItemButton>
          ))}
        </List>

        <Box sx={{ flexGrow: 1 }} />

        <Stack spacing={0.5} sx={{ p: 2, borderTop: "1px solid #E5E7EB" }}>
          <Typography variant="caption" color="text.secondary" fontWeight={600}>
            VisionGuard AI
          </Typography>
          <Typography variant="caption" color="text.disabled">
            Enterprise Safety Platform · v1.0.0
          </Typography>
        </Stack>
      </Drawer>

      <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column" }}>
        <AppBar position="static" color="inherit" elevation={0} sx={{ borderBottom: "1px solid #E5E7EB" }}>
          <Toolbar sx={{ gap: 2 }}>
            {branding && (
              <Stack direction="row" spacing={1.5} alignItems="center">
                {branding.logo_url ? (
                  <Avatar src={branding.logo_url} variant="rounded" sx={{ width: 28, height: 28 }} />
                ) : null}
                <Stack spacing={0}>
                  <Typography variant="subtitle2" fontWeight={700} lineHeight={1.2}>
                    {branding.name}
                  </Typography>
                  {branding.tagline && (
                    <Typography variant="caption" color="text.secondary" lineHeight={1}>
                      {branding.tagline}
                    </Typography>
                  )}
                </Stack>
              </Stack>
            )}
            <Box sx={{ flexGrow: 1 }} />
            <Chip
              size="small"
              icon={<CircleIcon sx={{ fontSize: 10 }} color={connected ? "success" : "error"} />}
              label={connected ? "Live" : "Disconnected"}
              variant="outlined"
            />
            {isMasterSession && <Chip size="small" color="warning" label="Master session" />}
            <Typography variant="body2" color="text.secondary">
              {user?.name} · {user?.role}
            </Typography>
            <Box
              sx={{
                width: 32,
                height: 32,
                borderRadius: "50%",
                bgcolor: "primary.main",
                color: "white",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 13,
                fontWeight: 700,
              }}
            >
              {initials}
            </Box>
            <IconButton onClick={handleLogout} size="small" title="Logout">
              <LogoutIcon fontSize="small" />
            </IconButton>
          </Toolbar>
        </AppBar>

        <Box component="main" sx={{ flexGrow: 1, p: 3 }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
