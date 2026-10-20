import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export interface DetectionHealthData {
  checked_at: string;
  summary: { total_cameras: number; expected_cameras: number; detecting_cameras: number; gap_cameras: number; paused_cameras: number; status: string };
  cameras: { camera_id: string; camera_name: string; factory_name: string; zone_name: string; state: string; last_inference_at: string | null }[];
}

export function useDetectionHealth(page = 0, problemsOnly = false) {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(performance.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const query = useQuery({
    queryKey: ["detection-health", page, problemsOnly],
    queryFn: async ({ signal }) => {
      const startedAt = performance.now();
      const startedWallAt = Date.now();
      const response = await api.get("/analytics/detection-health", {
        params: { page: page + 1, page_size: 20, problems_only: problemsOnly }, signal,
      });
      if (!response.data.data?.summary || !Array.isArray(response.data.data?.cameras)) throw new Error("Invalid health response");
      return { data: response.data.data as DetectionHealthData, total: response.data.meta.total as number, startedAt, startedWallAt };
    },
    refetchInterval: 10000, refetchOnWindowFocus: "always",
  });
  // Charge request transit time too. A resumed tab or failing HTTP refresh
  // must not keep displaying old detection evidence as current.
  const fresh = !query.isError && query.data && Math.max(
    Math.max(now, performance.now()) - query.data.startedAt, Date.now() - query.data.startedWallAt,
  ) < 15000;
  return { ...query, current: fresh ? query.data : undefined };
}
