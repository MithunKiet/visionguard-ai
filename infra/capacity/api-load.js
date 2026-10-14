// Read-only staging workload. Run only against an authorized deployment.
import http from 'k6/http';
import { check, sleep } from 'k6';

const base = (__ENV.CAPACITY_BASE_URL || '').replace(/\/$/, '');
const token = __ENV.CAPACITY_ACCESS_TOKEN;
const users = Number(__ENV.CAPACITY_USERS || 5);
if (!/^https?:\/\/[^/?#@]+$/.test(base) || !token || !Number.isInteger(users) || users < 1 || users > 100) {
  throw new Error('Supply a base URL without credentials/path, an access-token environment variable, and 1–100 users');
}
export const options = {
  vus: users,
  duration: __ENV.CAPACITY_DURATION || '10m',
  discardResponseBodies: true,
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<750'],
    checks: ['rate==1'],
  },
};
export default function () {
  const parameters = { headers: { Authorization: `Bearer ${token}` }, timeout: '10s', redirects: 0 };
  const responses = http.batch([
    ['GET', `${base}/api/v1/alerts?page_size=50`, null, parameters],
    ['GET', `${base}/api/v1/violations?page_size=50`, null, parameters],
    ['GET', `${base}/api/v1/cameras`, null, parameters],
  ]);
  responses.forEach(response => check(response, { 'authorized read succeeds': result => result.status === 200 }));
  sleep(2);
}
