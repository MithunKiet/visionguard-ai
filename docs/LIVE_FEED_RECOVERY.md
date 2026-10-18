# Browser live-feed recovery

The authenticated application shell now owns one WebSocket per browser tab. The header and dashboard subscribe to the same bounded event buffer; route navigation no longer opens a second connection. Separate tabs still have separate sessions/connections. The backend protocol and authorization rules are unchanged.

## Recover persisted state after a gap

Redis pub/sub and the WebSocket feed are ephemeral. On every successful connection, including reconnect and credential replacement, the client invalidates the existing authorized queries for alert counts/lists/details, incident evidence, violations, cameras/live grid and notification-delivery views. Active queries reload; inactive cached views are marked stale for their next use.

The client waits for an existing HTTP fetch to finish instead of repeatedly cancelling it. If that fetch began before the new connection, another pass obtains a fresh snapshot. This prevents a delayed old response from satisfying the reconnect refresh. Events arriving during an HTTP refresh schedule another pass. Ordinary alert/violation/camera-status bursts are coalesced over a one-second window and refresh only the affected query families. Occupancy telemetry does not refresh those lists.

HTTP snapshots restore the current persisted views, not the missing live-event history. The transient feed keeps at most 50 recent activity events and is cleared on disconnect or token change; it is not an audit log. Missing desktop popups are not replayed. Use persisted alerts/incidents and the durable notification outbox for operational review/delivery. Existing polling remains a fallback; a failed HTTP request is not proof of current server state.

## Telemetry and session boundaries

The latest camera count is kept separately from activity, so occupancy updates cannot evict all recent alerts from the feed. It clears immediately when the socket disconnects. After reconnect it shows `Awaiting update` until a new valid count arrives, and it expires after 60 seconds without another occupancy message even if the WebSocket remains connected. Zero is a valid observed count; unavailable data is never converted to zero. The worker currently emits unchanged counts every 30 seconds.

This expiry measures time since browser receipt. It does not establish camera exposure time, upstream frame freshness, physical occupancy accuracy or cross-camera deduplication. `Live`/`Connected` describes the WebSocket transport, not the health of every camera, query or service.

Logout, token replacement and shell unmount close the old connection and cancel its reconnect, telemetry-expiry and queued-refresh timers. Late callbacks check the current credential before updating state. Old-session live data is hidden immediately during credential changes. Existing HTTP session refresh and backend authorization remain authoritative; this change does not add a separate authentication mechanism.

Malformed JSON, unknown message types, missing/object-incompatible payloads and invalid occupancy counts are ignored. These browser checks are input hygiene, not a substitute for backend tenant/role enforcement.

## Validation

Browser regressions reproduce two defects before their fixes: two simultaneous connections for the header/dashboard, and a slow HTTP response from before reconnect leaving the alert list stale. Tests cover shared connection/navigation, immediate missed-alert refresh, disconnected/expired occupancy, coalesced alert bursts, telemetry/malformed-frame isolation, logout/retry cancellation, cross-tenant buffer clearing and token replacement. HTTP/WebSocket data are mocked; these are browser lifecycle tests, not factory or network capacity evidence.

Run `npm run build` and `npm run test:e2e` in `frontend/`. Site acceptance still needs real HTTPS/WebSocket ingress, authorization changes, network interruption, representative browser concurrency and backend/broker load. The [multi-factory roadmap](MULTI_FACTORY_REMEDIATION.md) retains those external gates.
