"use client";

import { ChunkCard } from "@/components/chunk/chunk-card";
import { StatsBar } from "@/components/chunk/stats-bar";
import { UploadZone } from "@/components/parse/upload-zone";
import { Card, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useChunk, computeStats } from "@/hooks/use-chunk";
import { useJob } from "@/hooks/use-job";
import { ASYNC_THRESHOLD_MB, STRATEGIES, STRATEGY_LABELS, type Strategy } from "@/lib/constants";
import { formatSize, isLargeFile } from "@/lib/file";
import type { ChunkOut } from "@/lib/types";
import { cn } from "@/lib/utils";
import { FlaskConical } from "lucide-react";
import { useState } from "react";

const CHIP_ACTIVE = "bg-brand-600 text-white ring-brand-600";
const CHIP_IDLE = "bg-white text-stone-600 ring-stone-200 hover:bg-brand-50 hover:text-brand-700 hover:ring-brand-200";

export default function ChunkLabPage() {
  const chunk = useChunk();
  const job = useJob();

  const [file, setFile] = useState<File | null>(null);
  const [asyncMode, setAsyncMode] = useState(false);
  const [active, setActive] = useState<Strategy>("auto");
  const [compareMode, setCompareMode] = useState(false);
  const [compared, setCompared] = useState<Strategy[]>([]);
  // 结果缓存：strategy → chunks（切 Tab 不重发）
  const [cache, setCache] = useState<Partial<Record<Strategy, ChunkOut[]>>>({});

  const jobStatus = job.job?.status;
  const asyncChunks: ChunkOut[] | undefined =
    asyncMode && job.job?.status === "succeeded" ? (job.job.result as ChunkOut[]) : undefined;

  const runStrategy = (strategy: Strategy, f: File) => {
    setActive(strategy);
    if (cache[strategy]) return; // 已缓存
    if (isLargeFile(f, ASYNC_THRESHOLD_MB)) {
      setAsyncMode(true);
      job.submit.mutate({ file: f, kind: "parse_and_chunk", strategy });
    } else {
      setAsyncMode(false);
      chunk.mutate(
        { file: f, strategy },
        { onSuccess: (data) => setCache((c) => ({ ...c, [strategy]: data })) },
      );
    }
  };

  const handleFile = (f: File) => {
    chunk.reset();
    job.reset();
    setCache({});
    setCompared([]);
    setFile(f);
    runStrategy("auto", f);
  };

  const toggleCompare = (s: Strategy) => {
    setCompared((prev) => {
      const next = prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s];
      // 选中的策略若未请求过则触发请求
      for (const strategy of next) {
        if (!cache[strategy]) runStrategy(strategy, file!);
      }
      return next;
    });
  };

  const currentChunks: ChunkOut[] | undefined =
    asyncMode ? asyncChunks : (cache[active] ?? undefined);

  const loading =
    (asyncMode && (job.poll.isPending || jobStatus === "queued" || jobStatus === "running")) ||
    (!asyncMode && chunk.isPending && !cache[active]);

  const error = asyncMode
    ? job.job?.status === "failed"
      ? job.job.error
      : job.submit.error?.message
    : chunk.error?.message;

  const errorText = error ? String(error) : undefined;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5">
      {/* 顶部：上传与文件缓存状态 */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-medium text-ink">切块实验室</h1>
          <p className="mt-0.5 text-xs text-stone-500">
            同一文件 × 4 种切片策略，并排对比切片粒度与上下文完整性
          </p>
        </div>
        {file && (
          <Card className="p-3">
            <div className="max-w-56 truncate text-xs font-medium text-ink">{file.name}</div>
            <div className="mt-0.5 flex items-center gap-2 text-[11px] text-stone-400">
              <span className="tabular">{formatSize(file.size)}</span>
              {asyncMode && (
                <span className="rounded bg-accent-50 px-1.5 py-0.5 font-medium text-accent-700 ring-1 ring-inset ring-accent-200">
                  异步任务 · {jobStatus}
                </span>
              )}
            </div>
          </Card>
        )}
      </div>

      {!file && (
        <Card>
          <EmptyState
            icon={FlaskConical}
            title="开始切块策略实验"
            description="上传一个文档，即可在 auto / 滑窗 / 父子 / 标题层级四种策略间切换并缓存结果，支持多策略并排对比"
            className="pb-4"
          />
          <UploadZone onFile={handleFile} hint="上传一个文档开始切块策略对比实验" />
        </Card>
      )}

      {errorText && (
        <Card className="border-red-200 bg-red-50 p-4 text-xs text-red-700">{errorText}</Card>
      )}

      {file && (
        <>
          {/* 策略 Tabs + 对比模式开关 */}
          <Tabs value={active} onValueChange={(v) => runStrategy(v as Strategy, file)}>
            <TabsList className="items-center">
              {STRATEGIES.map((s) => (
                <TabsTrigger key={s} value={s}>
                  {STRATEGY_LABELS[s]}
                </TabsTrigger>
              ))}
              <button
                type="button"
                onClick={() => setCompareMode((v) => !v)}
                className={cn(
                  "mb-1 ml-auto rounded-lg border px-3 py-1.5 text-[11px] font-medium transition-colors",
                  compareMode
                    ? "border-brand-300 bg-brand-50 text-brand-700"
                    : "border-stone-300 text-stone-500 hover:bg-stone-100",
                )}
              >
                {compareMode ? "退出对比" : `加入对比${compared.length ? ` (${compared.length})` : ""}`}
              </button>
            </TabsList>

            {STRATEGIES.map((s) => (
              <TabsContent key={s} value={s} className="mt-4">
                <div className="flex flex-col gap-4">
                  {currentChunks ? (
                    <>
                      <StatsBar stats={computeStats(currentChunks)} />
                      <div className="space-y-2">
                        {currentChunks.map((c, i) => (
                          <ChunkCard key={i} chunk={c} index={i} strategy={s} />
                        ))}
                      </div>
                    </>
                  ) : loading ? (
                    Array.from({ length: 4 }).map((_, i) => (
                      <Skeleton key={i} className="h-24 w-full" />
                    ))
                  ) : null}
                </div>
              </TabsContent>
            ))}
          </Tabs>

          {/* 对比模式：并排展示已选策略的切片与指标 */}
          {compareMode && compared.length >= 2 && (
            <div>
              <div className="mb-2 text-xs text-stone-500">
                对比模式 —— 勾选下方策略加入对比（当前 {compared.length} 个）
              </div>
              <div className="mb-4 flex flex-wrap gap-2">
                {STRATEGIES.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => toggleCompare(s)}
                    className={cn(
                      "rounded-md px-3 py-1.5 text-[11px] font-medium ring-1 ring-inset transition-colors",
                      compared.includes(s) ? CHIP_ACTIVE : CHIP_IDLE,
                    )}
                  >
                    {STRATEGY_LABELS[s]}
                  </button>
                ))}
              </div>

              {/* 指标对比表 */}
              <Card className="mb-4 overflow-x-auto p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-stone-200 bg-paper text-left text-[11px] text-stone-400">
                      <th className="p-3 font-normal">策略</th>
                      <th className="p-3 font-normal">切片总数</th>
                      <th className="p-3 font-normal">平均字符</th>
                      <th className="p-3 font-normal">最长切片</th>
                      <th className="p-3 font-normal">含 header_path</th>
                    </tr>
                  </thead>
                  <tbody>
                    {compared.map((s) => {
                      const chunks = cache[s];
                      const stats = chunks ? computeStats(chunks) : null;
                      return (
                        <tr key={s} className="border-b border-stone-100 last:border-0 hover:bg-brand-50/40">
                          <td className="p-3 font-medium text-ink">{STRATEGY_LABELS[s]}</td>
                          {stats ? (
                            <>
                              <td className="tabular p-3 text-stone-600">{stats.total}</td>
                              <td className="tabular p-3 text-stone-600">{stats.avgLength}</td>
                              <td className="tabular p-3 text-stone-600">{stats.maxLength}</td>
                              <td className="tabular p-3 text-stone-600">{stats.headerPathRatio}%</td>
                            </>
                          ) : (
                            <td className="p-3 text-stone-300" colSpan={4}>
                              请求中…
                            </td>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </Card>

              {/* 并排切片列表 */}
              <div
                className="grid gap-4"
                style={{ gridTemplateColumns: `repeat(${compared.length}, minmax(0, 1fr))` }}
              >
                {compared.map((s) => (
                  <div key={s} className="min-w-0 space-y-2">
                    <CardTitle className="sticky top-0 rounded-md bg-paper py-2 text-xs text-brand-700">
                      {STRATEGY_LABELS[s]} · {(cache[s] ?? []).length} 片
                    </CardTitle>
                    {(cache[s] ?? []).slice(0, 10).map((c, i) => (
                      <ChunkCard key={i} chunk={c} index={i} strategy={s} />
                    ))}
                    {(cache[s] ?? []).length > 10 && (
                      <div className="text-center text-[11px] text-stone-400">
                        仅展示前 10 片，共 {(cache[s] ?? []).length} 片
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 对比模式策略选择（未达 2 个时） */}
          {compareMode && compared.length < 2 && (
            <div className="flex flex-wrap gap-2">
              {STRATEGIES.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => toggleCompare(s)}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-[11px] font-medium ring-1 ring-inset transition-colors",
                    compared.includes(s) ? CHIP_ACTIVE : CHIP_IDLE,
                  )}
                >
                  {STRATEGY_LABELS[s]}
                </button>
              ))}
              <span className="self-center text-[11px] text-stone-400">
                再选 {2 - compared.length} 个策略开始并排对比
              </span>
            </div>
          )}

          {/* 重新上传 */}
          <div className="flex justify-center">
            <button
              type="button"
              onClick={() => {
                setFile(null);
                setCache({});
                setCompared([]);
              }}
              className="text-xs text-stone-500 underline-offset-2 hover:text-brand-700 hover:underline"
            >
              换一个文件重新实验
            </button>
          </div>
        </>
      )}
    </div>
  );
}
