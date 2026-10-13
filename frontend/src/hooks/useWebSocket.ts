import { useEffect, useRef, useState } from "react";
import { WS_URL } from "../api/client";
import { useAuthStore } from "../store/authStore";

export interface LiveEvent {
  type:
    | "violation.created"
    | "alert.created"
    | "camera.status_changed"
    | "occupancy.updated";
  data: any;
}

/** Connects to /ws/live and keeps a rolling buffer of the most recent events. */
export function useLiveFeed(maxEvents = 50) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    setEvents([]);
    setConnected(false);
    if (!accessToken) return;

    let cancelled = false;
    let retryDelay = 2000;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      if (cancelled) return;
      // Token travels as the WebSocket subprotocol, not a `?token=` query
      // param — keeps it out of server access logs and browser history (see
      // backend/src/modules/realtime/routes.py).
      const ws = new WebSocket(`${WS_URL}/api/v1/ws/live`, [accessToken]);
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled) return;
        setConnected(true);
        retryDelay = 2000;
      };
      ws.onmessage = (msg) => {
        if (cancelled) return;
        try {
          const parsed: LiveEvent = JSON.parse(msg.data);
          setEvents((prev) => [parsed, ...prev].slice(0, maxEvents));
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        if (cancelled) return;
        setConnected(false);
        retryTimer = setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 1.5, 15000);
      };
      ws.onerror = () => ws.close();
    };

    connect();
    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      wsRef.current?.close();
    };
  }, [accessToken, maxEvents]);

  return { events, connected };
}
