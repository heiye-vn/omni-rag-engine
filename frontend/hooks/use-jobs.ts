import { api } from "@/lib/api-client";
import { useQuery } from "@tanstack/react-query";

/** 最近异步任务列表：10s 轮询（仪表盘数据源） */
export function useJobs(limit = 20) {
  return useQuery({
    queryKey: ["jobs", limit],
    queryFn: () => api.listJobs(limit),
    refetchInterval: 10_000,
    retry: false,
  });
}
