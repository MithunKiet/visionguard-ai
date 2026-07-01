import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../api/client";
import { SeverityChip, StatusChip } from "../components/SeverityChip";

const STATUS_OPTIONS = ["", "Open", "Acknowledged", "Resolved", "FalsePositive"];

async function fetchAlerts(status: string) {
  const resp = await api.get("/alerts", { params: status ? { status, page_size: 100 } : { page_size: 100 } });
  return resp.data.data as any[];
}

export function Alerts() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("Open");

  const { data: alerts, isLoading } = useQuery({
    queryKey: ["alerts", statusFilter],
    queryFn: () => fetchAlerts(statusFilter),
    refetchInterval: 15000,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["alerts"] });

  const ack = useMutation({
    mutationFn: (id: string) => api.patch(`/alerts/${id}/acknowledge`, {}),
    onSuccess: invalidate,
  });
  const resolve = useMutation({
    mutationFn: (id: string) => api.patch(`/alerts/${id}/resolve`, { note: "Resolved from dashboard" }),
    onSuccess: invalidate,
  });
  const falsePositive = useMutation({
    mutationFn: (id: string) => api.patch(`/alerts/${id}/false-positive`, { reason: "Marked from dashboard" }),
    onSuccess: invalidate,
  });

  return (
    <Stack spacing={3}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h5" fontWeight={700}>
          Alerts
        </Typography>
        <TextField
          select
          size="small"
          label="Status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          sx={{ width: 200 }}
        >
          {STATUS_OPTIONS.map((s) => (
            <MenuItem key={s} value={s}>
              {s || "All"}
            </MenuItem>
          ))}
        </TextField>
      </Stack>

      <Paper variant="outlined">
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Alert #</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Severity</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Created</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(alerts ?? []).map((a) => (
              <TableRow key={a.id} hover>
                <TableCell sx={{ fontFamily: "monospace" }}>{a.alert_number}</TableCell>
                <TableCell>{a.alert_type.replace("PPE_VIOLATION_", "")}</TableCell>
                <TableCell>
                  <SeverityChip severity={a.severity} />
                </TableCell>
                <TableCell>
                  <StatusChip status={a.status} />
                </TableCell>
                <TableCell>{new Date(a.created_on).toLocaleString()}</TableCell>
                <TableCell align="right">
                  <Stack direction="row" spacing={1} justifyContent="flex-end">
                    {a.status === "Open" && (
                      <Button size="small" onClick={() => ack.mutate(a.id)}>
                        Acknowledge
                      </Button>
                    )}
                    {(a.status === "Open" || a.status === "Acknowledged") && (
                      <>
                        <Button size="small" color="success" onClick={() => resolve.mutate(a.id)}>
                          Resolve
                        </Button>
                        <Button size="small" color="inherit" onClick={() => falsePositive.mutate(a.id)}>
                          False Positive
                        </Button>
                      </>
                    )}
                  </Stack>
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && (alerts ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography variant="body2" color="text.secondary">
                    No alerts for this filter.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>
    </Stack>
  );
}
