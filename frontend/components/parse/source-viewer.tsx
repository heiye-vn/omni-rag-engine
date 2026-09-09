"use client";

import { LocationBadge } from "@/components/parse/location-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { Element } from "@/lib/types";
import { FileText } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";

/**
 * 原文对照视图：
 * - 有 raw_text 且 Element 携带行号定位 → 逐行渲染 + 行号槽 + 区间高亮 + 自动滚动
 * - 其他情况（PDF/音视频/无 raw_text）→ 降级为 Element 详情面板
 */
export function SourceViewer({
  rawText,
  selected,
  fileLabel,
}: {
  rawText?: string | null;
  selected?: Element | null;
  fileLabel?: string;
}) {
  const lines = useMemo(() => (rawText ?? "").split("\n"), [rawText]);
  const containerRef = useRef<HTMLDivElement>(null);
  const highlightRef = useRef<HTMLDivElement>(null);

  const hasLineHighlight =
    !!rawText && !!selected?.location && selected.location.start_line != null;
  const startLine = selected?.location?.start_line ?? 0;
  const endLine = selected?.location?.end_line ?? startLine;

  // 选中变化时自动滚动到高亮区间
  useEffect(() => {
    if (hasLineHighlight && highlightRef.current && containerRef.current) {
      highlightRef.current.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [hasLineHighlight, startLine, endLine]);

  if (!rawText) {
    return <DetailPanel element={selected} fileLabel={fileLabel} />;
  }

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs text-stone-400">
          {hasLineHighlight ? (
            <>
              选中 <span className="font-medium text-brand-700">L{startLine}-L{endLine}</span>
            </>
          ) : (
            "点击左侧元素查看对应原文"
          )}
        </span>
        <span className="tabular text-xs text-stone-400">{lines.length} 行</span>
      </div>
      <div
        ref={containerRef}
        className="flex-1 overflow-auto rounded-lg border border-stone-200/60 bg-[#fdfcf9] py-2 font-mono text-xs leading-relaxed"
      >
        {lines.map((line, i) => {
          const lineNo = i + 1;
          const inRange = hasLineHighlight && lineNo >= startLine && lineNo <= endLine;
          return (
            <div
              key={lineNo}
              ref={inRange && lineNo === startLine ? highlightRef : undefined}
              className={cn(
                "flex border-l-2 px-3 whitespace-pre-wrap",
                inRange ? "border-brand-500 bg-brand-100/60 text-ink" : "border-transparent",
              )}
            >
              <span
                className={cn(
                  "tabular mr-3 w-10 shrink-0 select-none text-right",
                  inRange ? "font-medium text-brand-700" : "text-stone-300",
                )}
              >
                {lineNo}
              </span>
              <span className={cn(inRange ? "text-ink" : "text-stone-600")}>
                {line || "\u00A0"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** 降级详情面板：无行号定位的格式（PDF/PPTX/音视频）展示 Element 完整信息 */
function DetailPanel({ element, fileLabel }: { element?: Element | null; fileLabel?: string }) {
  if (!element) {
    return (
      <EmptyState
        icon={FileText}
        title="原文对照"
        description={fileLabel ? `${fileLabel} —— 该格式无行级原文，选中元素后此处显示详情` : "解析完成后，选中元素在此对照原文"}
      />
    );
  }

  return (
    <div className="flex h-full flex-col gap-3 overflow-auto">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-stone-400">选中元素</span>
        <span className="font-mono text-[11px] text-stone-400">#{element.id}</span>
      </div>

      {element.location && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-stone-400">物理定位：</span>
          <LocationBadge location={element.location} />
        </div>
      )}

      <div className="rounded-lg bg-stone-50 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-stone-700">
        {element.content || "（无文本内容）"}
      </div>

      {element.raw_content && (
        <div>
          <div className="mb-1 text-xs text-stone-400">raw_content（可渲染原文格式）</div>
          <pre className="max-h-64 overflow-auto rounded-lg bg-stone-100 p-3 font-mono text-[11px] text-stone-600">
            {element.raw_content}
          </pre>
        </div>
      )}

      {element.metadata && Object.keys(element.metadata).length > 0 && (
        <div>
          <div className="mb-1 text-xs text-stone-400">metadata</div>
          <pre className="max-h-48 overflow-auto rounded-lg bg-stone-100 p-3 font-mono text-[11px] text-stone-600">
            {JSON.stringify(element.metadata, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

export function SourceViewerSkeleton() {
  return (
    <div className="space-y-1.5">
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} className="h-5 w-full" />
      ))}
    </div>
  );
}
