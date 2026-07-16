import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
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
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { api } from "../api/client";
import { AddZoneDialog } from "../components/AddZoneDialog";
import { EditZonePpeDialog } from "../components/EditZonePpeDialog";
import { ManagePpeTypesDialog } from "../components/ManagePpeTypesDialog";
import { usePpeTypes } from "../components/ppeItems";

async function fetchZones() {
  const resp = await api.get("/zones");
  return resp.data.data as any[];
}

export function Zones() {
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [ppeZone, setPpeZone] = useState<{ id: string; name: string } | null>(null);
  const [manageTypesOpen, setManageTypesOpen] = useState(false);

  const { data: zones, isLoading } = useQuery({
    queryKey: ["zones"],
    queryFn: fetchZones,
  });

  const { data: ppeTypes } = usePpeTypes();

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/zones/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["zones"] }),
  });

  return (
    <Stack spacing={3}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h5" fontWeight={700}>
          Zones
        </Typography>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" startIcon={<SettingsOutlinedIcon />} onClick={() => setManageTypesOpen(true)}>
            Manage PPE Types
          </Button>
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setAddOpen(true)}>
            Add Zone
          </Button>
        </Stack>
      </Stack>

      <AddZoneDialog open={addOpen} onClose={() => setAddOpen(false)} />
      <EditZonePpeDialog open={!!ppeZone} onClose={() => setPpeZone(null)} zone={ppeZone} />
      <ManagePpeTypesDialog open={manageTypesOpen} onClose={() => setManageTypesOpen(false)} />

      <Paper variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow sx={{ "& th": { bgcolor: "background.default", fontWeight: 700 } }}>
              <TableCell>Name</TableCell>
              <TableCell>Code</TableCell>
              <TableCell>Factory / Department</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Max Occupancy</TableCell>
              <TableCell>Mandatory PPE</TableCell>
              <TableCell>Restricted</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(zones ?? []).map((z) => (
              <TableRow key={z.id} hover>
                <TableCell sx={{ fontWeight: 600 }}>{z.name}</TableCell>
                <TableCell>{z.code}</TableCell>
                <TableCell>
                  <Stack spacing={0}>
                    <Typography variant="body2">{z.factory_name}</Typography>
                    <Typography variant="caption" color="text.secondary">{z.department_name}</Typography>
                  </Stack>
                </TableCell>
                <TableCell>{z.zone_type}</TableCell>
                <TableCell>{z.max_occupancy}</TableCell>
                <TableCell>
                  <Stack direction="row" spacing={0.5} flexWrap="wrap" alignItems="center">
                    {(z.required_ppe_types ?? []).map((code: string) => (
                      <Chip
                        key={code}
                        size="small"
                        variant="outlined"
                        label={ppeTypes?.find((t) => t.code === code)?.name ?? code}
                      />
                    ))}
                    {(!z.required_ppe_types || z.required_ppe_types.length === 0) && (
                      <Typography variant="caption" color="text.secondary">None</Typography>
                    )}
                    <Tooltip title="Edit mandatory PPE">
                      <IconButton size="small" onClick={() => setPpeZone({ id: z.id, name: z.name })}>
                        <EditOutlinedIcon fontSize="inherit" />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                </TableCell>
                <TableCell>
                  {z.is_restricted ? <Chip size="small" color="warning" label="Restricted" /> : "—"}
                </TableCell>
                <TableCell align="right">
                  <IconButton
                    size="small"
                    color="error"
                    disabled={deleteMutation.isPending}
                    onClick={() => deleteMutation.mutate(z.id)}
                    title="Delete zone"
                  >
                    <DeleteOutlineIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && (zones ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={8}>
                  <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: "center" }}>
                    No zones yet.
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
