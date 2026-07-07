import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { api } from "../api/client";
import { AddFactoryDialog } from "../components/AddFactoryDialog";

async function fetchFactories() {
  const resp = await api.get("/factories");
  return resp.data.data as any[];
}

export function Factories() {
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);

  const { data: factories, isLoading } = useQuery({
    queryKey: ["factories"],
    queryFn: fetchFactories,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/factories/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["factories"] }),
  });

  return (
    <Stack spacing={3}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h5" fontWeight={700}>
          Factories
        </Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setAddOpen(true)}>
          Add Factory
        </Button>
      </Stack>

      <AddFactoryDialog open={addOpen} onClose={() => setAddOpen(false)} />

      <Paper variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow sx={{ "& th": { bgcolor: "background.default", fontWeight: 700 } }}>
              <TableCell>Name</TableCell>
              <TableCell>Code</TableCell>
              <TableCell>Location</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(factories ?? []).map((f) => (
              <TableRow key={f.id} hover>
                <TableCell sx={{ fontWeight: 600 }}>{f.name}</TableCell>
                <TableCell>{f.code}</TableCell>
                <TableCell>{f.location ?? "—"}</TableCell>
                <TableCell>
                  <Chip size="small" label={f.status} color={f.status === "Active" ? "success" : "default"} />
                </TableCell>
                <TableCell align="right">
                  <IconButton
                    size="small"
                    color="error"
                    disabled={deleteMutation.isPending}
                    onClick={() => deleteMutation.mutate(f.id)}
                    title="Delete factory"
                  >
                    <DeleteOutlineIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && (factories ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>
                  <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: "center" }}>
                    No factories yet.
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
