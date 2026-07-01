import Chip from "@mui/material/Chip";

const COLORS: Record<string, "error" | "warning" | "info" | "default"> = {
  Critical: "error",
  High: "warning",
  Medium: "info",
  Low: "default",
};

export function SeverityChip({ severity }: { severity: string }) {
  return <Chip label={severity} color={COLORS[severity] ?? "default"} size="small" />;
}

const STATUS_COLORS: Record<string, "error" | "warning" | "success" | "default"> = {
  Open: "error",
  Acknowledged: "warning",
  Resolved: "success",
  FalsePositive: "default",
};

export function StatusChip({ status }: { status: string }) {
  return <Chip label={status} color={STATUS_COLORS[status] ?? "default"} size="small" variant="outlined" />;
}
