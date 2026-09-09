"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/input";
import { useHealth } from "@/hooks/use-health";
import { useJobs } from "@/hooks/use-jobs";
import { EngineApiError } from "@/lib/api-client";
import type { JobStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Activity, Boxes, Clock3, FileStack, Inbox, Scissors } from "lucide-react";
import Link from "next/link";

const STATUS_TONES: Record<JobStatus, "blue" | "amber" | "green" | "red"> = {
  queued: "blue",
  running: "amber",
  succeeded: "green",
  failed: "red",
};

const STATUS_TEXT: Record<JobStatus, string> = {
  queued: "排队中",
  running: "运行中",
  succeeded: "已完成",
  failed: "失败",
};

function durationText(started?: number | null, finished?: number | null) {
  if (!started || !finished) return "—";
  return `${((finished - started) * 1000).toFixed(0)}ms`;
}

export default function DashboardPage() {
  const health = useHealth();
  const jobs = useJobs();

  const unreachable = health.error instanceof EngineApiError && health.error.unreachable;
  const online = !unreachable && health.data?.status === "ok";

  const stats = [
    {
      label: "引擎状态",
      icon: Activity,
      value: health.isPending ? null : online ? "在线" : "离线",
      sub: online ? "所有端点可用" : "请检查后端服务",
      accent: online,
    },
    { label: "支持格式", icon: FileStack, value: "37+", sub: "txt · md · office · pdf · av…" },
    { label: "切块策略", icon: Scissors, value: "4", sub: "auto / 滑窗 / 父子 / 标题" },
    { label: "向量数据库", icon: Boxes, value: "5", sub: "Chroma · Milvus · Qdrant…" },
  ];

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-5">
      {unreachable && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          无法连接引擎（{process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"}），请先运行{" "}
          <code className="rounded bg-red-100 px-1.5 py-0.5 font-mono text-xs">uv run uvicorn app.server:app</code>
        </div>
      )}

      {/* 指标卡：图标徽章 + 等宽数字 */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {stats.map(({ label, icon: Icon, value, sub, accent }) => (
          <Card key={label} className="p-4">
            <div className="flex items-center justify-between">
              <CardDescription className="mt-0">{label}</CardDescription>
              <div className="flex size-7 items-center justify-center rounded-lg bg-brand-50">
                <Icon className="size-3.5 text-brand-600" />
              </div>
            </div>
            {value === null ? (
              <Skeleton className="mt-2 h-7 w-16" />
            ) : (
              <div
                className={cn(
                  "tabular mt-1 text-xl font-medium",
                  accent === undefined ? "text-ink" : accent ? "text-brand-600" : "text-red-600",
                )}
              >
                {value}
              </div>
            )}
            <div className="mt-0.5 truncate text-[11px] text-stone-400">{sub}</div>
          </Card>
        ))}
      </div>

      {/* 最近异步任务 */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle>最近任务</CardTitle>
            <CardDescription>大文件异步解析任务实时状态</CardDescription>
          </div>
          {jobs.data && jobs.data.length > 0 && (
            <Badge tone="brand">{jobs.data.length} 个任务</Badge>
          )}
        </CardHeader>
        {jobs.isPending ? (
          <div className="space-y-2">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        ) : jobs.data && jobs.data.length > 0 ? (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-stone-200 text-left text-[11px] text-stone-400">
                <th className="pb-2 font-normal">文件</th>
                <th className="pb-2 font-normal">类型</th>
                <th className="pb-2 font-normal">状态</th>
                <th className="pb-2 text-right font-normal">耗时</th>
              </tr>
            </thead>
            <tbody>
              {jobs.data.map((job) => (
                <tr key={job.job_id} className="border-b border-stone-100 last:border-0 hover:bg-brand-50/40">
                  <td className="max-w-56 truncate py-2.5 pr-3 font-medium text-stone-700">{job.file_name}</td>
                  <td className="py-2.5 pr-3 text-stone-500">{job.kind === "parse" ? "解析" : "解析并切块"}</td>
                  <td className="py-2.5 pr-3">
                    <Badge tone={STATUS_TONES[job.status]} dot>
                      {STATUS_TEXT[job.status]}
                    </Badge>
                  </td>
                  <td className="tabular py-2.5 text-right text-stone-500">
                    <span className="inline-flex items-center gap-1">
                      <Clock3 className="size-3 text-stone-300" />
                      {durationText(job.started_at, job.finished_at)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState
            icon={Inbox}
            title="暂无异步任务"
            description="超过 5MB 的大文件会自动转为异步任务，提交后在此实时跟踪排队与解析进度"
          />
        )}
      </Card>

      {/* 快速开始 */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle>快速开始</CardTitle>
            <CardDescription>三步体验引擎核心能力</CardDescription>
          </div>
        </CardHeader>
        <div className="grid gap-3 md:grid-cols-3">
          {[
            { href: "/parse", step: "01", title: "解析文档", desc: "上传文件查看结构化语义节点与原文高亮对照" },
            { href: "/chunk-lab", step: "02", title: "对比切块", desc: "同一文件切换 4 种切片策略并排对比" },
            { href: "/kb", step: "03", title: "检索验证", desc: "入库知识库并发起 Top-K 相似度检索" },
          ].map(({ href, step, title, desc }) => (
            <Link
              key={href}
              href={href}
              className="group rounded-xl border border-stone-200 bg-paper p-4 transition-all hover:border-brand-300 hover:bg-brand-50/60 hover:shadow-xs"
            >
              <div className="font-mono text-[11px] font-medium text-brand-600">{step}</div>
              <div className="mt-1.5 text-sm font-medium text-ink group-hover:text-brand-700">{title}</div>
              <div className="mt-1 text-xs leading-relaxed text-stone-500">{desc}</div>
            </Link>
          ))}
        </div>
      </Card>
    </div>
  );
}
