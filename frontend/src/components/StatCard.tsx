import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

export function StatCard({
  label,
  value,
  accent,
  icon,
}: {
  label: string;
  value: number | string;
  accent?: string;
  icon?: ReactNode;
}) {
  const color = accent ?? "#0F5C4A";
  return (
    <Paper
      elevation={0}
      sx={{
        p: 2.5,
        flex: 1,
        minWidth: 180,
        border: "1px solid",
        borderColor: "divider",
        boxShadow: "0 1px 2px rgba(16, 24, 40, 0.04)",
        transition: "box-shadow 0.15s, transform 0.15s",
        "&:hover": {
          boxShadow: "0 4px 12px rgba(16, 24, 40, 0.08)",
          transform: "translateY(-1px)",
        },
      }}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
        <Stack spacing={0.5}>
          <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 1 }}>
            {label}
          </Typography>
          <Typography variant="h4" fontWeight={700} sx={{ color: accent }}>
            {value}
          </Typography>
        </Stack>
        {icon && (
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: 40,
              height: 40,
              borderRadius: 2,
              bgcolor: `${color}1A`,
              color,
              flexShrink: 0,
            }}
          >
            {icon}
          </Box>
        )}
      </Stack>
    </Paper>
  );
}
