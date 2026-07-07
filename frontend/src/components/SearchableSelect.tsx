import Autocomplete from "@mui/material/Autocomplete";
import TextField from "@mui/material/TextField";

export interface SearchableOption {
  id: string;
  label: string;
}

interface SearchableSelectProps {
  label: string;
  options: SearchableOption[];
  value: string;
  onChange: (id: string) => void;
  required?: boolean;
  disabled?: boolean;
  helperText?: string;
  fullWidth?: boolean;
  size?: "small" | "medium";
  sx?: object;
}

/** Type-to-filter dropdown for id-backed pickers (zone, factory, department,
 * …) — plain MUI TextField-select has no search box once the option list
 * grows past a handful of entries. */
export function SearchableSelect({
  label,
  options,
  value,
  onChange,
  required,
  disabled,
  helperText,
  fullWidth,
  size,
  sx,
}: SearchableSelectProps) {
  const selected = options.find((o) => o.id === value) ?? null;

  return (
    <Autocomplete
      options={options}
      getOptionLabel={(o) => o.label}
      isOptionEqualToValue={(o, v) => o.id === v.id}
      value={selected}
      onChange={(_, newValue) => onChange(newValue?.id ?? "")}
      disabled={disabled}
      fullWidth={fullWidth}
      size={size}
      sx={sx}
      renderInput={(params) => (
        <TextField {...params} label={label} required={required} helperText={helperText} />
      )}
    />
  );
}
