import { useRef, useState } from "react";
import { Alert, Box, CircularProgress, Stack, TextField, Typography } from "@mui/material";
import { useAuthImage } from "./AuthImage";

/** Normalized to the reference photo: 0..1 of its width/height from the top-left. */
export interface Roi { x: number; y: number; width: number; height: number }

const MIN_SIDE = 0.02;
const clamp = (value: number) => Math.min(1, Math.max(0, value));
const round = (value: number) => Math.round(value * 10000) / 10000;

export function roiValid(roi: Roi | null): roi is Roi {
  return !!roi && roi.width >= MIN_SIDE && roi.height >= MIN_SIDE && roi.x >= 0 && roi.y >= 0
    && roi.x + roi.width <= 1.0001 && roi.y + roi.height <= 1.0001;
}

/** Drag on the reference photo to mark the asset area; the numeric fields
 * give a keyboard-accessible and precise alternative to the mouse. */
export function RoiEditor({ imagePath, value, onChange, disabled }: {
  imagePath: string | null; value: Roi | null; onChange: (roi: Roi) => void; disabled?: boolean;
}) {
  const { url, error, loading } = useAuthImage(imagePath);
  const frame = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);

  const point = (event: React.PointerEvent) => {
    const rect = frame.current!.getBoundingClientRect();
    return { x: clamp((event.clientX - rect.left) / rect.width), y: clamp((event.clientY - rect.top) / rect.height) };
  };
  const fromDrag = (d: NonNullable<typeof drag>): Roi => ({
    x: round(Math.min(d.x0, d.x1)), y: round(Math.min(d.y0, d.y1)),
    width: round(Math.abs(d.x1 - d.x0)), height: round(Math.abs(d.y1 - d.y0)),
  });
  const shown = drag ? fromDrag(drag) : value;
  const setField = (field: keyof Roi, percent: string) => {
    const base = value ?? { x: 0.4, y: 0.4, width: 0.1, height: 0.2 };
    const next = { ...base, [field]: round(clamp(Number(percent) / 100)) };
    if (!Number.isNaN(next[field])) onChange(next);
  };

  if (!imagePath) return <Alert severity="info">Capture a reference photo first, then mark the asset on it.</Alert>;
  if (loading) return <CircularProgress size={24} role="status" aria-label="Loading reference photo" />;
  if (error || !url) return <Alert severity="warning">Reference photo could not be loaded. Retry later.</Alert>;

  return <Stack spacing={1}>
    <Typography variant="body2" color="text.secondary">
      Drag a box tightly around the asset where it should be. Avoid walkways where people stand.
    </Typography>
    <Box ref={frame} sx={{ position: "relative", userSelect: "none", touchAction: "none", cursor: disabled ? "default" : "crosshair", lineHeight: 0 }}
      onPointerDown={event => {
        if (disabled) return;
        frame.current!.setPointerCapture(event.pointerId);
        const p = point(event);
        setDrag({ x0: p.x, y0: p.y, x1: p.x, y1: p.y });
      }}
      onPointerMove={event => { if (drag) { const p = point(event); setDrag({ ...drag, x1: p.x, y1: p.y }); } }}
      onPointerUp={() => {
        if (!drag) return;
        const roi = fromDrag(drag);
        setDrag(null);
        if (roiValid(roi)) onChange(roi);
      }}
      onPointerCancel={() => setDrag(null)}>
      <Box component="img" src={url} alt="Reference photo" draggable={false} sx={{ width: "100%", display: "block", borderRadius: 1 }} />
      {shown && <Box aria-hidden sx={{ position: "absolute", left: `${shown.x * 100}%`, top: `${shown.y * 100}%`,
        width: `${shown.width * 100}%`, height: `${shown.height * 100}%`, border: "2px solid", borderColor: "error.main",
        bgcolor: "rgba(211, 47, 47, 0.12)", pointerEvents: "none" }} />}
    </Box>
    <Stack direction="row" spacing={1}>
      {(["x", "y", "width", "height"] as const).map(field => <TextField key={field} size="small" type="number" disabled={disabled}
        label={`${field === "x" ? "Left" : field === "y" ? "Top" : field === "width" ? "Width" : "Height"} %`}
        value={value ? Math.round(value[field] * 1000) / 10 : ""} inputProps={{ min: 0, max: 100, step: 0.5 }}
        onChange={event => setField(field, event.target.value)} />)}
    </Stack>
    {value && !roiValid(value) && <Alert severity="warning">The area must stay inside the photo and be at least 2% wide and tall.</Alert>}
  </Stack>;
}
