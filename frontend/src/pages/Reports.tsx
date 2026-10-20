import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Chip, Paper, Stack, Table, TableBody, TableCell, TableHead, TablePagination, TableRow, TextField, Typography } from "@mui/material";
import { api } from "../api/client";
import { useAuthStore } from "../store/authStore";

type Report = {
  id: string; report_type: string; format: string; from_date: string; to_date: string;
  status: string; stage: string; attempts: number; row_count: number | null;
  failure_message: string | null; next_attempt_at: string | null;
};

function localDateTime(date: Date) {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

export function Reports() {
  const queryClient = useQueryClient();
  const user = useAuthStore(state => state.user);
  const allowed = user?.roles.some(role => ["SYSTEM_ADMIN", "ENTERPRISE_ADMIN"].includes(role));
  const [page, setPage] = useState(0);
  const [reportType, setReportType] = useState("violations_summary");
  const [format, setFormat] = useState("xlsx");
  const [from, setFrom] = useState(() => localDateTime(new Date(Date.now() - 7 * 86400000)));
  const [to, setTo] = useState(() => localDateTime(new Date()));
  const [notice, setNotice] = useState("");
  const request = useRef<{ body: string; key: string } | null>(null);
  const reports = useQuery({
    queryKey: ["reports", page], enabled: !!allowed,
    queryFn: async ({ signal }) => {
      const response = await api.get("/reports", { params: { page: page + 1, page_size: 20 }, signal });
      return { items: response.data.data as Report[], total: response.data.meta.total as number };
    },
    refetchInterval: 5000,
  });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["reports"] });
  const generate = useMutation({
    mutationFn: async () => {
      if (!from || !to || new Date(from) > new Date(to)) throw new Error("Choose a valid start and end time.");
      const payload = { report_type: reportType, format, from_date: new Date(from).toISOString(), to_date: new Date(to).toISOString() };
      const body = JSON.stringify(payload);
      if (request.current?.body !== body) request.current = { body, key: crypto.randomUUID() };
      return api.post("/reports/generate", payload, { headers: { "Idempotency-Key": request.current!.key } });
    },
    onSuccess: () => { request.current = null; setPage(0); setNotice("Report queued. You can leave this page and return later."); },
    onSettled: invalidate,
  });
  const retry = useMutation({
    mutationFn: (id: string) => api.post(`/reports/${id}/retry`),
    onSuccess: () => setNotice("Report queued for another attempt."),
    onSettled: invalidate,
  });
  const download = useMutation({
    mutationFn: async (id: string) => {
      const response = await api.get(`/reports/${id}/download`);
      // Links are requested only after a click and current server-side authorization.
      const link = document.createElement("a");
      link.href = response.data.data.download_url;
      link.rel = "noopener noreferrer";
      link.target = "_blank";
      document.body.appendChild(link);
      link.click();
      link.remove();
    },
  });
  const error = (err: any) => err?.response?.data?.error?.message ?? err?.message ?? "The request could not be completed.";
  if (!allowed) return <Alert severity="warning">Enterprise administrator access is required for reports.</Alert>;
  return <Stack spacing={3}>
    <Typography variant="h5" fontWeight={700}>Reports</Typography>
    <Typography variant="body2">Generate enterprise-wide violation or alert reports in the background. Times below use your browser's timezone.</Typography>
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={2}>
        <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
          <TextField select label="Report type" value={reportType} onChange={e => setReportType(e.target.value)} SelectProps={{ native: true }}>
            <option value="violations_summary">PPE violations</option><option value="alerts_summary">Alerts</option>
          </TextField>
          <TextField select label="Format" value={format} onChange={e => setFormat(e.target.value)} SelectProps={{ native: true }}>
            <option value="xlsx">Excel</option><option value="pdf">PDF</option>
          </TextField>
          <TextField label="From" type="datetime-local" value={from} onChange={e => setFrom(e.target.value)} InputLabelProps={{ shrink: true }} />
          <TextField label="To" type="datetime-local" value={to} onChange={e => setTo(e.target.value)} InputLabelProps={{ shrink: true }} />
        </Stack>
        <Typography variant="caption">Maximum 366 days per request; PDF supports 5,000 rows and Excel 50,000. Larger results require a shorter period.</Typography>
        <Button variant="contained" disabled={generate.isPending} onClick={() => { setNotice(""); generate.mutate(); }}>
          {generate.isPending ? "Queueing…" : "Generate report"}
        </Button>
      </Stack>
    </Paper>
    {notice && <Alert severity="info" onClose={() => setNotice("")}>{notice}</Alert>}
    {generate.isError && <Alert severity="error">Report request could not be confirmed: {error(generate.error)} Retry the same request to avoid duplicates.</Alert>}
    {retry.isError && <Alert severity="error">Retry could not be confirmed: {error(retry.error)}</Alert>}
    {download.isError && <Alert severity="error">Download unavailable: {error(download.error)}</Alert>}
    {reports.isError && <Alert severity="error" action={<Button onClick={() => reports.refetch()}>Refresh</Button>}>Reports could not be loaded.</Alert>}
    <Paper variant="outlined" sx={{ overflowX: "auto" }}>
      <Table size="small"><TableHead><TableRow>
        <TableCell>Report</TableCell><TableCell>Period</TableCell><TableCell>Status / progress</TableCell><TableCell>Rows</TableCell><TableCell>Actions</TableCell>
      </TableRow></TableHead><TableBody>
        {!reports.isError && reports.data?.items.map(report => <TableRow key={report.id}>
          <TableCell>{report.report_type === "alerts_summary" ? "Alerts" : "PPE violations"} · {report.format.toUpperCase()}</TableCell>
          <TableCell>{new Date(report.from_date).toLocaleString()} – {new Date(report.to_date).toLocaleString()}</TableCell>
          <TableCell><Stack spacing={0.5} alignItems="flex-start">
            <Chip size="small" label={report.status} color={report.status === "Completed" ? "success" : report.status === "Failed" ? "error" : "default"} />
            {report.status === "Running" && <Typography variant="caption">{report.stage} · Attempt {report.attempts}</Typography>}
            {report.failure_message && <Typography variant="caption">{report.failure_message}</Typography>}
            {report.status === "Retrying" && report.next_attempt_at && <Typography variant="caption">Automatic retry after {new Date(report.next_attempt_at).toLocaleString()}</Typography>}
          </Stack></TableCell>
          <TableCell>{report.row_count ?? "—"}</TableCell>
          <TableCell>{report.status === "Completed" && <Button disabled={download.isPending} onClick={() => download.mutate(report.id)}>Download</Button>}
            {report.status === "Failed" && <Button disabled={retry.isPending} onClick={() => retry.mutate(report.id)}>Retry report</Button>}</TableCell>
        </TableRow>)}
        {reports.isLoading && <TableRow><TableCell colSpan={5}>Loading reports…</TableCell></TableRow>}
        {!reports.isLoading && !reports.isError && reports.data?.items.length === 0 && <TableRow><TableCell colSpan={5}>No reports on this page.</TableCell></TableRow>}
      </TableBody></Table>
      <TablePagination component="div" count={reports.data?.total ?? 0} page={page} rowsPerPage={20} rowsPerPageOptions={[20]} onPageChange={(_, next) => setPage(next)} />
    </Paper>
  </Stack>;
}
