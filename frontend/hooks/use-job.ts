"use client";

import { api } from "@/lib/api-client";
import type { Job, JobKind, ParsedDocument } from "@/lib/types";
import type { Strategy } from "@/lib/constants";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

/**
 * 异步解析（大文件 >5MB）：submit → 1.5s 轮询 → 终态停止
 *
 * 用法：
 *   const job = useJob();
 *   job.submit(file, "parse");          // 触发
 *   job.data                             // 终态 Job（含 result）
 */
export function useJob() {
  const queryClient = useQueryClient();

  const submit = useMutation({
    mutationFn: (vars: { file: File; kind: JobKind; strategy?: Strategy }) =>
      api.submitJob(vars.file, vars.kind, { strategy: vars.strategy }),
  });

  const activeJobId = submit.data?.job_id;

  // 轮询任务直至终态；queued/running 状态每 1.5s 刷新
  const poll = useQuery<Job>({
    queryKey: ["job", activeJobId],
    queryFn: () => api.getJob(activeJobId!),
    enabled: !!activeJobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "succeeded" || status === "failed" ? false : 1500;
    },
    retry: false,
  });

  return {
    submit,
    poll,
    /** 终态任务（成功或失败） */
    job: poll.data,
    reset: () => {
      submit.reset();
      queryClient.removeQueries({ queryKey: ["job"] });
    },
  };
}

/** 从异步任务的 result 中提取 ParsedDocument[]（kind=parse 时） */
export function extractParsedDocuments(job: Job | undefined): ParsedDocument[] | null {
  if (!job || job.status !== "succeeded" || job.kind !== "parse") return null;
  return job.result as ParsedDocument[];
}
