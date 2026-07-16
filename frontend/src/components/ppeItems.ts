import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export interface PpeType {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
}

/** Enterprise-defined catalog of PPE items — dynamic, not a hardcoded set.
 * Manage entries via POST/PATCH /ppe-types (see ManagePpeTypesDialog). */
export function usePpeTypes(includeInactive = false) {
  return useQuery({
    queryKey: ["ppe-types", includeInactive],
    queryFn: async () =>
      (await api.get("/ppe-types", { params: { include_inactive: includeInactive } }))
        .data.data as PpeType[],
  });
}

// Reasonable starting guess for a brand-new zone — matches the backend's
// own default when required_ppe_types is omitted entirely.
export const DEFAULT_ZONE_PPE_CODES = ["helmet", "vest"];

/** Human-readable list from an "enforces"/required-codes string array. */
export function formatEnforcedPpe(codes: string[] | undefined, types: PpeType[] | undefined): string {
  if (!codes || codes.length === 0) return "None";
  const nameByCode = new Map((types ?? []).map((t) => [t.code, t.name]));
  return codes.map((c) => nameByCode.get(c) ?? c).join(", ");
}
