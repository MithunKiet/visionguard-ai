import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import { api } from "../api/client";
import { useAuthStore } from "../store/authStore";
import { SearchableSelect } from "./SearchableSelect";

const ALL_ROLES = ["SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "FACTORY_MANAGER", "SAFETY_OFFICER", "SUPERVISOR", "VIEWER"];

// Mirrors backend modules/users/application/services.py::_ASSIGNABLE_ROLES —
// UI-side hint only, the backend re-validates every request regardless.
const ASSIGNABLE_ROLES: Record<string, string[]> = {
  SYSTEM_ADMIN: ALL_ROLES,
  ENTERPRISE_ADMIN: ["FACTORY_MANAGER", "SAFETY_OFFICER", "SUPERVISOR", "VIEWER"],
  FACTORY_MANAGER: ["SAFETY_OFFICER", "SUPERVISOR", "VIEWER"],
};

function assignableRoles(callerRoles: string[]): Set<string> {
  const out = new Set<string>();
  for (const r of callerRoles) for (const a of ASSIGNABLE_ROLES[r] ?? []) out.add(a);
  return out;
}

interface UserToEdit {
  id: string;
  name: string;
  email: string;
  status: string;
  roles: string[];
  factory_id: string | null;
  department_id: string | null;
}

interface InviteUserDialogProps {
  open: boolean;
  onClose: () => void;
  /** When set, the dialog edits this user (PUT) instead of inviting one (POST). */
  user?: UserToEdit | null;
}

const EMPTY_FORM = {
  name: "",
  email: "",
  roles: [] as string[],
  factory_id: "",
  department_id: "",
  status: "Active",
};

function formFromUser(user: UserToEdit) {
  return {
    name: user.name,
    email: user.email,
    roles: [...user.roles],
    factory_id: user.factory_id ?? "",
    department_id: user.department_id ?? "",
    status: user.status,
  };
}

interface CreatedResult {
  name: string;
  email: string;
  temp_password: string;
  welcome_email_sent: boolean;
}

export function InviteUserDialog({ open, onClose, user }: InviteUserDialogProps) {
  const isEdit = !!user;
  const queryClient = useQueryClient();
  const caller = useAuthStore((s) => s.user);
  const [form, setForm] = useState(user ? formFromUser(user) : EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CreatedResult | null>(null);

  useEffect(() => {
    if (open) setForm(user ? formFromUser(user) : EMPTY_FORM);
  }, [open, user]);

  const { data: factories } = useQuery({
    queryKey: ["factories"],
    queryFn: async () => (await api.get("/factories")).data.data as any[],
    enabled: open,
  });
  const { data: departments } = useQuery({
    queryKey: ["departments"],
    queryFn: async () => (await api.get("/departments")).data.data as any[],
    enabled: open,
  });

  const allowedRoles = assignableRoles(caller?.roles ?? []);
  // Roles already on the user being edited stay visible (checked, disabled)
  // even if the caller isn't allowed to grant them fresh — dropping them
  // from the form silently would mean unchecking them for real on save.
  const displayRoles = ALL_ROLES.filter((r) => allowedRoles.has(r) || form.roles.includes(r));

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (isEdit) {
        const payload = {
          name: form.name.trim(),
          status: form.status,
          roles: form.roles,
          factory_id: form.factory_id || null,
          department_id: form.department_id || null,
        };
        return (await api.put(`/users/${user!.id}`, payload)).data.data;
      }
      const payload = {
        name: form.name.trim(),
        email: form.email.trim(),
        roles: form.roles,
        factory_id: form.factory_id || null,
        department_id: form.department_id || null,
      };
      return (await api.post("/users", payload)).data.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      if (isEdit) {
        handleClose();
      } else {
        setResult(data);
      }
    },
    onError: (err: any) =>
      setError(err?.response?.data?.error?.message ?? err?.message ?? `Failed to ${isEdit ? "update" : "invite"} user`),
  });

  const set = (field: "name" | "email") => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [field]: e.target.value }));

  const setField = (field: "factory_id" | "department_id") => (value: string) =>
    setForm((f) => ({ ...f, [field]: value, ...(field === "factory_id" ? { department_id: "" } : {}) }));

  const toggleRole = (role: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({
      ...f,
      roles: e.target.checked ? [...f.roles, role] : f.roles.filter((r) => r !== role),
    }));

  const handleClose = () => {
    setError(null);
    setResult(null);
    onClose();
  };

  const departmentOptions = (departments ?? []).filter((d) => !form.factory_id || d.factory_id === form.factory_id);

  const canSubmit =
    form.name.trim() &&
    (isEdit || form.email.trim()) &&
    form.roles.length > 0 &&
    !saveMutation.isPending;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>{result ? "User Invited" : isEdit ? "Edit User" : "Invite User"}</DialogTitle>
      <DialogContent>
        {result ? (
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="success">
              <b>{result.name}</b> ({result.email}) has been added.
            </Alert>

            {!result.welcome_email_sent && (
              <Alert severity="warning">
                No email server is configured in this environment, so the welcome email was not
                sent — share these credentials with them yourself.
              </Alert>
            )}

            <Divider />

            <Stack spacing={0.5}>
              <Typography variant="caption" color="text.secondary">
                Temporary password — shown only once, copy it now
              </Typography>
              <Typography variant="body1" sx={{ fontFamily: "monospace", fontWeight: 700 }}>
                {result.temp_password}
              </Typography>
            </Stack>

            <Typography variant="caption" color="text.secondary">
              They'll be forced to set a new password on first login.
            </Typography>
          </Stack>
        ) : (
          <Stack spacing={2} sx={{ mt: 1 }}>
            {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}

            <Stack direction="row" spacing={2}>
              <TextField label="Name" value={form.name} onChange={set("name")} required fullWidth />
              <TextField
                label="Email"
                value={form.email}
                onChange={set("email")}
                required
                fullWidth
                type="email"
                disabled={isEdit}
                helperText={isEdit ? "Email can't be changed" : undefined}
              />
            </Stack>

            <div>
              <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
                Roles *
              </Typography>
              <Stack direction="row" flexWrap="wrap">
                {displayRoles.map((role) => (
                  <FormControlLabel
                    key={role}
                    sx={{ width: "50%", mr: 0 }}
                    control={
                      <Checkbox
                        size="small"
                        checked={form.roles.includes(role)}
                        onChange={toggleRole(role)}
                        disabled={!allowedRoles.has(role)}
                      />
                    }
                    label={<Typography variant="body2">{role}</Typography>}
                  />
                ))}
              </Stack>
            </div>

            <SearchableSelect
              label="Factory"
              value={form.factory_id}
              onChange={setField("factory_id")}
              options={(factories ?? []).map((f) => ({ id: f.id, label: `${f.name} (${f.code})` }))}
              helperText="Required for factory/zone-scoped roles — Factory Managers can only assign their own factory regardless of what's picked here."
            />

            <SearchableSelect
              label="Department (optional)"
              value={form.department_id}
              onChange={setField("department_id")}
              options={departmentOptions.map((d) => ({ id: d.id, label: d.name }))}
              disabled={!form.factory_id}
            />

            {isEdit && (
              <ToggleButtonGroup
                size="small"
                exclusive
                value={form.status}
                onChange={(_, v) => v && setForm((f) => ({ ...f, status: v }))}
              >
                <ToggleButton value="Active">Active</ToggleButton>
                <ToggleButton value="Inactive">Inactive</ToggleButton>
              </ToggleButtonGroup>
            )}

            {!isEdit && (
              <Alert severity="info">
                A secure temporary password is generated automatically — they set their own on
                first login.
              </Alert>
            )}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        {result ? (
          <Button variant="contained" onClick={handleClose}>Done</Button>
        ) : (
          <>
            <Button onClick={handleClose}>Cancel</Button>
            <Button variant="contained" onClick={() => saveMutation.mutate()} disabled={!canSubmit}>
              {saveMutation.isPending ? "Saving…" : isEdit ? "Save Changes" : "Send Invite"}
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
}
