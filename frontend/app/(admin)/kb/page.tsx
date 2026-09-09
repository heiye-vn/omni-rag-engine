"use client";

import { LocationBadge } from "@/components/parse/location-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input, Select } from "@/components/ui/input";
import { UploadZone } from "@/components/parse/upload-zone";
import { useIngest, useSearch } from "@/hooks/use-kb";
import {
  KB_NAME_PATTERN,
  PROVIDERS,
  STORE_TYPES,
  type Provider,
  type StoreType,
} from "@/lib/constants";
import { formatSize } from "@/lib/file";
import type { FileEntry } from "@/lib/kb-local";
import { loadRecentKbs, rememberKb } from "@/lib/kb-local";
import { Database, Search } from "lucide-react";
import { useCallback, useState } from "react";

interface UploadItem {
  file: File;
  status: "pending" | "uploading" | "success" | "failed";
  detail?: string;
}

export default function KnowledgeBasePage() {
  // 左栏（入库）状态
  const [kb, setKb] = useState("");
  const [storeType, setStoreType] = useState<StoreType>("chroma");
  const [items, setItems] = useState<UploadItem[]>([]);
  const ingest = useIngest();

  // 右栏（检索）状态
  const [query, setQuery] = useState("");
  const [k, setK] = useState(4);
  const [provider, setProvider] = useState<Provider>("auto");
  const [searchKb, setSearchKb] = useState("");
  const [recentKbs, setRecentKbs] = useState<string[]>([]);
  const search = useSearch();

  // 首次渲染后加载最近 KB（避免 SSR/localStorage 不匹配）
  useState(() => setRecentKbs(loadRecentKbs()));

  const kbValid = KB_NAME_PATTERN.test(kb);

  const addFiles = useCallback((files: File[]) => {
    setItems((prev) => [...prev, ...files.map((file) => ({ file, status: "pending" as const }))]);
  }, []);

  /** 顺序上传所有 pending 文件 */
  const uploadAll = async () => {
    if (!kbValid) return;
    rememberKb(kb);
    setRecentKbs(loadRecentKbs());
    setSearchKb((prev) => prev || kb);

    for (let i = 0; i < items.length; i++) {
      if (items[i].status !== "pending") continue;
      setItems((prev) =>
        prev.map((it, idx) => (idx === i ? { ...it, status: "uploading" } : it)),
      );
      try {
        const res = await ingest.mutateAsync({
          kb,
          file: items[i].file,
          storeType,
          provider,
        });
        setItems((prev) =>
          prev.map((it, idx) =>
            idx === i
              ? { ...it, status: "success", detail: `${res.document_count} 文档 · ${res.chunk_count} 切片` }
              : it,
          ),
        );
      } catch (err) {
        setItems((prev) =>
          prev.map((it, idx) =>
            idx === i ? { ...it, status: "failed", detail: String(err instanceof Error ? err.message : err) } : it,
          ),
        );
      }
    }
  };

  const activeSearchKb = searchKb || kb;

  return (
    <div className="mx-auto grid max-w-6xl grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-5">
      {/* 左栏：入库面板 */}
      <Card className="self-start">
        <CardHeader>
          <div>
            <CardTitle>知识库入库</CardTitle>
            <CardDescription>上传文档切块后写入指定知识库的向量数据库</CardDescription>
          </div>
          <div className="flex size-8 items-center justify-center rounded-lg bg-brand-50">
            <Database className="size-4 text-brand-600" />
          </div>
        </CardHeader>

        <label className="mb-1 block text-xs font-medium text-stone-600">知识库标识</label>
        <Input
          value={kb}
          onChange={(e) => setKb(e.target.value)}
          placeholder="如 demo、company-wiki"
          className={kb && !kbValid ? "border-red-400 focus:border-red-400 focus:ring-red-400/20" : undefined}
        />
        {kb && !kbValid && (
          <p className="mt-1 text-[11px] text-red-600">
            仅允许字母、数字、下划线、连字符，以字母或数字开头
          </p>
        )}

        <div className="mt-3 grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-stone-600">向量库</label>
            <Select value={storeType} onChange={(e) => setStoreType(e.target.value as StoreType)}>
              {STORE_TYPES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-stone-600">Embedding</label>
            <Select value={provider} onChange={(e) => setProvider(e.target.value as Provider)}>
              {PROVIDERS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Select>
          </div>
        </div>

        <div className="mt-4">
          <UploadZone onFile={(f) => addFiles([f])} hint="支持多文件，逐个入库并显示状态" />
        </div>

        {items.length > 0 && (
          <div className="mt-3 space-y-1.5">
            {items.map((it, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between gap-2 rounded-lg border border-stone-200 bg-paper px-3 py-2"
              >
                <div className="min-w-0">
                  <div className="truncate text-xs font-medium text-ink">{it.file.name}</div>
                  <div className="tabular text-[11px] text-stone-400">
                    {formatSize(it.file.size)}
                    {it.detail ? ` · ${it.detail}` : ""}
                  </div>
                </div>
                <Badge
                  dot
                  tone={
                    it.status === "success"
                      ? "green"
                      : it.status === "failed"
                        ? "red"
                        : it.status === "uploading"
                          ? "amber"
                          : "neutral"
                  }
                >
                  {it.status === "uploading" ? "入库中" : it.status === "success" ? "成功" : it.status === "failed" ? "失败" : "待上传"}
                </Badge>
              </div>
            ))}
          </div>
        )}

        <Button className="mt-4 w-full" onClick={uploadAll} disabled={!kbValid || items.length === 0 || ingest.isPending}>
          {ingest.isPending ? "入库中…" : `开始入库 (${items.filter((i) => i.status === "pending").length})`}
        </Button>

        {recentKbs.length > 0 && (
          <div className="mt-4">
            <div className="mb-1.5 text-xs text-stone-400">最近使用的知识库</div>
            <div className="flex flex-wrap gap-1.5">
              {recentKbs.map((name) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => {
                    setKb(name);
                    setSearchKb(name);
                  }}
                  className="rounded-md bg-brand-50 px-2.5 py-1 font-mono text-[11px] text-brand-700 ring-1 ring-inset ring-brand-200 transition-colors hover:bg-brand-100"
                >
                  {name}
                </button>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* 右栏：检索面板 */}
      <Card className="self-start">
        <CardHeader>
          <div>
            <CardTitle>相似度检索</CardTitle>
            <CardDescription>对知识库发起 Top-K 向量检索，结果携带溯源定位</CardDescription>
          </div>
          <div className="flex size-8 items-center justify-center rounded-lg bg-brand-50">
            <Search className="size-4 text-brand-600" />
          </div>
        </CardHeader>

        <div className="flex gap-2">
          <Input
            value={activeSearchKb}
            onChange={(e) => setSearchKb(e.target.value)}
            placeholder="知识库标识"
            className="w-36 shrink-0 font-mono text-xs"
          />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && query.trim() && KB_NAME_PATTERN.test(activeSearchKb)) {
                search.mutate({ kb: activeSearchKb, query: query.trim(), k, storeType, provider });
              }
            }}
            placeholder="输入查询内容，如「切块策略」"
          />
          <Button
            onClick={() => search.mutate({ kb: activeSearchKb, query: query.trim(), k, storeType, provider })}
            disabled={!query.trim() || !KB_NAME_PATTERN.test(activeSearchKb) || search.isPending}
          >
            {search.isPending ? "检索中…" : "检索"}
          </Button>
        </div>

        <div className="mt-3 flex items-center gap-3">
          <span className="text-xs text-stone-500">Top-K</span>
          <input
            type="range"
            min={1}
            max={100}
            value={k}
            onChange={(e) => setK(Number(e.target.value))}
            className="flex-1 accent-brand-600"
          />
          <span className="tabular w-8 rounded bg-brand-50 py-0.5 text-center text-xs font-medium text-brand-700">{k}</span>
        </div>

        {search.error && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
            {search.error.message}
          </div>
        )}

        {search.data && (
          <div className="mt-4">
            <div className="mb-2 text-xs text-stone-400">
              命中 <span className="font-medium text-brand-700">{search.data.total}</span> 条 · query: {search.data.query}
            </div>
            <div className="space-y-2">
              {search.data.results.map((chunk, i) => (
                <SearchResultCard key={i} chunk={chunk} rank={i + 1} />
              ))}
            </div>
          </div>
        )}

        {!search.data && !search.error && !search.isPending && (
          <EmptyState
            icon={Search}
            title="等待检索"
            description="先在左侧完成知识库入库，再输入查询验证 Top-K 召回效果"
            className="mt-4"
          />
        )}
      </Card>
    </div>
  );
}

