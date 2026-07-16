import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import AddIcon from "@mui/icons-material/Add";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { api } from "../api/client";
import { AddEnterpriseDialog } from "../components/AddEnterpriseDialog";

async function fetchEnterprises() {
  const resp = await api.get("/enterprises");
  return resp.data.data as any[];
}

export function Enterprises() {
  const [addOpen, setAddOpen] = useState(false);

  const { data: enterprises, isLoading } = useQuery({
    queryKey: ["enterprises"],
    queryFn: fetchEnterprises,
  });

  return (
    <Stack spacing={3}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Stack spacing={0.5}>
          <Typography variant="h5" fontWeight={700}>
            Enterprises
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Platform-wide client tenants — visible to Super Admins only.
          </Typography>
        </Stack>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setAddOpen(true)}>
          Onboard Enterprise
        </Button>
      </Stack>

      <AddEnterpriseDialog open={addOpen} onClose={() => setAddOpen(false)} />

      <Paper variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow sx={{ "& th": { bgcolor: "background.default", fontWeight: 700 } }}>
              <TableCell>Name</TableCell>
              <TableCell>Code</TableCell>
              <TableCell>Industry</TableCell>
              <TableCell>Contact</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Created</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(enterprises ?? []).map((e) => (
              <TableRow key={e.id} hover>
                <TableCell sx={{ fontWeight: 600 }}>{e.name}</TableCell>
                <TableCell>{e.code}</TableCell>
                <TableCell>{e.industry ?? "—"}</TableCell>
                <TableCell>
                  <Stack spacing={0}>
                    <Typography variant="body2">{e.contact_person ?? "—"}</Typography>
                    {e.contact_email && (
                      <Typography variant="caption" color="text.secondary">{e.contact_email}</Typography>
                    )}
                  </Stack>
                </TableCell>
                <TableCell>
                  <Chip size="small" label={e.status} color={e.status === "Active" ? "success" : "default"} />
                </TableCell>
                <TableCell>{e.created_at ? new Date(e.created_at).toLocaleDateString() : "—"}</TableCell>
              </TableRow>
            ))}
            {!isLoading && (enterprises ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: "center" }}>
                    No enterprises yet.
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
