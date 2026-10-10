// k6 performance smoke test: a short, steady load against the web entry point.
// It is a gate, not a benchmark. The release fails if latency or errors
// cross the thresholds below.
//
//   k6 run -e BASE_URL=http://localhost:8080 tests/load/smoke.js

import http from "k6/http";
import { check, sleep } from "k6";

const BASE = __ENV.BASE_URL || "http://localhost:8080";

export const options = {
  scenarios: {
    steady: {
      executor: "constant-vus",
      vus: 10,
      duration: "30s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{kind:read}": ["p(95)<300"],
    "http_req_duration{kind:write}": ["p(95)<500"],
    checks: ["rate>0.99"],
  },
};

export default function () {
  const health = http.get(`${BASE}/healthz`, { tags: { kind: "read" } });
  check(health, { "web healthy": (r) => r.status === 200 });

  const jobs = http.get(`${BASE}/api/jobs`, { tags: { kind: "read" } });
  check(jobs, { "jobs listed": (r) => r.status === 200 });

  // One write in every five iterations, like a mostly read workload.
  if (__ITER % 5 === 0) {
    const created = http.post(
      `${BASE}/api/jobs`,
      JSON.stringify({ payload: `load test ${__VU}-${__ITER}` }),
      { headers: { "Content-Type": "application/json" }, tags: { kind: "write" } },
    );
    check(created, { "job accepted": (r) => r.status === 202 });
  }

  sleep(0.2);
}
