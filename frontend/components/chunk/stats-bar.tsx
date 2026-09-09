"use client";

import { Card } from "@/components/ui/card";
import type { ChunkStats } from "@/hooks/use-chunk";

/** 指标条：切片总数 / 平均字符 / 最长切片 / header_path 覆盖率 */
export function StatsBar({ stats }: { stats: ChunkStats }) {
  const items = [
    { label: "切片总数", value: stats.total },
    { label: "平均字符数", value: stats.avgLength },
    { label: "最长切片", value: stats.maxLength },
    { label: "含 header_path", value: `${stats.headerPathRatio}%` },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {items.map(({ label, value }) => (
        <Card key={label} className="p-3">
          <div className="text-[11px] text-stone-500">{label}</div>
          <div className="tabular mt-0.5 text-xl font-medium text-ink">{value}</div>
        </Card>
      ))}
    </div>
  );
}
