import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { api } from "../api/client";

async function fetchViolations() {
  const resp = await api.get("/violations", { params: { page_size: 100 } });
  return resp.data.data as any[];
}

export function Violations() {
  const [preview, setPreview] = useState<string | null>(null);

  const { data: violations, isLoading } = useQuery({
    queryKey: ["violations"],
    queryFn: fetchViolations,
    refetchInterval: 20000,
  });

  return (
    <Stack spacing={3}>
      <Typography variant="h5" fontWeight={700}>
        Violations
      </Typography>

      <Paper variant="outlined">
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Type</TableCell>
              <TableCell>Confidence</TableCell>
              <TableCell>Needs Review</TableCell>
              <TableCell>Detected</TableCell>
              <TableCell>Snapshot</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(violations ?? []).map((v) => (
              <TableRow key={v.id} hover>
                <TableCell sx={{ textTransform: "capitalize" }}>{v.violation_type.replace("_", " ")}</TableCell>
                <TableCell>{(v.confidence * 100).toFixed(0)}%</TableCell>
                <TableCell>{v.needs_review ? "Yes" : "No"}</TableCell>
                <TableCell>{new Date(v.created_on).toLocaleString()}</TableCell>
                <TableCell>
                  {v.snapshot_url ? (
                    <img
                      src={v.snapshot_url}
                      alt="snapshot"
                      style={{ height: 40, borderRadius: 4, cursor: "pointer" }}
                      onClick={() => setPreview(v.snapshot_url)}
                    />
                  ) : (
                    "-"
                  )}
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && (violations ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>
                  <Typography variant="body2" color="text.secondary">
                    No violations recorded yet.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>

      <Dialog open={!!preview} onClose={() => setPreview(null)} maxWidth="md">
        <DialogContent>
          {preview && <img src={preview} alt="violation snapshot" style={{ maxWidth: "100%" }} />}
        </DialogContent>
      </Dialog>
    </Stack>
  );
}
