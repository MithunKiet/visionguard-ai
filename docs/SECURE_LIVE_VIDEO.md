# Secure live video

Live Grid uses an authenticated HLS gateway, with playback started explicitly per camera. It no longer embeds a public MediaMTX viewer or derives a stream path from an RTSP URL. This is live viewing, not continuous recording or video archival.

## Access model

`GET /api/v1/cameras/{camera_public_uuid}/live/{asset}` requires the normal access-token Authorization header on **every** playlist, initialization file and segment. The backend checks the current account, revocation/password state, tenant and factory/zone scope, including camera soft deletion. Inactive and maintenance cameras return 409. Missing mappings return 404; unavailable or invalid upstream streams return 503.

The player uses the existing single-flight token refresh flow. Credentials are not placed in media URLs, browser storage, playlists or iframes. A camera-specific loader rejects destinations outside that camera's API path. Logout/unmount destroys playback and aborts its requests. Successful media responses use `Cache-Control: private, no-store`; the gateway never forwards upstream cookies or redirects. Playlist references must be simple sibling filenames, including references inside URI attributes.

Authorization applies when each request begins. Bytes already received cannot be revoked, and an in-flight request may finish after permissions change. The player targets a six-second forward buffer; this is not a strict revocation deadline. Subsequent requests are denied after account, scope or camera changes. Native HLS fallback is deliberately absent because it cannot attach the required Authorization header; use a browser supported by hls.js/Media Source Extensions.

## Configure a deployment

1. Keep MediaMTX and its RTSP/HLS listeners on a trusted private network. The production Compose overlay publishes no media ports. Development ports bind only to loopback. WebRTC, RTMP, SRT and MoQ are disabled. Do not add an nginx `/media` shortcut or publish port 8888: the origin is not the application authorization boundary. Internal RTSP readers remain trusted; isolate workers, relays and the gateway from untrusted containers/hosts.
2. Provision each camera relay explicitly in `infra/mediamtx/mediamtx.yml`. Give every camera a unique path, preferably its public UUID. For a camera MediaMTX can pull directly, configure that path's `source` as its RTSP URL and `sourceOnDemand: yes`. Supply camera credentials through a protected deployment configuration, never commit them. Existing authenticated publisher/ffmpeg relays are also supported. The application does not automatically provision relays when a camera is created.
3. Set independent random `MEDIA_HLS_SECRET` and `MEDIAMTX_PUBLISH_PASSWORD` values securely in the deployment environment. The production overlay requires both. Use at least 32 random characters for the gateway secret. Compose passes the gateway secret to the backend and MediaMTX's `MTX_HLSCDNSECRET`; it identifies gateway requests without MediaMTX's browser-cookie handshake. This powerful origin credential stays server-side. Rotate both services together. Publisher credentials use the pinned MediaMTX version's supported but deprecated path credential settings; review their replacement before upgrading MediaMTX.
4. Set `MEDIA_CAMERA_PATHS` to a JSON object mapping **camera public UUIDs** to their provisioned paths, for example `{"11111111-1111-4111-8111-111111111111":"camera-11111111"}`. Duplicate stream paths, noncanonical UUIDs and unsafe paths are rejected on startup. Verify the physical camera and tenant before assigning a mapping; the operator controls this association. Do not reuse a path for a different camera while old mappings remain.
5. Compose sets `MEDIA_HLS_URL=http://mediamtx:8888`. For a host-run backend, set the private/loopback origin and matching secret in `backend/.env`. An empty origin disables the gateway. Restart API replicas after mapping or credential changes. No database migration is introduced by this feature.
6. Rebuild the frontend and serve it and `/api/` under the same HTTPS origin using the existing reverse proxy. Remove obsolete `VITE_MEDIAMTX_WEBRTC_URL` settings. TLS certificates, secure ingress, and any separate storage endpoint still require deployment configuration.

Use H.264 with a browser-compatible profile/pixel format, frequent keyframes (approximately one second), and supported audio codecs if audio is needed. MediaMTX remuxes; it does not transcode an incompatible camera codec. Non-low-latency fMP4 is intentional: no ICE/TURN or public UDP media ports are needed, at the cost of several seconds of delay. Camera status changes only prevent application viewing/detection; they do not physically power off a camera or stop an operator's independent relay.

## Capacity and operation

Each asset request rechecks SQL/Redis authorization, then releases the SQL connection before reading media. The gateway has a 15-second total upstream deadline, a 256 KiB playlist limit and a 16 MiB segment limit. It buffers one bounded asset per request and opens a short-lived upstream HTTP connection. Set ingress connection/rate limits, size API memory/concurrency and benchmark the intended number of simultaneous viewers before rollout. Bandwidth grows approximately as camera bitrate multiplied by simultaneous viewers. This implementation does not introduce a CDN or a capacity guarantee.

Keep `hlsVariant: fmp4`. Low-latency query parameters, byte-range playlists, nested paths and external playlist URLs are unsupported. Reverse proxies/CDNs must not cache authenticated media. Keep secrets out of access logs and tracing headers. MediaMTX is pinned to version 1.21.2 and an image digest; revalidate configuration, security advisories and playback when updating it.

Before a production pilot, verify two real tenant accounts, allowed/denied camera scopes, logout and suspension during playback, real-domain HTTPS, camera codecs/keyframes, latency, relay outages/recovery and concurrent-viewer limits. Configure camera credentials and relays for the actual site. Synthetic validation does not establish physical-camera performance.

## Validation

Backend regressions exercise every asset type against PostgreSQL/Redis, including anonymous/foreign-tenant requests, factory/zone denial, logout, suspension, password/scope changes, deletion, inactive/maintenance cameras and malformed/unconfigured requests. Origin tests cover unsafe playlist URLs, oversized bodies, redirects, timeouts and isolation of origin credentials. The local full backend run passed 86 tests, including the optional real MediaMTX smoke; all eight Chromium browser tests passed. Backend lint, TypeScript/Vite build, production Compose checks and the frontend production-dependency audit also passed (the build still reports large bundles).

Browser tests decode generated H.264/fMP4 fixtures using authenticated requests, refresh an expired token, clear playback on denial and tear down on logout. The fixtures contain only a synthetic test pattern. Regenerate from the repository root with:

```sh
ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc2=size=64x64:rate=10 -t 4 -an -c:v libx264 -profile:v baseline -pix_fmt yuv420p -g 10 -sc_threshold 0 -f hls -hls_time 1 -hls_segment_type fmp4 -hls_segment_filename frontend/tests/fixtures/live/seg%d.mp4 frontend/tests/fixtures/live/index.m3u8
```

The optional `test_real_media_relay_through_authorized_gateway` additionally reads an actual MediaMTX master playlist, media playlist, initialization file and segment through the authenticated API. Run against an isolated synthetic publisher at `factory-cam-01`, with `TEST_MEDIA_HLS_URL` and `TEST_MEDIA_HLS_SECRET` plus the normal disposable test database/Redis settings. CI skips this optional relay smoke when its origin is absent; authorization and browser regressions still run.
