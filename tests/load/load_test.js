import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 2000 },  // ramp up to 2000 users over 30 seconds
    { duration: '1m', target: 2000 },   // stay at 2000 users for 1 minute
    { duration: '10s', target: 0 },     // ramp down to 0 users
  ],
  thresholds: {
    http_req_duration: ['p(95)<200'], // 95% of requests must complete below 200ms
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
let INVOICE_ID = __ENV.INVOICE_ID || 'test-id';

export default function () {
  const res = http.get(`${BASE_URL}/invoice`);
  
  check(res, {
    'status is 200': (r) => r.status === 200,
    'latency < 200ms': (r) => r.timings.duration < 200,
  });

  sleep(1);
}
