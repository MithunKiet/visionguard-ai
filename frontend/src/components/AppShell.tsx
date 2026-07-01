import { useMemo } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import DashboardIcon from "@mui/icons-material/SpaceDashboard";
import VideocamIcon from "@mui/icons-material/Videocam";
import WarningIcon from "@mui/icons-material/WarningAmber";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive";
import LogoutIcon from "@mui/icons-material/Logout";
import CircleIcon from "@mui/icons-material/Circle";
import { useAuthStore } from "../store/authStore";
import { useLiveFeed } from "../hooks/useWebSocket";

const DRAWER_WIDTH = 220;

const NAV = [
  { to: "/", label: "Dashboard", icon: <DashboardIcon /> },
  { to: "/cameras", label: "Cameras", icon: <VideocamIcon /> },
  { to: "/violations", label: "Violations", icon: <WarningIcon /> },
  { to: "/alerts", label: "Alerts", icon: <NotificationsActiveIcon /> },
];

export function AppShell() {
  const navigate = useNavigate();
  const { user, isMasterSession, clearSession } = useAuthStore();
  const { connected } = useLiveFeed(1);

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
          [`& .MuiDrawer-paper`]: { width: DRAWER_WIDTH, boxSizing: "border-box" },
        }}
      >
        <Toolbar>
          <Typography variant="h6" fontWeight={700} color="primary">
            VisionGuard
          </Typography>
        </Toolbar>
        <List>
          {NAV.map((item) => (
            <ListItemButton
              key={item.to}
              component={NavLink}
              to={item.to}
              end={item.to === "/"}
              sx={{
                "&.active": {
                  bgcolor: "action.selected",
                  borderRight: "3px solid",
                  borderColor: "primary.main",
                },
              }}
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.label} />
            </ListItemButton>
          ))}
        </List>
      </Drawer>

      <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column" }}>
        <AppBar position="static" color="inherit" elevation={0} sx={{ borderBottom: "1px solid #E5E7EB" }}>
          <Toolbar sx={{ gap: 2 }}>
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
