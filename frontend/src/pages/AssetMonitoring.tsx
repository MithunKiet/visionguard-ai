import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import AddIcon from "@mui/icons-material/Add";
import {
  Alert, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControlLabel, Paper, Stack,
  Switch, Table, TableBody, TableCell, TableHead, TablePagination, TableRow, TextField, Typography,
} from "@mui/material";
import { api } from "../api/client";
import { useAuthStore } from "../store/authStore";
import { AuthImage } from "../components/AuthImage";
import { RoiEditor, roiValid, type Roi } from "../components/RoiEditor";
import { SearchableSelect } from "../components/SearchableSelect";
import { ASSET_TYPES, assetTypeLabel } from "../components/assetTypes";

interface SafetyAsset {
  id: string; asset_code: string; asset_type: string; name: string; location_desc: string | null;
  zone_name: string; camera_id: string; camera_name: string; roi: Roi | null;
  has_reference: boolean; reference_captured_at: string | null;
  check_interval_seconds: number; change_after_seconds: number; similarity_threshold: number;
  monitoring_enabled: boolean; monitoring_status: string; last_similarity: number | null; last_checked_at: string | null;
  version: number; open_incident?: AssetIncident | null;
}

interface AssetIncident {
  id: string; kind: string; similarity: number | null; has_snapshot: boolean; detected_at: string; cleared_at: string | null;
  alert_number: string | null; alert_status: string | null;
}

const PAGE_SIZE = 50;
const MANAGE_ROLES = ["SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER"];
const STATUS: Record<string, { label: string; color: "success" | "error" | "warning" | "info" | "default" }> = {
  OK: { label: "Area matches reference", color: "success" },
  Changed: { label: "Area changed", color: "error" },
  ViewChanged: { label: "Camera view changed", color: "warning" },
  Occluded: { label: "Blocked by a person", color: "info" },
  Unconfirmed: { label: "Not confirmed by a worker", color: "warning" },
  NotConfigured: { label: "Not configured", color: "default" },
  Disabled: { label: "Monitoring off", color: "default" },
};
const KIND: Record<string, string> = { AREA_CHANGED: "Area changed", VIEW_CHANGED: "Camera view changed" };
const date = (value: string | null) => value ? new Date(value).toLocaleString() : "—";
const message = (error: any, fallback: string) => error?.response?.data?.error?.message ?? fallback;

export function StatusChip({ status }: { status: string }) {
  const entry = STATUS[status] ?? { label: status, color: "default" as const };
  return <Chip size="small" label={entry.label} color={entry.color} />;
}

export function AssetMonitoring() {
  const canManage = useAuthStore(s => s.user?.roles.some(role => MANAGE_ROLES.includes(role)));
  const [page, setPage] = useState(0);
  const [addOpen, setAddOpen] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["safety-assets", page],
    queryFn: async () => {
      const response = await api.get("/safety-assets", { params: { page: page + 1, page_size: PAGE_SIZE } });
      return { rows: response.data.data as SafetyAsset[], total: response.data.meta?.total ?? 0 };
    },
    refetchInterval: 15000,
  });
  const total = isError ? 0 : data?.total ?? 0;
  useEffect(() => {
    if (data && page > 0 && page * PAGE_SIZE >= data.total) setPage(Math.max(0, Math.ceil(data.total / PAGE_SIZE) - 1));
  }, [data, page]);

  return <Stack spacing={3}>
    <Stack direction="row" justifyContent="space-between" alignItems="center">
      <Typography variant="h5" fontWeight={700}>Asset Monitoring</Typography>
      {canManage && <Button variant="contained" startIcon={<AddIcon />} onClick={() => setAddOpen(true)}>Add asset</Button>}
    </Stack>
    <Alert severity="info">
      Each asset (fire extinguisher, dustbin, first-aid box…) is checked against its reference photo. Monitoring reports
      that its area changed; it cannot tell whether the asset is missing, moved or blocked. Review the evidence photo
      before acting. Accuracy on your cameras has not been measured.
    </Alert>
    {isError && <Alert severity="error" action={<Button onClick={() => refetch()}>Retry</Button>}>Assets unavailable. Previous results are hidden.</Alert>}
    <Paper variant="outlined">
      <Table>
        <TableHead><TableRow>
          <TableCell>Code</TableCell><TableCell>Type</TableCell><TableCell>Name</TableCell><TableCell>Zone · Camera</TableCell>
          <TableCell>Status</TableCell><TableCell>Last check</TableCell><TableCell>Open incident</TableCell><TableCell align="right">Actions</TableCell>
        </TableRow></TableHead>
        <TableBody>
          {(!isError ? data?.rows ?? [] : []).map(asset => <TableRow key={asset.id} hover>
            <TableCell>{asset.asset_code}</TableCell>
            <TableCell>{assetTypeLabel(asset.asset_type)}</TableCell>
            <TableCell>{asset.name}{asset.location_desc && <Typography variant="caption" display="block">{asset.location_desc}</Typography>}</TableCell>
            <TableCell>{asset.zone_name} · {asset.camera_name}</TableCell>
            <TableCell><StatusChip status={asset.monitoring_status} /></TableCell>
            <TableCell>{date(asset.last_checked_at)}</TableCell>
            <TableCell>{asset.open_incident ? `${KIND[asset.open_incident.kind] ?? asset.open_incident.kind} since ${date(asset.open_incident.detected_at)}` : "None"}</TableCell>
            <TableCell align="right"><Button size="small" onClick={() => setSelected(asset.id)}>{canManage ? "Configure" : "View"}</Button></TableCell>
          </TableRow>)}
          {!isLoading && !isError && (data?.rows ?? []).length === 0 && <TableRow><TableCell colSpan={8}>
            <Typography variant="body2" color="text.secondary">No monitored assets registered in your scope.</Typography>
          </TableCell></TableRow>}
        </TableBody>
      </Table>
      <TablePagination component="div" count={total} page={Math.min(page, Math.max(0, Math.ceil(total / PAGE_SIZE) - 1))}
        rowsPerPage={PAGE_SIZE} rowsPerPageOptions={[PAGE_SIZE]} onPageChange={(_, next) => setPage(next)} />
    </Paper>
    {addOpen && <AddAssetDialog onClose={() => setAddOpen(false)} onCreated={id => { setAddOpen(false); setSelected(id); }} />}
    {selected && <AssetDialog id={selected} canManage={!!canManage} onClose={() => setSelected(null)} />}
  </Stack>;
}

function AddAssetDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const client = useQueryClient();
  const [form, setForm] = useState({ asset_type: "FIRE_EXTINGUISHER", camera_id: "", asset_code: "", name: "", location_desc: "" });
  const typeLabel = assetTypeLabel(form.asset_type).toLowerCase();
  const cameras = useQuery({ queryKey: ["cameras-for-assets"], queryFn: async () => (await api.get("/cameras")).data.data as any[] });
  const create = useMutation({
    mutationFn: async () => (await api.post("/safety-assets", { ...form, location_desc: form.location_desc || null })).data.data as SafetyAsset,
    onSuccess: async asset => { await client.invalidateQueries({ queryKey: ["safety-assets"] }); onCreated(asset.id); },
  });
  const ready = form.camera_id && form.asset_code.trim() && form.name.trim();
  return <Dialog open onClose={() => { if (!create.isPending) onClose(); }} fullWidth maxWidth="sm">
    <DialogTitle>Add asset</DialogTitle>
    <DialogContent dividers>
      <Stack spacing={2}>
        {create.isError && <Alert severity="error">{message(create.error, "The asset could not be saved.")}</Alert>}
        {cameras.isError && <Alert severity="error">Cameras could not be loaded.</Alert>}
        <TextField select label="Asset type" required value={form.asset_type} SelectProps={{ native: true }}
          onChange={e => setForm({ ...form, asset_type: e.target.value })}>
          {Object.entries(ASSET_TYPES).map(([value, type]) => <option key={value} value={value}>{type.label}</option>)}
        </TextField>
        <SearchableSelect label={`Camera that sees this ${typeLabel}`} required value={form.camera_id}
          options={(cameras.data ?? []).map(c => ({ id: c.id, label: `${c.name} (${c.code})` }))}
          onChange={camera_id => setForm({ ...form, camera_id })} />
        <TextField label="Asset code" required placeholder={`${ASSET_TYPES[form.asset_type]?.codePrefix ?? "AS"}-001`} value={form.asset_code}
          inputProps={{ maxLength: 50 }} onChange={e => setForm({ ...form, asset_code: e.target.value })} />
        <TextField label="Name" required placeholder={`${assetTypeLabel(form.asset_type)}, welding bay`} value={form.name} inputProps={{ maxLength: 200 }}
          onChange={e => setForm({ ...form, name: e.target.value })} />
        <TextField label="Location description" value={form.location_desc} inputProps={{ maxLength: 300 }}
          onChange={e => setForm({ ...form, location_desc: e.target.value })} />
        <Typography variant="body2" color="text.secondary">Monitoring starts only after you capture a reference photo, mark the {typeLabel} and turn monitoring on.</Typography>
      </Stack>
    </DialogContent>
    <DialogActions>
      <Button disabled={create.isPending} onClick={onClose}>Cancel</Button>
      <Button variant="contained" disabled={!ready || create.isPending} onClick={() => create.mutate()}>{create.isPending ? "Saving…" : "Save"}</Button>
    </DialogActions>
  </Dialog>;
}