/** 检索结果卡片：内容 + metadata 溯源徽章 */
function SearchResultCard({
  chunk,
  rank,
}: {
  chunk: { page_content: string; metadata: Record<string, unknown> };
  rank: number;
}) {
  const meta = chunk.metadata ?? {};
  const location =
    meta.start_line != null || meta.page_number != null || meta.selector != null || meta.start_time != null
      ? {
          start_line: meta.start_line as number | undefined,
          end_line: meta.end_line as number | undefined,
          page_number: meta.page_number as number | undefined,
          bbox: meta.bbox as [number, number, number, number] | undefined,
          selector: meta.selector as string | undefined,
          start_time: meta.start_time as number | undefined,
          end_time: meta.end_time as number | undefined,
        }
      : undefined;

  return (
    <div className="rounded-lg border border-stone-200/80 bg-white p-3 transition-colors hover:border-brand-200">
      <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
        <span className="flex size-5 items-center justify-center rounded bg-accent-50 font-mono text-[11px] font-medium text-accent-700">
          {rank}
        </span>
        {meta.file_name ? <Badge tone="purple">{String(meta.file_name)}</Badge> : null}
        {meta.element_type ? <Badge tone="teal">{String(meta.element_type)}</Badge> : null}
        {meta.header_path ? (
          <Badge tone="blue" className="max-w-48 truncate" title={String(meta.header_path)}>
            {String(meta.header_path)}
          </Badge>
        ) : null}
        <LocationBadge location={location} />
      </div>
      <p className="line-clamp-4 text-xs leading-relaxed text-stone-700">{chunk.page_content}</p>
    </div>
  );
}
