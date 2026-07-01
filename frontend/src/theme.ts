import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#0F5C4A" },
    secondary: { main: "#D97706" },
    error: { main: "#DC2626" },
    warning: { main: "#F59E0B" },
    success: { main: "#16A34A" },
    background: { default: "#F4F6F5", paper: "#FFFFFF" },
  },
  shape: { borderRadius: 8 },
  typography: {
    fontFamily: '"Inter", "Segoe UI", Roboto, sans-serif',
  },
});
