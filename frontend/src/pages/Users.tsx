import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import AddIcon from "@mui/icons-material/Add";
import BlockIcon from "@mui/icons-material/Block";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TablePagination from "@mui/material/TablePagination";
import Typography from "@mui/material/Typography";
import { api } from "../api/client";
import { InviteUserDialog } from "../components/InviteUserDialog";
import { useAuthStore } from "../store/authStore";

export function Users() {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editUser, setEditUser] = useState<any | null>(null);
  const [page, setPage] = useState(0);
  const roles = useAuthStore(state => state.user?.roles);
  const allowed = roles?.some(role => ["SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER"].includes(role));

  const result = useQuery({
    queryKey: ["users", page], enabled: !!allowed,
    queryFn: async () => {
      const response = await api.get("/users", { params: { page: page + 1, page_size: 20 } });
      return { items: response.data.data as any[], total: response.data.meta.total as number };
    },
  });
  const users = result.isError ? [] : result.data?.items ?? [];

  useEffect(() => {
    if (result.data && !result.isFetching && !result.isError) {
      const lastPage = Math.max(0, Math.ceil(result.data.total / 20) - 1);
      if (page > lastPage) setPage(lastPage);
    }
  }, [result.data, result.isFetching, result.isError, page]);

  const deactivateMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/users/${id}`),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
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

  if (!allowed) return <Alert severity="warning">User administration access is required.</Alert>;

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

      {result.isError && <Alert severity="error" action={<Button color="inherit" onClick={() => void result.refetch()}>Retry</Button>}>
        Users could not be loaded.
      </Alert>}
      {deactivateMutation.isError && <Alert severity="error" action={<Button color="inherit" onClick={() => void result.refetch()}>Refresh list</Button>}>
        User deactivation could not be confirmed. Check the refreshed list before retrying.
      </Alert>}

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
            {users.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: "center" }}>
                    {result.isLoading ? "Loading users…" : result.isError ? "User list unavailable."
                      : result.data?.total ? "No users on this page." : "No users yet."}
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        <TablePagination component="div" count={result.data?.total ?? -1} page={page}
          onPageChange={(_, next) => setPage(next)} rowsPerPage={20} rowsPerPageOptions={[20]} />
      </Paper>
    </Stack>
  );
}
