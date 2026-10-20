import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
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

interface LiveState {
  events: LiveEvent[];
  connected: boolean;
  latestOccupancy?: LiveEvent;
}

const EMPTY: LiveState = { events: [], connected: false };
const LiveContext = createContext<LiveState | null>(null);
const RESYNC_KEYS = new Set([
  "open-alert-counts", "recent-violations", "alerts", "alert-detail", "incident-evidence",
  "violations", "cameras", "cameras-live-grid", "notification-deliveries", "notification-delivery-summary",
  "detection-health",
]);
const EVENT_KEYS: Record<LiveEvent["type"], string[]> = {
  "alert.created": ["open-alert-counts", "alerts", "notification-deliveries", "notification-delivery-summary"],
  "violation.created": ["recent-violations", "violations"],
  "camera.status_changed": ["cameras", "cameras-live-grid", "detection-health"],
  "occupancy.updated": [],
};

/** One socket per mounted authenticated shell, shared by every consumer. */
export function LiveFeedProvider({ children }: { children: ReactNode }) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const queryClient = useQueryClient();
  const [state, setState] = useState<LiveState & { token: string | null }>({ ...EMPTY, token: null });

  useEffect(() => {
    setState({ ...EMPTY, token: accessToken });
    if (!accessToken) return;

    let cancelled = false;
    let retryDelay = 2000;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    let occupancyTimer: ReturnType<typeof setTimeout> | undefined;
    let ws: WebSocket | undefined;
    let refreshing = false;
    let resyncRequested = false;
    const pendingKeys = new Set<string>();
    const current = () => !cancelled && useAuthStore.getState().accessToken === accessToken;

    // Coalesce bursts and let an existing fetch finish instead of repeatedly
    // cancelling it. Events received during that fetch schedule another pass.
    const refresh = async () => {
      refreshTimer = undefined;
      if (!current() || refreshing || pendingKeys.size === 0) return;
      const keys = new Set(pendingKeys);
      pendingKeys.clear();
      const predicate = (query: { queryKey: readonly unknown[] }) => keys.has(String(query.queryKey[0]));
      if (resyncRequested && queryClient.getQueryCache().findAll({ predicate })
          .some(query => query.state.fetchStatus === "fetching")) {
        // Joining a request that started before reconnect is not a new
        // snapshot. Fetch once more after it finishes, without starving it.
        for (const key of keys) pendingKeys.add(key);
      }
      resyncRequested = false;
      refreshing = true;
      try {
        await queryClient.invalidateQueries({ predicate }, { cancelRefetch: false });
      } finally {
        refreshing = false;
        if (current() && pendingKeys.size) refreshTimer = setTimeout(() => void refresh(), 1000);
      }
    };
    const enqueue = (keys: Iterable<string>) => {
      for (const key of keys) pendingKeys.add(key);
      if (pendingKeys.size && !refreshing && refreshTimer === undefined) {
        refreshTimer = setTimeout(() => void refresh(), 1000);
      }
    };
    const retry = () => {
      if (!current()) return;
      retryTimer = setTimeout(connect, retryDelay);
      retryDelay = Math.min(retryDelay * 1.5, 15000);
    };

    const connect = () => {
      if (!current()) return;
      // Token travels as the WebSocket subprotocol, not a `?token=` query
      // param. Never log it or retain events from a previous credential.
      let socket: WebSocket;
      try {
        socket = new WebSocket(`${WS_URL}/api/v1/ws/live`, [accessToken]);
      } catch {
        retry();
        return;
      }
      ws = socket;

      socket.onopen = () => {
        if (!current()) return;
        setState(prev => ({ ...prev, connected: true }));
        retryDelay = 2000;
        // Pub/sub cannot replay events missed while disconnected. Restore the
        // persisted views through their existing authorized HTTP endpoints.
        resyncRequested = true;
        enqueue(RESYNC_KEYS);
        clearTimeout(refreshTimer);
        refreshTimer = undefined;
        void refresh();
      };
      socket.onmessage = (msg) => {
        if (!current()) return;
        try {
          const parsed: LiveEvent = JSON.parse(msg.data);
          if (!parsed || !Object.prototype.hasOwnProperty.call(EVENT_KEYS, parsed.type) || !parsed.data
              || typeof parsed.data !== "object" || Array.isArray(parsed.data)) return;
          if (parsed.type === "occupancy.updated") {
            if (!Number.isInteger(parsed.data.current_count) || parsed.data.current_count < 0) return;
            setState(prev => ({ ...prev, latestOccupancy: parsed }));
            clearTimeout(occupancyTimer);
            // A live transport alone does not make old camera telemetry fresh.
            occupancyTimer = setTimeout(() => {
              if (current()) setState(prev => ({ ...prev, latestOccupancy: undefined }));
            }, 60000);
          } else {
            setState(prev => ({ ...prev, events: [parsed, ...prev.events].slice(0, 50) }));
            enqueue(EVENT_KEYS[parsed.type]);
          }
        } catch {
          /* ignore malformed frames */
        }
      };
      socket.onclose = () => {
        if (!current()) return;
        clearTimeout(occupancyTimer);
        setState({ ...EMPTY, token: accessToken });
        retry();
      };
      socket.onerror = () => socket.close();
    };

    // Also avoids opening a throwaway socket during StrictMode's setup probe.
    retryTimer = setTimeout(connect, 0);
    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      clearTimeout(refreshTimer);
      clearTimeout(occupancyTimer);
      pendingKeys.clear();
      ws?.close();
    };
  }, [accessToken, queryClient]);

  // Hide old session data immediately, before effect cleanup/reset runs.
  const value = state.token === accessToken
    ? { events: state.events, connected: state.connected, latestOccupancy: state.latestOccupancy } : EMPTY;
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

export function useLiveFeed(maxEvents = 50) {
  const state = useContext(LiveContext);
  if (!state) throw new Error("useLiveFeed requires LiveFeedProvider");
  return { ...state, events: state.events.slice(0, maxEvents) };
}
