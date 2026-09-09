"use client";

import { LocationBadge } from "@/components/parse/location-badge";
import { Badge } from "@/components/ui/badge";
import type { ChunkOut } from "@/lib/types";
import { STRATEGY_LABELS, type Strategy } from "@/lib/constants";
import { useState } from "react";

function pickLocation(meta: Record<string, unknown>) {
  // chunk metadata 是扁平化的 location 字段（start_line/end_line 等直接平铺）
  if (meta.start_line == null && meta.page_number == null && meta.selector == null && meta.start_time == null) {
    return undefined;
  }
  return {
    start_line: meta.start_line as number | undefined,
    end_line: meta.end_line as number | undefined,
    page_number: meta.page_number as number | undefined,
    bbox: meta.bbox as [number, number, number, number] | undefined,
    selector: meta.selector as string | undefined,
    start_time: meta.start_time as number | undefined,
    end_time: meta.end_time as number | undefined,
  };
}

/** 切片卡片：策略徽章 + 序号 + 字符数 + header_path 面包屑 + 内容展开 + 定位徽章 */
export function ChunkCard({
  chunk,
  index,
  strategy,
}: {
  chunk: ChunkOut;
  index: number;
  strategy?: Strategy;
}) {
  const [expanded, setExpanded] = useState(false);
  const headerPath = chunk.metadata?.header_path as string | undefined;
  const content = chunk.page_content;

  return (
    <div className="rounded-xl border border-stone-200/80 bg-white p-4 transition-colors hover:border-brand-200">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <span className="flex size-5 items-center justify-center rounded bg-brand-50 font-mono text-[11px] font-medium text-brand-700">
          {index + 1}
        </span>
        {strategy && <Badge tone="brand">{STRATEGY_LABELS[strategy]}</Badge>}
        <LocationBadge location={pickLocation(chunk.metadata)} />
        <span className="tabular ml-auto text-[11px] text-stone-400">{content.length} 字符</span>
      </div>

      {headerPath && (
        <div className="mb-2 flex items-center gap-1 text-[11px] font-medium text-brand-700">
          {headerPath.split(">").map((seg, i) => (
            <span key={i} className={i > 0 ? "text-stone-400" : undefined}>
              {i > 0 && <span className="mr-1 text-stone-300">›</span>}
              {seg.trim()}
            </span>
          ))}
        </div>
      )}

      <p
        className={
          expanded
            ? "whitespace-pre-wrap text-xs leading-relaxed text-stone-700"
            : "line-clamp-3 text-xs leading-relaxed text-stone-700"
        }
      >
        {content}
      </p>
      {content.length > 150 && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-1.5 text-[11px] font-medium text-brand-600 hover:text-brand-700 hover:underline"
        >
          {expanded ? "收起" : "展开全文"}
        </button>
      )}
    </div>
  );
}
