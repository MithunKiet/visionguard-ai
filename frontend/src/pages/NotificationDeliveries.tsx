import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, MenuItem, Paper, Stack, Table, TableBody, TableCell, TableHead, TablePagination, TableRow, TextField, Typography } from "@mui/material";
import { api } from "../api/client";
import { useAuthStore } from "../store/authStore";

interface Delivery {
  id: string;
  alert_number: string;
  channel: string;
  status: string;
  attempts: number;
  next_attempt_at: string;
  last_error: string | null;
}

const statuses = ["", "Failed", "Retrying", "Pending", "Skipped", "Sent", "Published"];

export function NotificationDeliveries() {
  const roles = useAuthStore(s => s.user?.roles ?? []);
  const allowed = roles.some(role => ["SYSTEM_ADMIN", "ENTERPRISE_ADMIN"].includes(role));
  const [status, setStatus] = useState("Failed");
  const [page, setPage] = useState(0);
  const client = useQueryClient();
  const deliveries = useQuery({
    queryKey: ["notification-deliveries", status, page], enabled: allowed, refetchInterval: 15000,
    queryFn: async () => {
      const response = await api.get("/notifications/deliveries", { params: { status: status || undefined, page: page + 1, page_size: 50 } });
      return { items: response.data.data as Delivery[], total: response.data.meta.total as number };
    },
  });
  const summary = useQuery({
    queryKey: ["notification-delivery-summary"], enabled: allowed, refetchInterval: 15000,
    queryFn: async () => (await api.get("/notifications/deliveries/summary")).data.data as {
      counts: Record<string, number>; oldest_pending_at: string | null;
    },
  });
  const retry = useMutation({
    mutationFn: (id: string) => api.post(`/notifications/deliveries/${id}/retry`),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["notification-deliveries"] }),
        client.invalidateQueries({ queryKey: ["notification-delivery-summary"] }),
      ]);
    },
  });
  if (!allowed) return <Alert severity="info">Enterprise administrator access is required.</Alert>;
  return <Stack spacing={2}>
    <Typography variant="h5" fontWeight={700}>Notification delivery</Typography>
    <Typography color="text.secondary">Failed: {summary.data?.counts.Failed ?? "—"} · Waiting: {summary.data ? (summary.data.counts.Pending ?? 0) + (summary.data.counts.Retrying ?? 0) : "—"}</Typography>
    {summary.data?.oldest_pending_at && <Typography variant="body2">Oldest waiting notification: {new Date(summary.data.oldest_pending_at).toLocaleString()}</Typography>}
    <Typography variant="body2" color="text.secondary">Sent means accepted by the provider. Published means a live update was sent; neither confirms that someone read it. Retrying a failed delivery may produce a duplicate if the provider accepted an earlier attempt.</Typography>
    {(deliveries.isError || summary.isError) && <Alert severity="error">Delivery status could not be loaded. Please refresh and retry.</Alert>}
    {retry.isError && <Alert severity="error">Retry could not be queued. Refresh the list and check the delivery status.</Alert>}
    <TextField select label="Delivery status" value={status} onChange={e => { setStatus(e.target.value); setPage(0); }} sx={{ width: 220 }}>
      {statuses.map(value => <MenuItem key={value || "all"} value={value}>{value || "All"}</MenuItem>)}
    </TextField>
    <Paper variant="outlined" sx={{ overflowX: "auto" }}>
      <Table size="small">
        <TableHead><TableRow>{["Alert", "Channel", "Status", "Attempts", "Next attempt", "Last result", "Action"].map(label => <TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead>
        <TableBody>
          {(deliveries.data?.items ?? []).map(job => <TableRow key={job.id}>
            <TableCell>{job.alert_number}</TableCell><TableCell>{job.channel}</TableCell><TableCell>{job.status}</TableCell><TableCell>{job.attempts}</TableCell>
            <TableCell>{["Pending", "Retrying"].includes(job.status) ? new Date(job.next_attempt_at).toLocaleString() : "—"}</TableCell>
            <TableCell>{job.last_error?.replace(/_/g, " ") || "—"}</TableCell>
            <TableCell>{["Failed", "Skipped"].includes(job.status) && <Button disabled={retry.isPending} onClick={() => retry.mutate(job.id)}>Retry delivery</Button>}</TableCell>
          </TableRow>)}
          {!deliveries.data?.items.length && <TableRow><TableCell colSpan={7}>{deliveries.isLoading ? "Loading deliveries…" : deliveries.isError ? "Delivery status unavailable." : "No deliveries for this filter."}</TableCell></TableRow>}
        </TableBody>
      </Table>
      <TablePagination component="div" count={deliveries.data?.total ?? 0} page={page} rowsPerPage={50} rowsPerPageOptions={[50]} onPageChange={(_, next) => setPage(next)} />
    </Paper>
  </Stack>;
}
