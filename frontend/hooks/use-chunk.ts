"use client";

import { api } from "@/lib/api-client";
import { ASYNC_THRESHOLD_MB, type Strategy } from "@/lib/constants";
import type { ChunkOut } from "@/lib/types";
import { useMutation } from "@tanstack/react-query";

/**
 * 切块请求：同步路径（小文件）。
 * 大文件走 useJob(kind=parse_and_chunk) —— 由页面按大小分流，本 hook 只负责同步请求。
 * 结果缓存由页面 state 管理（按 strategy 键），切 Tab 不重发。
 */
export function useChunk() {
  return useMutation({
    mutationFn: (vars: { file: File; strategy: Strategy }) => api.parseAndChunk(vars.file, vars.strategy),
  });
}

/** 切片指标统计 */
export interface ChunkStats {
  total: number;
  avgLength: number;
  maxLength: number;
  headerPathRatio: number;
}

export function computeStats(chunks: ChunkOut[]): ChunkStats {
  if (chunks.length === 0) {
    return { total: 0, avgLength: 0, maxLength: 0, headerPathRatio: 0 };
  }
  const lengths = chunks.map((c) => c.page_content.length);
  const withHeader = chunks.filter((c) => !!c.metadata?.header_path).length;
  return {
    total: chunks.length,
    avgLength: Math.round(lengths.reduce((a, b) => a + b, 0) / lengths.length),
    maxLength: Math.max(...lengths),
    headerPathRatio: Math.round((withHeader / chunks.length) * 100),
  };
}

/** 大文件阈值重导出，便于页面分流判断 */
export { ASYNC_THRESHOLD_MB };
