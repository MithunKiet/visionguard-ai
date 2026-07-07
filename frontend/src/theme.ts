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
  components: {
    // The searchable dropdowns (SearchableSelect + plain Autocomplete usages)
    // otherwise render a flat, barely-separated popup — no shadow, no
    // spacing between options, no visible hover/selected state.
    MuiAutocomplete: {
      styleOverrides: {
        paper: {
          marginTop: 4,
          borderRadius: 8,
          boxShadow: "0 8px 24px rgba(16, 24, 40, 0.12)",
          border: "1px solid #E5E7EB",
        },
        listbox: {
          padding: 4,
        },
        option: {
          borderRadius: 6,
          padding: "8px 12px",
          '&[aria-selected="true"]': {
            backgroundColor: "rgba(15, 92, 74, 0.08)",
          },
          '&.Mui-focused': {
            backgroundColor: "rgba(15, 92, 74, 0.06) !important",
          },
        },
      },
    },
  },
});