function AssetDialog({ id, canManage, onClose }: { id: string; canManage: boolean; onClose: () => void }) {
  const client = useQueryClient();
  const detail = useQuery({ queryKey: ["safety-asset", id], refetchInterval: 15000,
    queryFn: async () => (await api.get(`/safety-assets/${id}`)).data.data as SafetyAsset });
  const incidents = useQuery({ queryKey: ["safety-asset-incidents", id], refetchInterval: 15000,
    queryFn: async () => (await api.get(`/safety-assets/${id}/incidents`)).data.data as AssetIncident[] });
  const asset = detail.data;
  const [draft, setDraft] = useState<{ roi: Roi | null; check_interval_seconds: number; change_after_seconds: number; similarity_threshold: number; monitoring_enabled: boolean } | null>(null);
  const [evidence, setEvidence] = useState<string | null>(null);
  const [saved, setSaved] = useState("");
  useEffect(() => {
    // Seed edits once per loaded version; background refreshes must not overwrite typing.
    if (asset && (!draft || !dirty)) setDraft({ roi: asset.roi, check_interval_seconds: asset.check_interval_seconds,
      change_after_seconds: asset.change_after_seconds, similarity_threshold: asset.similarity_threshold, monitoring_enabled: asset.monitoring_enabled });
  }, [asset?.version]); // eslint-disable-line react-hooks/exhaustive-deps
  const dirty = !!asset && !!draft && JSON.stringify(draft) !== JSON.stringify({ roi: asset.roi, check_interval_seconds: asset.check_interval_seconds,
    change_after_seconds: asset.change_after_seconds, similarity_threshold: asset.similarity_threshold, monitoring_enabled: asset.monitoring_enabled });
  const refresh = () => Promise.all([client.invalidateQueries({ queryKey: ["safety-asset", id] }),
    client.invalidateQueries({ queryKey: ["safety-assets"] }), client.invalidateQueries({ queryKey: ["safety-asset-incidents", id] })]);
  const capture = useMutation({
    mutationFn: async () => (await api.post(`/safety-assets/${id}/reference`)).data.data as SafetyAsset,
    onMutate: () => setSaved(""),
    onSuccess: async () => { setSaved("Reference photo captured. Check the marked area still covers the asset."); setDraft(null); await refresh(); },
  });
  const save = useMutation({
    mutationFn: async () => {
      // Send only edited fields: an unchanged area must not re-version the worker policy.
      const changes = Object.fromEntries(Object.entries(draft!).filter(([key, value]) =>
        JSON.stringify(value) !== JSON.stringify(asset![key as keyof SafetyAsset])));
      return (await api.put(`/safety-assets/${id}`, { version: asset!.version, ...changes })).data.data as SafetyAsset;
    },
    onMutate: () => setSaved(""),
    onSuccess: async () => { setSaved("Saved. A worker must confirm the new settings before status updates."); setDraft(null); await refresh(); },
    onError: async () => { await refresh(); },
  });
  const busy = capture.isPending || save.isPending;
  const referencePath = asset?.has_reference ? `/safety-assets/${id}/reference?captured=${encodeURIComponent(asset.reference_captured_at ?? "")}` : null;
  const canMonitor = !!asset?.has_reference && roiValid(draft?.roi ?? null);

  return <Dialog open onClose={() => { if (!busy) onClose(); }} fullWidth maxWidth="md">
    <DialogTitle>{asset ? `${asset.asset_code} · ${assetTypeLabel(asset.asset_type)} · ${asset.name}` : "Monitored asset"}</DialogTitle>
    <DialogContent dividers>
      <Stack spacing={2}>
        {detail.isLoading && <Typography role="status">Loading asset…</Typography>}
        {detail.isError && <Alert severity="error">The asset could not be loaded. It may have been removed or be outside your access.</Alert>}
        {capture.isError && <Alert severity="error">{message(capture.error, "The reference photo could not be captured.")}</Alert>}
        {save.isError && <Alert severity="error">{message(save.error, "The changes could not be saved.")} The latest values have been reloaded.</Alert>}
        {saved && <Alert severity="success">{saved}</Alert>}
        {asset && draft && <>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <StatusChip status={asset.monitoring_status} />
            <Typography variant="body2">{asset.zone_name} · {asset.camera_name}</Typography>
            <Typography variant="body2" color="text.secondary">Last check: {date(asset.last_checked_at)}
              {asset.last_similarity != null && ` · similarity ${(asset.last_similarity * 100).toFixed(0)}%`}</Typography>
          </Stack>
          <Divider />
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="h6">Reference photo and asset area</Typography>
            {canManage && <Button disabled={busy} onClick={() => capture.mutate()}>{capture.isPending ? "Capturing…" : asset.has_reference ? "Recapture from camera" : "Capture from camera"}</Button>}
          </Stack>
          <Typography variant="body2" color="text.secondary">
            Capture when the {assetTypeLabel(asset.asset_type).toLowerCase()} is in its proper place, nothing blocks it and lighting is normal. Reference captured: {date(asset.reference_captured_at)}
          </Typography>
          <RoiEditor imagePath={referencePath} value={draft.roi} disabled={!canManage || busy} onChange={roi => setDraft({ ...draft, roi })} />
          <Divider />
          <Typography variant="h6">Checks</Typography>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField label="Check every (seconds)" type="number" disabled={!canManage || busy} value={draft.check_interval_seconds}
              inputProps={{ min: 10, max: 3600 }} onChange={e => setDraft({ ...draft, check_interval_seconds: Number(e.target.value) })} />
            <TextField label="Alert after change lasts (seconds)" type="number" disabled={!canManage || busy} value={draft.change_after_seconds}
              inputProps={{ min: 30, max: 86400 }} onChange={e => setDraft({ ...draft, change_after_seconds: Number(e.target.value) })} />
            <TextField label="Similarity threshold" type="number" disabled={!canManage || busy} value={draft.similarity_threshold}
              inputProps={{ min: 0.05, max: 0.95, step: 0.05 }} helperText="Below this the area counts as changed"
              onChange={e => setDraft({ ...draft, similarity_threshold: Number(e.target.value) })} />
          </Stack>
          <FormControlLabel control={<Switch checked={draft.monitoring_enabled} disabled={!canManage || busy || (!canMonitor && !draft.monitoring_enabled)}
            onChange={e => setDraft({ ...draft, monitoring_enabled: e.target.checked })} />}
            label={canMonitor || draft.monitoring_enabled ? "Monitoring on" : "Monitoring on (capture a reference photo and mark the area first)"} />
          <Divider />
          <Typography variant="h6">Incidents</Typography>
          {incidents.isError && <Alert severity="warning">Incidents could not be loaded.</Alert>}
          {(incidents.data ?? []).length === 0 && !incidents.isError && <Typography variant="body2" color="text.secondary">No incidents recorded.</Typography>}
          {(incidents.data ?? []).length > 0 && <Table size="small">
            <TableHead><TableRow><TableCell>Detected</TableCell><TableCell>Kind</TableCell><TableCell>Similarity</TableCell>
              <TableCell>Cleared</TableCell><TableCell>Alert</TableCell><TableCell /></TableRow></TableHead>
            <TableBody>{incidents.data!.map(incident => <TableRow key={incident.id}>
              <TableCell>{date(incident.detected_at)}</TableCell><TableCell>{KIND[incident.kind] ?? incident.kind}</TableCell>
              <TableCell>{incident.similarity == null ? "—" : `${(incident.similarity * 100).toFixed(0)}%`}</TableCell>
              <TableCell>{incident.cleared_at ? date(incident.cleared_at) : "Not cleared"}</TableCell>
              <TableCell>{incident.alert_number ? `${incident.alert_number} (${incident.alert_status})` : "No alert (maintenance)"}</TableCell>
              <TableCell>{incident.has_snapshot && <Button size="small" onClick={() => setEvidence(evidence === incident.id ? null : incident.id)}>
                {evidence === incident.id ? "Hide evidence" : "Evidence"}</Button>}</TableCell>
            </TableRow>)}</TableBody>
          </Table>}
          {evidence && <AuthImage path={`/safety-assets/${id}/incidents/${evidence}/snapshot`} alt="Incident evidence" />}
        </>}
      </Stack>
    </DialogContent>
    <DialogActions>
      <Button disabled={busy} onClick={onClose}>Close</Button>
      {canManage && asset && <Button variant="contained" disabled={busy || !dirty || (draft?.monitoring_enabled && !canMonitor) || (!!draft?.roi && !roiValid(draft.roi))}
        onClick={() => save.mutate()}>{save.isPending ? "Saving…" : "Save changes"}</Button>}
    </DialogActions>
  </Dialog>;
}
