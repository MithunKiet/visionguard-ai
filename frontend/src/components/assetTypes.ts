// Keep in sync with AssetType in backend/src/modules/assets/api/schemas.py.
export const ASSET_TYPES: Record<string, { label: string; codePrefix: string }> = {
  FIRE_EXTINGUISHER: { label: "Fire extinguisher", codePrefix: "FE" },
  DUSTBIN: { label: "Dustbin", codePrefix: "DB" },
  FIRST_AID_BOX: { label: "First-aid box", codePrefix: "FA" },
  EMERGENCY_EXIT_SIGN: { label: "Emergency exit sign", codePrefix: "EX" },
  OTHER: { label: "Other", codePrefix: "AS" },
};

export const assetTypeLabel = (type: string) => ASSET_TYPES[type]?.label ?? type;
