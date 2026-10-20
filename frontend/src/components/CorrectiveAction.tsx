import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Box, Button, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { api } from "../api/client";
import { useAuthStore } from "../store/authStore";

interface ActionState {
  revision: number; plan_version: number; description: string | null; assigned_to: string | null;
  assignee_name: string | null; assignee_active: boolean; due_at: string | null; completed_at: string | null;
  status: string; overdue: boolean;
  evidence: { id: string; filename: string; sha256: string; current_plan: boolean; plan_version: number }[];
}
const localTime = (value: string) => {
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};

export function CorrectiveAction({ id, active, canReview, onPendingChange, refreshIncident }: {
  id: string; active: boolean; canReview: boolean; onPendingChange: (pending: boolean) => void; refreshIncident: () => Promise<void>;
}) {
  const client = useQueryClient();
  const user = useAuthStore(state => state.user);
  const [description, setDescription] = useState("");
  const [owner, setOwner] = useState("");
  const [due, setDue] = useState("");
  const [dirty, setDirty] = useState(false);
  const [baseRevision, setBaseRevision] = useState(0);
  const [search, setSearch] = useState("");
  const [candidatePage, setCandidatePage] = useState(1);
  const [completionNote, setCompletionNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const uploadKey = useRef(crypto.randomUUID());
  const photoInput = useRef<HTMLInputElement | null>(null);
  const [notice, setNotice] = useState("");
  const [preview, setPreview] = useState<{ id: string; url: string } | null>(null);
  const mounted = useRef(true);
  const photoRequest = useRef<AbortController | null>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; photoRequest.current?.abort(); }; }, []);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview.url); }, [preview]);

  const action = useQuery({ queryKey: ["corrective-action", id], retry: false, refetchInterval: 15000,
    queryFn: async ({ signal }) => {
      const data = (await api.get(`/alerts/${id}/corrective-action`, { signal })).data.data;
      if (typeof data?.revision !== "number") throw new Error("Corrective action is unavailable");
      return data as ActionState;
    } });
  const data = action.isError ? undefined : action.data;
  useEffect(() => {
    onPendingChange(dirty || (!!data?.description && !data.completed_at && data.status !== "Cancelled"));
    if (!data) { setPreview(null); return; }
    if (!dirty) {
      setDescription(data.description ?? ""); setOwner(data.assigned_to ?? "");
      setDue(data.due_at ? localTime(data.due_at) : ""); setBaseRevision(data.revision);
    }
  }, [data, dirty, onPendingChange]);

  const candidates = useQuery({ queryKey: ["incident-assignees", id, search, candidatePage], enabled: canReview && active && !!data,
    queryFn: async ({ signal }) => {
      const response = await api.get(`/alerts/${id}/assignees`, { params: { search, page: candidatePage, page_size: 20 }, signal });
      return { users: response.data.data as { id: string; name: string }[], totalPages: response.data.meta.total_pages as number };
    } });
  const refresh = refreshIncident;
  const plan = useMutation({
    mutationFn: () => api.put(`/alerts/${id}/corrective-action`, { assigned_to: owner, due_at: new Date(due).toISOString(), description: description.trim(), expected_revision: baseRevision }),
    onSuccess: async response => { setDirty(false); setNotice("Corrective plan saved."); client.setQueryData(["corrective-action", id], response.data.data); await refresh(); },
    onError: async () => { setNotice(""); await refresh(); },
  });
  const upload = useMutation({
    mutationFn: () => {
      const body = new FormData(); body.append("file", file!); body.append("expected_revision", String(data!.revision)); body.append("upload_id", uploadKey.current);
      return api.post(`/alerts/${id}/corrective-action/evidence`, body);
    },
    onSuccess: async () => { setFile(null); if (photoInput.current) photoInput.current.value = ""; uploadKey.current = crypto.randomUUID(); setNotice("Corrective photo attached."); await refresh(); },
    onError: async () => { setNotice(""); await refresh(); },
  });
  const complete = useMutation({
    mutationFn: () => api.post(`/alerts/${id}/corrective-action/complete`, { expected_revision: data!.revision, note: completionNote.trim() }),
    onSuccess: async () => { setCompletionNote(""); setNotice("Corrective action completed. Record the final incident review to close it."); await refresh(); },
    onError: async () => { setNotice(""); await refresh(); },
  });
  const photo = useMutation({ mutationFn: async (evidenceId: string) => {
    setPreview(null);
    photoRequest.current?.abort(); const controller = new AbortController(); photoRequest.current = controller;
    const response = await api.get(`/alerts/${id}/corrective-action/evidence/${evidenceId}`, { responseType: "blob", signal: controller.signal });
    if (mounted.current && !controller.signal.aborted) setPreview({ id: evidenceId, url: URL.createObjectURL(response.data) });
  } });
  const busy = plan.isPending || upload.isPending || complete.isPending;
  const error = (err: any) => err?.response?.data?.error?.message ?? err?.message ?? "The request could not be confirmed.";
  const available = candidates.isError ? [] : candidates.data?.users ?? [];
  const canComplete = user?.id === data?.assigned_to || user?.roles.some(role => ["SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER"].includes(role));
  return <Stack spacing={2}>
    <Typography variant="h6">Corrective action</Typography>
    {action.isError && <Alert severity="warning" action={<Button onClick={() => action.refetch()}>Refresh action</Button>}>Corrective action could not be loaded. Refresh before planning or attaching evidence.</Alert>}
    {action.isLoading && <Typography>Loading corrective action…</Typography>}
    {notice && <Alert severity="info">{notice}</Alert>}
    {[plan, upload, complete].filter(mutation => mutation.isError).map((mutation, index) => <Alert severity="error" key={index}>
      {error(mutation.error)} Check the refreshed action before retrying; drafts are retained.
    </Alert>)}
    {data && <>
      <Typography>Action status: {data.status}{data.overdue ? " · Overdue" : ""}</Typography>
      {data.description && <>
        <Typography sx={{ whiteSpace: "pre-wrap" }}>{data.description}</Typography>
        <Typography>Responsible person: {data.assignee_name ?? "Unavailable"}{!data.assignee_active ? " · Account unavailable" : ""}</Typography>
        <Typography color={data.overdue ? "error" : "text.secondary"}>Action due: {data.due_at ? new Date(data.due_at).toLocaleString() : "Not set"}</Typography>
      </>}
      {canReview && active && <>
        {dirty && baseRevision !== data.revision && <Alert severity="warning">The action changed while you were editing. Refresh your draft before saving.</Alert>}
        <TextField label="Corrective action plan" multiline minRows={2} value={description} disabled={busy} onChange={e => { setDirty(true); setDescription(e.target.value); }} helperText={`${description.trim().length}/2000 characters`} />
        <TextField label="Search responsible reviewers" value={search} disabled={busy} onChange={e => { setSearch(e.target.value); setCandidatePage(1); }} />
        {candidates.isError && <Alert severity="warning">Responsible reviewers could not be loaded.</Alert>}
        <TextField select label="Responsible person" value={owner} disabled={busy} onChange={e => { setDirty(true); setOwner(e.target.value); }}>
          <MenuItem value="">Choose a reviewer</MenuItem>
          {owner && !available.some(user => user.id === owner) && <MenuItem value={owner}>{data.assignee_name ?? "Current selection"}</MenuItem>}
          {available.map(user => <MenuItem key={user.id} value={user.id}>{user.name}</MenuItem>)}
        </TextField>
        <Stack direction="row" spacing={1}>
          <Button disabled={candidatePage === 1 || busy} onClick={() => setCandidatePage(p => p - 1)}>Previous reviewers</Button>
          <Button disabled={busy || candidatePage >= (candidates.data?.totalPages ?? 1)} onClick={() => setCandidatePage(p => p + 1)}>More reviewers</Button>
        </Stack>
        <TextField label="Action due date" type="datetime-local" value={due} disabled={busy} InputLabelProps={{ shrink: true }} onChange={e => { setDirty(true); setDue(e.target.value); }} />
        <Typography variant="caption">Editing a saved plan invalidates completion and requires photos attached to the new plan. Times use your browser timezone.</Typography>
        <Stack direction="row" spacing={1}>
          <Button disabled={busy || !dirty || !description.trim() || description.trim().length > 2000 || !owner || !due || action.isFetching}
            onClick={() => plan.mutate()}>Save corrective plan</Button>
          {dirty && <Button disabled={busy} onClick={() => setDirty(false)}>Discard plan draft</Button>}
        </Stack>
      </>}
      <Typography variant="subtitle2">Corrective photos</Typography>
      {data.evidence.map(item => <Stack key={item.id}>
        <Button disabled={photo.isPending} onClick={() => photo.mutate(item.id)}>View corrective photo: {item.filename}</Button>
        <Typography variant="caption">Plan {item.plan_version}{item.current_plan ? " · Current plan" : " · Earlier plan"}</Typography>
      </Stack>)}
      {!data.evidence.length && <Typography>No corrective photos attached.</Typography>}
      {photo.isError && <Alert severity="warning">Corrective photo could not be loaded. Check access and retry.</Alert>}
      {preview && data.evidence.some(item => item.id === preview.id) && <Box component="img" src={preview.url} alt="Corrective action photo" sx={{ maxHeight: 400, objectFit: "contain" }} />}
      {canReview && active && data.description && !data.completed_at && <>
        {dirty && <Alert severity="info">Save or discard plan edits before attaching photos or completing the action.</Alert>}
        <Typography variant="caption">Attach a JPEG or PNG photo up to 5 MiB and 20 megapixels. Original bytes are preserved.</Typography>
        <input ref={photoInput} aria-label="Corrective photo" type="file" accept="image/jpeg,image/png" disabled={busy || dirty} onChange={e => { setFile(e.target.files?.[0] ?? null); uploadKey.current = crypto.randomUUID(); }} />
        {file && file.size > 5 * 1024 * 1024 && <Alert severity="warning">The photo exceeds 5 MiB.</Alert>}
        <Button disabled={busy || dirty || !file || file.size > 5 * 1024 * 1024} onClick={() => upload.mutate()}>Attach corrective photo</Button>
        <TextField label="Corrective completion note" multiline value={completionNote} disabled={busy} onChange={e => setCompletionNote(e.target.value)} helperText={`${completionNote.trim().length}/2000 characters`} />
        {!canComplete && <Typography variant="caption">The responsible person or a scoped administrator/manager must complete this action.</Typography>}
        <Button disabled={busy || dirty || !canComplete || !completionNote.trim() || completionNote.trim().length > 2000 || !data.evidence.some(item => item.current_plan)}
          onClick={() => complete.mutate()}>Complete corrective action</Button>
      </>}
    </>}
  </Stack>;
}
