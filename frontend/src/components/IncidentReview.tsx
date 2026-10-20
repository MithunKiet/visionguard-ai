import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Divider, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { api } from "../api/client";
import { useAuthStore } from "../store/authStore";
import { SeverityChip, StatusChip } from "./SeverityChip";
import { CorrectiveAction } from "./CorrectiveAction";

export interface Incident {
  id: string;
  alert_number: string;
  alert_type: string;
  severity: string;
  status: string;
  created_on: string;
  sla_due_at: string | null;
  acknowledged_on: string | null;
  resolved_on: string | null;
  action_due_at?: string | null;
  action_completed_at?: string | null;
  violation_id: string | null;
  factory_name?: string | null;
  zone_name?: string | null;
  camera_name?: string | null;
  review_history?: { id: string; from_status: string; to_status: string; comment: string | null; reviewer_name: string | null; created_on: string | null; event_type?: string; details?: { description?: string } }[];
}

interface Evidence {
  confidence: number;
  snapshot_url: string | null;
  needs_review: boolean;
  is_false_positive: boolean;
  created_on: string;
}

const date = (value: string | null) => value ? new Date(value).toLocaleString() : "Not recorded";
const label = (status: string) => status === "FalsePositive" ? "False positive" : status;

export function IncidentReview({ id, onClose }: { id: string; onClose: () => void }) {
  const client = useQueryClient();
  const roles = useAuthStore(state => state.user?.roles);
  const canReview = roles?.some(role => ["SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER", "SAFETY_OFFICER"].includes(role));
  const [decision, setDecision] = useState("resolve");
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState("");
  const [failedImage, setFailedImage] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const detail = useQuery({
    queryKey: ["alert-detail", id], retry: false, refetchInterval: 15000,
    queryFn: async () => (await api.get(`/alerts/${id}`)).data.data as Incident,
  });
  const incident = detail.isError ? undefined : detail.data;
  const evidence = useQuery({
    queryKey: ["incident-evidence", incident?.violation_id], enabled: !!incident?.violation_id, retry: false,
    queryFn: async () => (await api.get(`/violations/${incident!.violation_id}`)).data.data as Evidence,
  });
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["alerts"] }),
      client.invalidateQueries({ queryKey: ["alert-detail", id] }),
      client.invalidateQueries({ queryKey: ["incident-evidence"] }),
      client.invalidateQueries({ queryKey: ["violations"] }),
      client.invalidateQueries({ queryKey: ["open-alert-counts"] }),
      client.invalidateQueries({ queryKey: ["recent-violations"] }),
      client.invalidateQueries({ queryKey: ["corrective-action", id] }),
    ]);
  };
  const review = useMutation({
    mutationFn: ({ action, comment }: { action: string; comment: string }) => api.patch(`/alerts/${id}/${action}`,
      action === "false-positive" ? { reason: comment } : action === "resolve" ? { note: comment } : {}),
    onSuccess: async (_response, variables) => {
      setSaved(variables.action === "acknowledge" ? "Incident acknowledged." : "Review saved.");
      setNote("");
      await refresh();
    },
    onError: async () => { setSaved(""); await refresh(); },
  });
  const active = incident && ["Open", "Acknowledged"].includes(incident.status);
  const maxLength = decision === "false-positive" ? 200 : 2000;
  const busy = review.isPending || detail.isFetching;
  const conflict = isAxiosError(review.error) && [409, 422].includes(review.error.response?.status ?? 0);
  const snapshot = evidence.isError ? null : evidence.data?.snapshot_url;

  return <Dialog open onClose={() => { if (!review.isPending) onClose(); }} fullWidth maxWidth="md" aria-labelledby="incident-review-title">
    <DialogTitle id="incident-review-title">Review incident{incident ? ` · ${incident.alert_number}` : ""}</DialogTitle>
    <DialogContent dividers>
      <Stack spacing={2}>
        {detail.isLoading && <Typography role="status">Loading incident…</Typography>}
        {detail.isError && <Alert severity="error">Incident could not be loaded. It may no longer be accessible. Refresh to try again.</Alert>}
        {review.isError && <Alert severity="error">{conflict ? "The review was not accepted. The current status has been refreshed; check it and your note before retrying." : "Could not confirm that the review was saved. Check the refreshed status before retrying."}</Alert>}
        {saved && <Alert severity="success">{saved}</Alert>}
        {incident && <>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <SeverityChip severity={incident.severity} /><StatusChip status={incident.status} />
            <Typography>{incident.alert_type.replace("PPE_VIOLATION_", "").replace(/_/g, " ")}</Typography>
          </Stack>
          <Typography>{[incident.factory_name, incident.zone_name, incident.camera_name].filter(Boolean).join(" · ") || "Location unavailable"}</Typography>
          <Typography variant="body2">Created: {date(incident.created_on)}</Typography>
          <Typography variant="body2" color={active && incident.sla_due_at && Date.parse(incident.sla_due_at) < Date.now() ? "error" : "text.secondary"}>
            SLA deadline: {date(incident.sla_due_at)}{active && incident.sla_due_at && Date.parse(incident.sla_due_at) < Date.now() ? " · Overdue" : ""}
          </Typography>
          <Divider />
          <Typography variant="h6">Evidence</Typography>
          {!incident.violation_id && <Typography color="text.secondary">This incident has no linked violation snapshot.</Typography>}
          {incident.violation_id && evidence.isLoading && <Typography role="status">Loading evidence…</Typography>}
          {incident.violation_id && evidence.isError && <Alert severity="warning">Evidence could not be loaded. Refresh to retry; do not treat missing evidence as confirmation.</Alert>}
          {incident.violation_id && !evidence.isError && evidence.data && <>
            <Typography variant="body2">Detected: {date(evidence.data.created_on)} · Model confidence: {(evidence.data.confidence * 100).toFixed(0)}%</Typography>
            <Typography variant="body2" color="text.secondary">Model confidence does not confirm a violation. Review the evidence and context before deciding.</Typography>
            {snapshot && failedImage !== snapshot ? <Box component="img" src={snapshot} alt="Incident snapshot" referrerPolicy="no-referrer"
              onError={() => setFailedImage(snapshot)} sx={{ width: "100%", maxHeight: 440, objectFit: "contain", bgcolor: "background.default", borderRadius: 1 }} />
              : <Alert severity="info">{snapshot ? "Snapshot unavailable or expired. Refresh evidence to request it again." : "No snapshot was recorded for this incident."}</Alert>}
          </>}
          <Divider />
          <CorrectiveAction id={id} active={!!active} canReview={!!canReview} onPendingChange={setActionPending} refreshIncident={refresh} />
          <Divider />
          <Typography variant="h6">Review history</Typography>
          <Typography variant="body2">Created · {date(incident.created_on)}</Typography>
          {(incident.review_history ?? []).map(entry => <Box key={entry.id} sx={{ borderLeft: "3px solid", borderColor: "divider", pl: 2 }}>
            <Typography variant="body2" fontWeight={600}>{entry.event_type && entry.event_type !== "STATUS_CHANGED"
              ? entry.event_type.replace(/_/g, " ").toLowerCase() : `${label(entry.from_status)} → ${label(entry.to_status)}`}</Typography>
            <Typography variant="caption" color="text.secondary">{entry.reviewer_name || "Reviewer unavailable"} · {date(entry.created_on)}</Typography>
            {entry.comment && <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{entry.comment}</Typography>}
            {entry.details?.description && <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{entry.details.description}</Typography>}
          </Box>)}
          {!incident.review_history?.length && <Typography variant="body2" color="text.secondary">No status changes recorded.</Typography>}
          {!canReview && <Alert severity="info">You have read-only access to incident reviews.</Alert>}
          {canReview && active && <>
            <Divider />
            {actionPending && <Alert severity="info">Save or discard plan edits and complete any planned corrective action before resolving this incident.</Alert>}
            <TextField select label="Review decision" value={decision} disabled={review.isPending}
              onChange={event => { setDecision(event.target.value); review.reset(); setSaved(""); }}>
              <MenuItem value="resolve">Resolve incident</MenuItem><MenuItem value="false-positive">Mark as false positive</MenuItem>
            </TextField>
            <TextField label={decision === "false-positive" ? "False-positive reason" : "Resolution note"} required multiline minRows={3}
              value={note} disabled={review.isPending} onChange={event => setNote(event.target.value)}
              error={note.trim().length > maxLength} helperText={`${note.trim().length}/${maxLength} characters. Describe what you checked and why you chose this outcome.`} />
            <Stack direction="row" spacing={1}>
              {incident.status === "Open" && <Button disabled={busy} onClick={() => review.mutate({ action: "acknowledge", comment: "" })}>Acknowledge</Button>}
              <Button variant="contained" disabled={busy || !note.trim() || note.trim().length > maxLength || (decision === "resolve" && actionPending)}
                onClick={() => review.mutate({ action: decision, comment: note.trim() })}>{review.isPending ? "Saving…" : "Save review"}</Button>
            </Stack>
          </>}
        </>}
      </Stack>
    </DialogContent>
    <DialogActions>
      <Button disabled={review.isPending || detail.isFetching || evidence.isFetching} onClick={() => { setFailedImage(null); void refresh(); }}>Refresh evidence</Button>
      <Button disabled={review.isPending} onClick={onClose}>Close</Button>
    </DialogActions>
  </Dialog>;
}
