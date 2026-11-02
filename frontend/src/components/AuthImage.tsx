import { useEffect, useState } from "react";
import { Alert, Box, CircularProgress, type SxProps, type Theme } from "@mui/material";
import { api } from "../api/client";

/** Fetches a private image through the authenticated API (no permanent URLs)
 * and revokes its object URL when the path changes or the view unmounts. */
export function useAuthImage(path: string | null) {
  const [state, setState] = useState<{ url: string | null; error: boolean; loading: boolean }>({ url: null, error: false, loading: false });
  useEffect(() => {
    if (!path) { setState({ url: null, error: false, loading: false }); return; }
    const controller = new AbortController();
    let url: string | null = null;
    setState({ url: null, error: false, loading: true });
    api.get(path, { responseType: "blob", signal: controller.signal })
      .then(response => {
        if (controller.signal.aborted) return;
        url = URL.createObjectURL(response.data);
        setState({ url, error: false, loading: false });
      })
      .catch(() => { if (!controller.signal.aborted) setState({ url: null, error: true, loading: false }); });
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [path]);
  return state;
}

export function AuthImage({ path, alt, sx }: { path: string; alt: string; sx?: SxProps<Theme> }) {
  const { url, error, loading } = useAuthImage(path);
  if (loading) return <CircularProgress size={24} role="status" aria-label={`Loading ${alt}`} />;
  if (error || !url) return <Alert severity="warning">Image could not be loaded. Retry later; do not treat a missing image as confirmation.</Alert>;
  return <Box component="img" src={url} alt={alt} sx={[{ width: "100%", maxHeight: 440, objectFit: "contain", bgcolor: "background.default", borderRadius: 1 },
    ...(Array.isArray(sx) ? sx : sx ? [sx] : [])]} />;
}
