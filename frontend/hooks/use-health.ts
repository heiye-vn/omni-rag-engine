import { api } from "@/lib/api-client";
import { useQuery } from "@tanstack/react-query";

/** 引擎健康状态：30s 轮询 */
export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
    refetchInterval: 30_000,
    // 引擎离线是常态（未启动后端），不重试刷屏
    retry: false,
  });
}
