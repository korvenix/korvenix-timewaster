/**
 * Time Waster — k6 Load Test
 *
 * Target:  POST /api/join-events
 * Goal:    50 concurrent VUs, p99 < 500ms, 0 errors
 *
 * Run:
 *   k6 run \
 *     -e API_BASE_URL=http://localhost:8000 \
 *     -e AUTH_TOKEN=<valid-oidc-token> \
 *     backend/tests/load/k6-load-test.js
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const errorRate = new Rate('error_rate');
const joinEventDuration = new Trend('join_event_duration', true);

export const options = {
  scenarios: {
    concurrent_join_events: {
      executor: 'shared-iterations',
      vus: 50,
      iterations: 500,
      maxDuration: '60s',
    },
  },
  thresholds: {
    http_req_duration: ['p(99)<500'],
    http_req_failed: ['rate==0'],
    error_rate: ['rate==0'],
  },
};

const BASE_URL = __ENV.API_BASE_URL || 'http://localhost:8000';
const AUTH_TOKEN = __ENV.AUTH_TOKEN || 'test-token';

const HEADERS = {
  'Content-Type': 'application/json',
  Authorization: `Bearer ${AUTH_TOKEN}`,
};

// Pool of synthetic event IDs to spread load across Firestore documents
const EVENT_IDS = Array.from({ length: 100 }, (_, i) => `load-test-event-${i}`);

export default function () {
  const eventId = EVENT_IDS[Math.floor(Math.random() * EVENT_IDS.length)];
  const now = new Date().toISOString();

  const payload = JSON.stringify({
    eventId,
    joinedAt: now,
    meetingStartAt: now,
  });

  const res = http.post(`${BASE_URL}/api/join-events`, payload, { headers: HEADERS });

  const success = check(res, {
    'status 200': (r) => r.status === 200,
    'response time < 500ms': (r) => r.timings.duration < 500,
    'no error in body': (r) => {
      try {
        const body = JSON.parse(r.body);
        return !body.detail && !body.error;
      } catch {
        return false;
      }
    },
  });

  errorRate.add(!success);
  joinEventDuration.add(res.timings.duration);
}

export function handleSummary(data) {
  const p99 = data.metrics.http_req_duration.values['p(99)'];
  const errors = data.metrics.http_req_failed.values.rate;

  console.log(`\n=== Load Test Summary ===`);
  console.log(`p99 latency : ${p99 ? p99.toFixed(1) + 'ms' : 'N/A'}`);
  console.log(`Error rate  : ${errors !== undefined ? (errors * 100).toFixed(2) + '%' : 'N/A'}`);
  console.log(`Threshold   : p99 < 500ms, error rate = 0%`);
  console.log(`Result      : ${p99 < 500 && errors === 0 ? 'PASS' : 'FAIL'}`);

  return {
    stdout: JSON.stringify(data, null, 2),
  };
}
