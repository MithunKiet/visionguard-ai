import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import BlockIcon from "@mui/icons-material/Block";
import RateReviewIcon from "@mui/icons-material/RateReview";
import VideocamIcon from "@mui/icons-material/Videocam";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import ZoomInIcon from "@mui/icons-material/ZoomIn";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { api } from "../api/client";
import { StatCard } from "../components/StatCard";

async function fetchViolations() {
  const resp = await api.get("/violations", { params: { page_size: 100 } });
  return resp.data.data as any[];
}

const TYPE_COLOR: Record<string, "error" | "warning" | "info" | "default"> = {
  helmet_missing: "error",
  vest_missing: "warning",
  mask_missing: "warning",
  gloves_missing: "info",
  shoes_missing: "info",
};

function confidenceColor(confidence: number): "success" | "warning" | "error" {
  if (confidence >= 0.8) return "success";
  if (confidence >= 0.6) return "warning";
  return "error";
}

export function Violations() {
  const [preview, setPreview] = useState<any | null>(null);

  const { data: violations, isLoading } = useQuery({
    queryKey: ["violations"],
    queryFn: fetchViolations,
    refetchInterval: 20000,
  });

  const stats = useMemo(() => {
    const items = violations ?? [];
    return {
      total: items.length,
      needsReview: items.filter((v) => v.needs_review).length,
      falsePositive: items.filter((v) => v.is_false_positive).length,
    };
  }, [violations]);

  return (
    <Stack spacing={3}>
      <Typography variant="h5" fontWeight={700}>
        Violations
      </Typography>

      <Stack direction="row" spacing={2} flexWrap="wrap">
        <StatCard label="Total Violations" value={stats.total} accent="#0F5C4A" icon={<WarningAmberIcon />} />
        <StatCard label="Needs Review" value={stats.needsReview} accent="#F59E0B" icon={<RateReviewIcon />} />
        <StatCard label="False Positives" value={stats.falsePositive} accent="#6B7280" icon={<BlockIcon />} />
      </Stack>

      <Paper variant="outlined" sx={{ overflow: "hidden" }}>
        <Table>
          <TableHead>
            <TableRow sx={{ "& th": { bgcolor: "background.default", fontWeight: 700 } }}>
              <TableCell>Type</TableCell>
              <TableCell>Location</TableCell>
              <TableCell>Confidence</TableCell>
              <TableCell>Review</TableCell>
              <TableCell>Detected</TableCell>
              <TableCell align="center">Snapshot</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(violations ?? []).map((v) => (
              <TableRow key={v.id} hover>
                <TableCell>
                  <Chip
                    size="small"
                    label={v.violation_type.replace(/_/g, " ")}
                    color={TYPE_COLOR[v.violation_type] ?? "default"}
                    sx={{ textTransform: "capitalize", fontWeight: 600 }}
                  />
                </TableCell>
                <TableCell>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <VideocamIcon fontSize="small" sx={{ color: "text.disabled" }} />
                    <Stack spacing={0}>
                      <Typography variant="body2" fontWeight={600}>
                        {v.camera_name ?? v.camera_code ?? "Unknown camera"}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {v.zone_name ?? "—"}
                      </Typography>
                    </Stack>
                  </Stack>
                </TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    variant="outlined"
                    color={confidenceColor(v.confidence)}
                    label={`${(v.confidence * 100).toFixed(0)}%`}
                    sx={{ fontWeight: 600, minWidth: 56 }}
                  />
                </TableCell>
                <TableCell>
                  {v.needs_review ? (
                    <Chip size="small" color="warning" variant="outlined" label="Review" />
                  ) : (
                    <Typography variant="body2" color="text.disabled">
                      —
                    </Typography>
                  )}
                </TableCell>
                <TableCell>
                  <Typography variant="body2">{new Date(v.created_on).toLocaleString()}</Typography>
                </TableCell>
                <TableCell align="center">
                  {v.snapshot_url ? (
                    <Box
                      onClick={() => setPreview(v)}
                      sx={{
                        position: "relative",
                        display: "inline-block",
                        cursor: "pointer",
                        borderRadius: 1.5,
                        overflow: "hidden",
                        border: "1px solid",
                        borderColor: "divider",
                        lineHeight: 0,
                        "&:hover .zoom-overlay": { opacity: 1 },
                      }}
                    >
                      <img src={v.snapshot_url} alt="snapshot" style={{ height: 48, width: 72, objectFit: "cover", display: "block" }} />
                      <Stack
                        className="zoom-overlay"
                        alignItems="center"
                        justifyContent="center"
                        sx={{
                          position: "absolute",
                          inset: 0,
                          bgcolor: "rgba(0,0,0,0.45)",
                          opacity: 0,
                          transition: "opacity 0.15s",
                        }}
                      >
                        <ZoomInIcon sx={{ color: "white" }} fontSize="small" />
                      </Stack>
                    </Box>
                  ) : (
                    <Typography variant="body2" color="text.disabled">
                      No snapshot
                    </Typography>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && (violations ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: "center" }}>
                    No violations recorded yet.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>

      <Dialog open={!!preview} onClose={() => setPreview(null)} maxWidth="md">
        {preview && (
          <>
            <DialogTitle>
              <Stack direction="row" spacing={1.5} alignItems="center">
                <Chip
                  size="small"
                  label={preview.violation_type.replace(/_/g, " ")}
                  color={TYPE_COLOR[preview.violation_type] ?? "default"}
                  sx={{ textTransform: "capitalize", fontWeight: 600 }}
                />
                <Typography variant="body2" color="text.secondary">
                  {preview.camera_name ?? preview.camera_code} · {preview.zone_name} ·{" "}
                  {new Date(preview.created_on).toLocaleString()}
                </Typography>
              </Stack>
            </DialogTitle>
            <DialogContent>
              <img src={preview.snapshot_url} alt="violation snapshot" style={{ maxWidth: "100%", borderRadius: 8 }} />
            </DialogContent>
          </>
        )}
      </Dialog>
    </Stack>
  );
}
