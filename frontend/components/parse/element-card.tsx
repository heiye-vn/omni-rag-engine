"use client";

import { LocationBadge } from "@/components/parse/location-badge";
import { TypeBadge } from "@/components/parse/type-badge";
import { cn } from "@/lib/utils";
import type { Element } from "@/lib/types";
import { useState } from "react";

/** Element 卡片：类型/定位徽章 + 内容预览 + raw_content 折叠查看 */
export function ElementCard({
  element,
  selected,
  onSelect,
}: {
  element: Element;
  selected: boolean;
  onSelect: () => void;
}) {
  const [showRaw, setShowRaw] = useState(false);

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full rounded-lg border p-3 text-left transition-colors",
        selected
          ? "border-brand-400 bg-brand-50/60 ring-1 ring-brand-300"
          : "border-stone-200 bg-white hover:border-brand-200 hover:bg-brand-50/30",
      )}
    >
      <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
        <TypeBadge type={element.type} />
        <LocationBadge location={element.location} />
        <span className="tabular ml-auto text-[11px] text-stone-400">{element.content.length} 字符</span>
      </div>

      <p className="line-clamp-3 text-xs leading-relaxed text-stone-700">
        {element.content || <span className="text-stone-300">（无文本内容）</span>}
      </p>

      {element.raw_content && (
        <div className="mt-2">
          <span
            role="button"
            tabIndex={0}
            className="text-[11px] font-medium text-brand-600 hover:text-brand-700 hover:underline"
            onClick={(e) => {
              e.stopPropagation();
              setShowRaw((v) => !v);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.stopPropagation();
                setShowRaw((v) => !v);
              }
            }}
          >
            {showRaw ? "收起原文格式" : "查看原文格式 (raw_content)"}
          </span>
          {showRaw && (
            <pre className="mt-1.5 max-h-48 overflow-auto rounded-md bg-stone-100 p-2 font-mono text-[11px] leading-relaxed text-stone-600">
              {element.raw_content}
            </pre>
          )}
        </div>
      )}
    </button>
  );
}
