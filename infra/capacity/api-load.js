// Read-only staging workload; use an authorized, populated deployment.
import http from 'k6/http';
import { check } from 'k6';

const base = (__ENV.CAPACITY_BASE_URL || '').replace(/\/$/, '');
const token = __ENV.CAPACITY_ACCESS_TOKEN;
const rate = Number(__ENV.CAPACITY_READ_CYCLES_PER_SECOND || 2);
const expectedCameras = Number(__ENV.CAPACITY_EXPECTED_CAMERAS);
const minHistory = Number(__ENV.CAPACITY_MIN_HISTORY || 100);
if (!/^https?:\/\/[^/?#@]+$/.test(base) || !token || !Number.isInteger(rate) || rate < 1 || rate > 30
    || !Number.isInteger(expectedCameras) || expectedCameras < 1 || !Number.isInteger(minHistory) || minHistory < 1) {
  throw new Error('Supply an origin, token, expected camera count, positive minimum history and 1–30 read cycles/second');
}
export const options = {
  scenarios: {
    reviewers: { executor: 'constant-arrival-rate', rate, timeUnit: '1s',
      duration: __ENV.CAPACITY_DURATION || '10m', preAllocatedVUs: 10, maxVUs: 100 },
  },
  thresholds: {
    http_req_failed: ['rate==0'],
    'http_req_duration{name:alerts}': ['p(95)<750'],
    'http_req_duration{name:violations}': ['p(95)<750'],
    'http_req_duration{name:cameras}': ['p(95)<750'],
    dropped_iterations: ['count==0'],
    checks: ['rate==1'],
  },
};
export default function () {
  const parameters = { headers: { Authorization: `Bearer ${token}` }, timeout: '10s', redirects: 0 };
  const paths = ['alerts?page_size=50', 'violations?page_size=50', 'cameras'];
  const responses = http.batch(paths.map(path => ['GET', `${base}/api/v1/${path}`, null,
    { ...parameters, tags: { name: path.split('?')[0] } }]));
  responses.forEach((response, index) => {
    check(response, { 'authorized read succeeds': result => result.status === 200 });
    let body = null;
    try { body = response.json(); } catch (_) { /* Invalid payload fails the data gate. */ }
    check(body, { 'representative dataset present': result => result && result.success === true
      && Array.isArray(result.data) && (index === 2 ? result.data.length === expectedCameras
        : result.data.length > 0 && result.meta && result.meta.total >= minHistory) });
  });
}
