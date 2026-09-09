"use client";

import { Button } from "@/components/ui/button";
import { ACCEPT_ATTR, ASYNC_THRESHOLD_MB, HEAVY_EXTENSIONS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { extractExt } from "@/lib/file";
import { useRef, useState, type DragEvent } from "react";

/**
 * 拖拽上传区：accept 由后端支持扩展名生成；
 * >ASYNC_THRESHOLD_MB 自动走异步任务（由调用方决定），重依赖格式给出提示
 */
export function UploadZone({
  onFile,
  disabled,
  hint,
}: {
  onFile: (file: File) => void;
  disabled?: boolean;
  hint?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const heavyHint = (file: File) =>
    HEAVY_EXTENSIONS.has(extractExt(file.name))
      ? "音视频依赖 Whisper 转写，解析可能较慢"
      : undefined;

  const handleFile = (file: File | undefined) => {
    if (!file || disabled) return;
    onFile(file);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    handleFile(e.dataTransfer.files?.[0]);
  };

  return (
    <div className="space-y-1.5">
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "group cursor-pointer rounded-xl border border-dashed p-6 text-center transition-colors",
          dragging
            ? "border-brand-400 bg-brand-50"
            : "border-stone-300 bg-paper hover:border-brand-300 hover:bg-brand-50/50",
          disabled && "pointer-events-none opacity-50",
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_ATTR}
          className="hidden"
          onChange={(e) => {
            handleFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <div className={cn("mx-auto mb-2 flex size-9 items-center justify-center rounded-lg transition-colors", dragging ? "bg-brand-100" : "bg-stone-100 group-hover:bg-brand-100")}>
          <svg className={cn("size-4", dragging ? "text-brand-600" : "text-stone-400 group-hover:text-brand-600")} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>
        </div>
        <div className="text-xs font-medium text-stone-600">拖拽文件到此处，或点击选择</div>
        <div className="mt-1 text-[11px] text-stone-400">
          {hint ?? `支持 37+ 格式 · 超过 ${ASYNC_THRESHOLD_MB}MB 自动转为异步任务`}
        </div>
      </div>
    </div>
  );
}

/** 上传按钮（与 UploadZone 配套，供表单底部触发） */
export function UploadButton({
  onClick,
  pending,
  children,
}: {
  onClick: () => void;
  pending?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Button onClick={onClick} disabled={pending} className="w-full">
      {pending ? "解析中…" : children}
    </Button>
  );
}
