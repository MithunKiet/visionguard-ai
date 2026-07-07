import { Dropdown } from "semantic-ui-react";

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
}

/** Type-to-filter dropdown for id-backed pickers (zone, factory, department,
 * …) — semantic-ui-react's search+selection Dropdown
 * (semantic-ui.com/modules/dropdown.html), not MUI's plain select. */
export function SearchableSelect({
  label,
  options,
  value,
  onChange,
  required,
  disabled,
  helperText,
}: SearchableSelectProps) {
  return (
    <div>
      <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 6, color: "#374151" }}>
        {label}
        {required && " *"}
      </label>
      <Dropdown
        placeholder={`Search ${label.toLowerCase()}…`}
        fluid
        search
        selection
        clearable={!required}
        disabled={disabled}
        options={options.map((o) => ({ key: o.id, text: o.label, value: o.id }))}
        value={value || undefined}
        onChange={(_, data) => onChange((data.value as string) ?? "")}
      />
      {helperText && (
        <div style={{ fontSize: 12, color: "#9CA3AF", marginTop: 4 }}>{helperText}</div>
      )}
    </div>
  );
}
