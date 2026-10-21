import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Table, TableBody, TableCell, TableHead, TablePagination, TableRow, Typography } from "@mui/material";
import { Link } from "react-router-dom";
import { api } from "../api/client";

type Preview = { valid: boolean; preview_token: string | null; rows: { row: number; name: string; code: string; zone_name: string | null; factory_name: string | null; errors: string[] }[] };

export function CameraImportDialog({ onClose }: { onClose: () => void }) {
  const queries = useQueryClient();
  const [csvText, setCsvText] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [requestKey, setRequestKey] = useState("");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [zonePage, setZonePage] = useState(0);
  const zones = useQuery({ queryKey: ["zones"], queryFn: async () => (await api.get("/zones")).data.data as any[] });

  const pick = async (file: File | undefined) => {
    setPreview(null); setResult(null); setCsvText(""); setRequestKey(""); setError(""); setUncertain(false);
    if (!file) return;
    if (file.size > 512 * 1024) { setError("Choose a CSV smaller than 512 KiB, with at most 200 cameras."); return; }
    setBusy(true);
    try { setCsvText(new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer())); }
    catch { setError("The file must use UTF-8 encoding."); }
    finally { setBusy(false); }
  };
  const check = async () => {
    setBusy(true); setError(""); setPreview(null);
    try {
      const response = await api.post("/cameras/import/preview", { csv_text: csvText });
      setPreview(response.data.data); setRequestKey(crypto.randomUUID());
    } catch (err: any) { setError(err?.response?.data?.error?.message ?? "Preview failed. Retry or check the CSV."); }
    finally { setBusy(false); }
  };
  const save = async () => {
    setBusy(true); setError("");
    try {
      const response = await api.post("/cameras/import/commit", { csv_text: csvText, preview_token: preview?.preview_token, request_key: requestKey });
      setResult(response.data.data); setCsvText(""); setPreview(null); setUncertain(false);
      void queries.invalidateQueries({ queryKey: ["cameras"] });
      void queries.invalidateQueries({ queryKey: ["detection-health"] });
    } catch (err: any) {
      const status = err?.response?.status;
      setUncertain(!status || status >= 500);
      setError(err?.response?.data?.error?.message ?? "Import could not be confirmed. Retry this import to recover its result.");
      if (status === 409) setPreview(null);
    } finally { setBusy(false); }
  };
  const template = () => {
    const url = URL.createObjectURL(new Blob(["name,code,zone_id,rtsp_url,factory_id,fps,camera_type,position_desc\r\n"], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = "camera-import-template.csv"; link.click(); URL.revokeObjectURL(url);
  };
  return <Dialog open onClose={busy ? undefined : onClose} fullWidth maxWidth="lg">
    <DialogTitle>Import cameras from CSV</DialogTitle>
    <DialogContent dividers><Stack spacing={2}>
      <Typography>Import up to 200 cameras per batch. Cameras stay inactive and unassigned until you activate them. Test connections and review detection health after registration.</Typography>
      <Alert severity="info">CSV files can contain camera passwords. Keep the file private. URLs and credentials are omitted from the preview.</Alert>
      {error && <Alert severity="error">{error}</Alert>}
      {uncertain && <Alert severity="warning">The server may have saved this batch. Use Retry import before closing this dialog. Closing discards the retry key; previewing the same CSV again will flag already registered cameras.</Alert>}
      {!result && <Stack direction="row" spacing={2}>
        <Button onClick={template}>Download CSV template</Button>
        <Button component="label" disabled={busy || uncertain}>Choose CSV<input aria-label="Camera CSV file" hidden type="file" accept=".csv,text/csv" onChange={e => { void pick(e.target.files?.[0]); e.target.value = ""; }} /></Button>
        <Button onClick={check} disabled={busy || !csvText || uncertain}>Preview CSV</Button>
      </Stack>}
      {!result && <details><summary>Available zone IDs for your CSV</summary>
        {zones.isError ? <Alert severity="error">Zone list unavailable. Refresh before choosing a mapping.</Alert> : <>
          <Table size="small"><TableHead><TableRow><TableCell>Factory / zone</TableCell><TableCell>Zone ID</TableCell><TableCell>Factory ID (optional)</TableCell></TableRow></TableHead>
            <TableBody>{zones.data?.slice(zonePage * 20, zonePage * 20 + 20).map(zone => <TableRow key={zone.id}><TableCell>{zone.factory_name} / {zone.name}</TableCell><TableCell>{zone.id}</TableCell><TableCell>{zone.factory_id}</TableCell></TableRow>)}</TableBody></Table>
          <TablePagination component="div" count={zones.data?.length ?? 0} page={zonePage} rowsPerPage={20} rowsPerPageOptions={[20]} onPageChange={(_, page) => setZonePage(page)} />
        </>}
      </details>}
      {preview && <>
        <Alert severity={preview.valid ? "success" : "error"}>{preview.valid ? `${preview.rows.length} cameras validated. Preview expires after 10 minutes.` : "Fix every row error and preview again. No cameras have been imported."}</Alert>
        <Table size="small"><TableHead><TableRow><TableCell>Row</TableCell><TableCell>Camera / code</TableCell><TableCell>Factory / zone</TableCell><TableCell>Validation</TableCell></TableRow></TableHead><TableBody>
          {preview.rows.map(row => <TableRow key={row.row}><TableCell>{row.row}</TableCell><TableCell>{row.name} / {row.code}</TableCell><TableCell>{row.factory_name} / {row.zone_name}</TableCell><TableCell>{row.errors.join("; ") || "Ready"}</TableCell></TableRow>)}
        </TableBody></Table>
      </>}
      {result && <>
        <Alert severity="success">{result.cameras.length} cameras registered{result.replayed ? " (previous result recovered)" : ""}. Registration does not confirm connectivity or detection.</Alert>
        <Typography>Open Cameras to test each connection and activate when ready. Worker admission depends on factory capacity; Detection health confirms fresh inference separately.</Typography>
        <Button component={Link} to="/detection-health" onClick={onClose}>Review detection health</Button>
      </>}
    </Stack></DialogContent>
    <DialogActions><Button disabled={busy} onClick={onClose}>{result ? "Done" : "Close"}</Button>
      {!result && <Button variant="contained" disabled={busy || !preview?.valid} onClick={save}>{busy ? "Working..." : uncertain ? "Retry import" : "Import inactive cameras"}</Button>}
    </DialogActions>
  </Dialog>;
}
