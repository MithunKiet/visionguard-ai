import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import AddIcon from "@mui/icons-material/Add";
import BlockIcon from "@mui/icons-material/Block";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
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
import { InviteUserDialog } from "../components/InviteUserDialog";

async function fetchUsers() {
  const resp = await api.get("/users");
  return resp.data.data as any[];
}

export function Users() {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editUser, setEditUser] = useState<any | null>(null);

  const { data: users, isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: fetchUsers,
  });

  const deactivateMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/users/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  const openInvite = () => {
    setEditUser(null);
    setDialogOpen(true);
  };
  const openEdit = (u: any) => {
    setEditUser(u);
    setDialogOpen(true);
  };
  const closeDialog = () => {
    setDialogOpen(false);
    setEditUser(null);
  };

  return (
    <Stack spacing={3}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Stack spacing={0.5}>
          <Typography variant="h5" fontWeight={700}>
            Users
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Manage who has access to your enterprise and what they can see.
          </Typography>
        </Stack>
        <Button variant="contained" startIcon={<AddIcon />} onClick={openInvite}>
          Invite User
        </Button>
      </Stack>

      <InviteUserDialog open={dialogOpen} onClose={closeDialog} user={editUser} />

      <Paper variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow sx={{ "& th": { bgcolor: "background.default", fontWeight: 700 } }}>
              <TableCell>Name</TableCell>
              <TableCell>Email</TableCell>
              <TableCell>Roles</TableCell>
              <TableCell>Factory</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(users ?? []).map((u) => (
              <TableRow key={u.id} hover>
                <TableCell sx={{ fontWeight: 600 }}>{u.name}</TableCell>
                <TableCell>{u.email}</TableCell>
                <TableCell>
                  <Stack direction="row" spacing={0.5} flexWrap="wrap">
                    {u.roles.map((r: string) => (
                      <Chip key={r} size="small" label={r} variant="outlined" />
                    ))}
                  </Stack>
                </TableCell>
                <TableCell>{u.factory_name ?? "—"}</TableCell>
                <TableCell>
                  <Chip size="small" label={u.status} color={u.status === "Active" ? "success" : "default"} />
                </TableCell>
                <TableCell align="right">
                  <IconButton size="small" onClick={() => openEdit(u)} title="Edit user">
                    <EditOutlinedIcon fontSize="small" />
                  </IconButton>
                  <IconButton
                    size="small"
                    color="error"
                    disabled={deactivateMutation.isPending || u.status === "Inactive"}
                    onClick={() => deactivateMutation.mutate(u.id)}
                    title="Deactivate user"
                  >
                    <BlockIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && (users ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: "center" }}>
                    No users yet.
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
