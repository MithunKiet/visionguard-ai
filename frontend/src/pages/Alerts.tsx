import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, MenuItem, Paper, Stack, Table, TableBody, TableCell, TableHead, TablePagination, TableRow, TextField, Typography } from "@mui/material";
import { api } from "../api/client";
import { SeverityChip, StatusChip } from "../components/SeverityChip";
import { IncidentReview, type Incident } from "../components/IncidentReview";

const STATUS_OPTIONS = ["", "Open", "Acknowledged", "Resolved", "FalsePositive"];
const SEVERITY_OPTIONS = ["", "Critical", "High", "Medium", "Low"];

export function Alerts() {
  const [page, setPage] = useState(0);
  const [status, setStatus] = useState("Open");
  const [severity, setSeverity] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const result = useQuery({
    queryKey: ["alerts", status, severity, page], refetchInterval: 15000,
    queryFn: async () => {
      const response = await api.get("/alerts", { params: { status: status || undefined, severity: severity || undefined, page: page + 1, page_size: 50 } });
      return { items: response.data.data as Incident[], total: response.data.meta.total as number };
    },
  });

  useEffect(() => {
    if (result.data && !result.isFetching && !result.isError) {
      const lastPage = Math.max(0, Math.ceil(result.data.total / 50) - 1);
      if (page > lastPage) setPage(lastPage);
    }
  }, [result.data, result.isFetching, result.isError, page]);

  return <Stack spacing={3}>
    <Typography variant="h5" fontWeight={700}>Alerts</Typography>
    <Typography color="text.secondary">Open an incident to inspect evidence, review its history and record your decision.</Typography>
    <Stack direction="row" spacing={2}>
      <TextField select label="Status" value={status} onChange={event => { setStatus(event.target.value); setPage(0); }} sx={{ minWidth: 180 }}>
        {STATUS_OPTIONS.map(value => <MenuItem key={value || "all"} value={value}>{value === "FalsePositive" ? "False positive" : value || "All"}</MenuItem>)}
      </TextField>
      <TextField select label="Severity" value={severity} onChange={event => { setSeverity(event.target.value); setPage(0); }} sx={{ minWidth: 150 }}>
        {SEVERITY_OPTIONS.map(value => <MenuItem key={value || "all"} value={value}>{value || "All"}</MenuItem>)}
      </TextField>
    </Stack>
    {result.isError && <Alert severity="error" action={<Button color="inherit" onClick={() => void result.refetch()}>Retry</Button>}>Alerts could not be loaded.</Alert>}
    <Paper variant="outlined" sx={{ overflowX: "auto" }}>
      <Table size="small">
        <TableHead><TableRow>{["Alert #", "Type", "Severity", "Status", "Created", "SLA deadline", "Review"].map(title => <TableCell key={title}>{title}</TableCell>)}</TableRow></TableHead>
        <TableBody>
          {!result.isError && (result.data?.items ?? []).map(incident => <TableRow key={incident.id} hover>
            <TableCell sx={{ fontFamily: "monospace" }}>{incident.alert_number}</TableCell>
            <TableCell>{incident.alert_type.replace("PPE_VIOLATION_", "").replace(/_/g, " ")}</TableCell>
            <TableCell><SeverityChip severity={incident.severity} /></TableCell>
            <TableCell><StatusChip status={incident.status} /></TableCell>
            <TableCell>{new Date(incident.created_on).toLocaleString()}</TableCell>
            <TableCell>{incident.sla_due_at ? new Date(incident.sla_due_at).toLocaleString() : "—"}</TableCell>
            <TableCell><Button onClick={() => setSelected(incident.id)} aria-label={`Review ${incident.alert_number}`}>Review</Button></TableCell>
          </TableRow>)}
          {(result.isError || !result.data?.items.length) && <TableRow><TableCell colSpan={7}>
            {result.isLoading ? "Loading alerts…" : result.isError ? "Alert list unavailable." : "No alerts for this filter."}
          </TableCell></TableRow>}
        </TableBody>
      </Table>
      <TablePagination component="div" count={result.data?.total ?? 0} page={page} onPageChange={(_, next) => setPage(next)} rowsPerPage={50} rowsPerPageOptions={[50]} />
    </Paper>
    {selected && <IncidentReview key={selected} id={selected} onClose={() => setSelected(null)} />}
  </Stack>;
}
