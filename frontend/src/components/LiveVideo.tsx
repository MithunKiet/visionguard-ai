import { useEffect, useRef, useState } from "react";
import Hls, { Loader, LoaderCallbacks, LoaderConfiguration, LoaderContext, LoaderStats } from "hls.js";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api, API_URL } from "../api/client";
import { useAuthStore } from "../store/authStore";

/** Keep every request in this camera's gateway and reuse session refresh logic. */
function cameraLoader(base: URL) {
  return class implements Loader<LoaderContext> {
    context: LoaderContext | null = null;
    stats: LoaderStats = { aborted: false, loaded: 0, total: 0, retry: 0, chunkCount: 0, bwEstimate: 0,
      loading: { start: 0, first: 0, end: 0 }, parsing: { start: 0, end: 0 }, buffering: { start: 0, first: 0, end: 0 } };
    controller = new AbortController();
    abort() { this.stats.aborted = true; this.controller.abort(); }
    destroy() { this.abort(); }
    load(context: LoaderContext, config: LoaderConfiguration, callbacks: LoaderCallbacks<LoaderContext>) {
      this.context = context;
      this.stats.loading.start = performance.now();
      const url = new URL(context.url, base);
      const file = url.pathname.slice(base.pathname.length);
      if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname) || url.search || url.hash ||
          url.username || url.password || !/^[A-Za-z0-9_-]+\.(m3u8|mp4|m4s|ts)$/.test(file)) {
        callbacks.onError({ code: 400, text: "Invalid media URL" }, context, null, this.stats);
        return;
      }
      const session = useAuthStore.getState().user;
      void api.get(url.href, { signal: this.controller.signal, timeout: Math.min(config.timeout || 20000, 20000),
        responseType: context.responseType === "arraybuffer" ? "arraybuffer" : "text",
      }).then(response => {
        const current = useAuthStore.getState().user;
        if (this.stats.aborted || current?.id !== session?.id || current?.enterprise_id !== session?.enterprise_id) return;
        const data = response.data as string | ArrayBuffer;
        this.stats.loading.first = this.stats.loading.end = performance.now();
        this.stats.loaded = this.stats.total = typeof data === "string" ? new TextEncoder().encode(data).length : data.byteLength;
        callbacks.onSuccess({ url: url.href, data }, this.stats, context, null);
      }).catch(error => {
        if (!this.stats.aborted) callbacks.onError({ code: error.response?.status ?? 0, text: "Live stream unavailable" }, context, null, this.stats);
      });
    }
  };
}

export default function LiveVideo({ cameraId, name }: { cameraId: string; name: string }) {
  const video = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");
  const user = useAuthStore(state => state.user);
  useEffect(() => {
    if (!playing || !video.current) return;
    if (!Hls.isSupported()) {
      setError("Live playback requires a browser with Media Source support.");
      setPlaying(false);
      return;
    }
    const element = video.current;
    const base = new URL(`${API_URL}/api/v1/cameras/${encodeURIComponent(cameraId)}/live/`, window.location.origin);
    const hls = new Hls({ loader: cameraLoader(base), lowLatencyMode: false, maxBufferLength: 6, backBufferLength: 0 });
    hls.on(Hls.Events.ERROR, (_, data) => {
      const code = data.response?.code;
      if (data.fatal || (code && [401, 403, 404, 409].includes(code))) {
        setError(code === 404 ? "Live streaming is not configured or access is unavailable." :
          code === 409 ? "Live streaming is paused for this camera." : "Live stream unavailable. Check access or try again.");
        setPlaying(false);
      }
    });
    hls.loadSource(new URL("index.m3u8", base).href);
    hls.attachMedia(element);
    return () => { hls.destroy(); element.removeAttribute("src"); element.load(); };
  }, [cameraId, playing, user?.id, user?.enterprise_id]);

  return <Stack onClick={event => event.stopPropagation()} sx={{ height: "100%", color: "white", alignItems: "center", justifyContent: "center" }}>
    {playing ? <>
      <video ref={video} aria-label={`Live video: ${name}`} autoPlay muted playsInline controls style={{ width: "100%", minHeight: 0, flex: 1 }} />
      <Button onClick={() => setPlaying(false)}>Stop live video</Button>
    </> : <>
      {error && <Typography role="alert" sx={{ p: 1 }}>{error}</Typography>}
      <Button onClick={() => { setError(""); setPlaying(true); }}>Play live video</Button>
    </>}
  </Stack>;
}
