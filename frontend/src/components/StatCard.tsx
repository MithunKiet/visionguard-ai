import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

export function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: number | string;
  accent?: string;
}) {
  return (
    <Paper variant="outlined" sx={{ p: 2.5, flex: 1, minWidth: 160 }}>
      <Stack spacing={0.5}>
        <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 1 }}>
          {label}
        </Typography>
        <Typography variant="h4" fontWeight={700} sx={{ color: accent }}>
          {value}
        </Typography>
      </Stack>
    </Paper>
  );
}
