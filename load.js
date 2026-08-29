import http from "k6/http";
import { check } from "k6";
import { Counter } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:5050";
const ROUTE = __ENV.ROUTE || "/get-pools";
const QUERY = __ENV.QUERY || "";
const RPS = Number(__ENV.RPS || 20);
const DURATION = __ENV.DURATION || "15s";

const poolSelected = new Counter("pool_selected");

export const options = {
  scenarios: {
    get_pools: {
      executor: "constant-arrival-rate",
      rate: RPS,
      timeUnit: "1s",
      duration: DURATION,
      preAllocatedVUs: Math.min(Math.max(RPS, 10), 100),
      maxVUs: Math.min(Math.max(RPS * 2, 20), 200),
    },
  },
};

export default function () {
  const url = QUERY ? `${BASE_URL}${ROUTE}?${QUERY}` : `${BASE_URL}${ROUTE}`;
  const res = http.get(url);

  let poolId = "";
  try {
    poolId = res.json("pool_id") || "";
  } catch (_) {
    poolId = "";
  }

  check(res, {
    "status is 200": (r) => r.status === 200,
    "body has pool_id": () => typeof poolId === "string" && poolId.length > 0,
  });

  if (poolId) {
    poolSelected.add(1, { pool_id: poolId });
  }
}
