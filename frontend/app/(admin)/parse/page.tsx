"use client";

import { ElementCard } from "@/components/parse/element-card";
import { SourceViewer, SourceViewerSkeleton } from "@/components/parse/source-viewer";
import { UploadZone } from "@/components/parse/upload-zone";
import { Card, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/input";
import { useJob, extractParsedDocuments } from "@/hooks/use-job";
import { useParse } from "@/hooks/use-parse";
import { ASYNC_THRESHOLD_MB } from "@/lib/constants";
import { formatSize, isLargeFile } from "@/lib/file";
import type { Element, ParsedDocument } from "@/lib/types";
import { cn } from "@/lib/utils";
import { FileSearch, Rows3 } from "lucide-react";
import { useMemo, useState } from "react";

const CHIP_ACTIVE = "bg-brand-600 text-white ring-brand-600";
const CHIP_IDLE = "bg-white text-stone-600 ring-stone-200 hover:bg-brand-50 hover:text-brand-700 hover:ring-brand-200";

export default function ParsePage() {
  const syncParse = useParse();
  const job = useJob();

  const [file, setFile] = useState<File | null>(null);
  const [asyncMode, setAsyncMode] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);

  // 统一数据源：同步结果或异步终态结果
  const documents: ParsedDocument[] | undefined = asyncMode
    ? (extractParsedDocuments(job.job) ?? undefined)
    : syncParse.data;

  const loading = asyncMode ? job.poll.isPending : syncParse.isPending;
  const error = asyncMode
    ? (job.job?.status === "failed" ? job.job.error : job.submit.error?.message)
    : syncParse.error?.message;

  const handleFile = (f: File) => {
    // 重置状态
    syncParse.reset();
    job.reset();
    setSelectedId(null);
    setTypeFilter(null);
    setFile(f);

    if (isLargeFile(f, ASYNC_THRESHOLD_MB)) {
      setAsyncMode(true);
      job.submit.mutate({ file: f, kind: "parse" });
    } else {
      setAsyncMode(false);
      syncParse.mutate(f);
    }
  };

  // 合并多文档元素（压缩包场景），并按类型过滤
  const allElements = useMemo<Element[]>(() => {
    if (!documents) return [];
    return documents.flatMap((doc) => doc.elements);
  }, [documents]);

  const typeCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const el of allElements) counts.set(el.type, (counts.get(el.type) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [allElements]);

  const visibleElements = useMemo(
    () => (typeFilter ? allElements.filter((el) => el.type === typeFilter) : allElements),
    [allElements, typeFilter],
  );

  const selectedElement = useMemo(
    () => allElements.find((el) => el.id === selectedId) ?? null,
    [allElements, selectedId],
  );

  const primaryDoc = documents?.[0];
  const jobStatus = job.job?.status;

  return (
    <div className="grid h-[calc(100vh-7.5rem)] grid-cols-[280px_minmax(0,1fr)_minmax(0,1.1fr)] gap-4">
      {/* 左栏：上传 + 文件信息 + 类型筛选 */}
      <div className="flex flex-col gap-4 overflow-y-auto">
        <Card>
          <CardTitle className="mb-3">上传文档</CardTitle>
          <UploadZone onFile={handleFile} disabled={loading} />
        </Card>

        {file && (
          <Card>
            <CardTitle className="mb-2 text-xs">文件信息</CardTitle>
            <div className="text-sm font-medium break-all text-ink">{file.name}</div>
            <div className="mt-1 flex items-center gap-2 text-xs text-stone-400">
              <span className="tabular">{formatSize(file.size)}</span>
              {asyncMode && (
                <span className="rounded bg-accent-50 px-1.5 py-0.5 text-[11px] font-medium text-accent-700 ring-1 ring-inset ring-accent-200">
                  异步任务
                </span>
              )}
            </div>
            {asyncMode && jobStatus && (
              <div className="mt-2 text-xs text-stone-500">
                任务状态：
                <span
                  className={cn(
                    "ml-1 font-medium",
                    jobStatus === "succeeded" && "text-brand-600",
                    jobStatus === "failed" && "text-red-600",
                    (jobStatus === "queued" || jobStatus === "running") && "text-accent-600",
                  )}
                >
                  {jobStatus === "queued" ? "排队中…" : jobStatus === "running" ? "解析中…" : jobStatus}
                </span>
              </div>
            )}
          </Card>
        )}

        {typeCounts.length > 0 && (
          <Card>
            <CardTitle className="mb-3 text-xs">元素类型筛选</CardTitle>
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => setTypeFilter(null)}
                className={cn(
                  "rounded-md px-2.5 py-1 text-[11px] font-medium ring-1 ring-inset transition-colors",
                  typeFilter === null ? CHIP_ACTIVE : CHIP_IDLE,
                )}
              >
                全部 {allElements.length}
              </button>
              {typeCounts.map(([type, count]) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => setTypeFilter(type === typeFilter ? null : type)}
                  className={cn(
                    "rounded-md px-2.5 py-1 text-[11px] font-medium ring-1 ring-inset transition-colors",
                    typeFilter === type ? CHIP_ACTIVE : CHIP_IDLE,
                  )}
                >
                  {type} {count}
                </button>
              ))}
            </div>
          </Card>
        )}

        {error && (
          <Card className="border-red-200 bg-red-50">
            <div className="text-xs text-red-700">{String(error)}</div>
          </Card>
        )}
      </div>

      {/* 中栏：Element 列表 */}
      <Card className="flex min-h-0 flex-col">
        <div className="mb-3 flex items-center justify-between">
          <CardTitle>Element 列表</CardTitle>
          {documents && (
            <span className="tabular text-xs text-stone-400">
              {documents.length} 个文档 · {allElements.length} 个元素
            </span>
          )}
        </div>

        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          {loading ? (
            Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)
          ) : visibleElements.length > 0 ? (
            visibleElements.map((el) => (
              <ElementCard
                key={el.id}
                element={el}
                selected={el.id === selectedId}
                onSelect={() => setSelectedId(el.id === selectedId ? null : el.id)}
              />
            ))
          ) : documents ? (
            <EmptyState icon={Rows3} title="该类型下暂无元素" description="切换左侧类型筛选查看其他元素" />
          ) : (
            <EmptyState
              icon={FileSearch}
              title="等待解析"
              description="在左侧上传文档，解析后的结构化语义节点将在此展示，点击可对照原文高亮"
            />
          )}
        </div>
      </Card>

      {/* 右栏：原文对照 */}
      <Card className="flex min-h-0 flex-col">
        <CardTitle className="mb-3">原文对照</CardTitle>
        <div className="min-h-0 flex-1">
          {loading ? (
            <SourceViewerSkeleton />
          ) : (
            <SourceViewer
              rawText={primaryDoc?.raw_text}
              selected={selectedElement}
              fileLabel={primaryDoc?.file_name}
            />
          )}
        </div>
      </Card>
    </div>
  );
}
