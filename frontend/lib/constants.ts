/**
 * 常量镜像 —— 与后端 app/factory.py / app/chunkers / app/vectorstores 对齐
 *
 * 后端新增格式或策略时需同步更新此文件
 */

import type { JobKind } from "./types";

/** 支持的文件扩展名（来源：app/factory.py get_supported_extensions()） */
export const SUPPORTED_EXTENSIONS = [
  ".txt", ".log",
  ".md", ".markdown",
  ".docx", ".xlsx", ".xls", ".pptx",
  ".pdf",
  ".html", ".htm",
  ".csv", ".tsv", ".json",
  ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp",
  ".mp3", ".wav", ".flac", ".m4a", ".ogg", ".wma", ".aac",
  ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v",
] as const;

/** 上传 input 的 accept 属性值 */
export const ACCEPT_ATTR = SUPPORTED_EXTENSIONS.join(",");

/** 重依赖格式（Whisper / OCR），上传前给出提示 */
export const HEAVY_EXTENSIONS = new Set([
  ".mp3", ".wav", ".flac", ".m4a", ".ogg", ".wma", ".aac",
  ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v",
]);

/** 超过此大小 (MB) 的文件自动走异步任务路径 */
export const ASYNC_THRESHOLD_MB = 5;

/** 切块策略 */
export const STRATEGIES = ["auto", "sliding_window", "parent_child", "header_aware"] as const;
export type Strategy = (typeof STRATEGIES)[number];

export const STRATEGY_LABELS: Record<Strategy, string> = {
  auto: "Auto 智能路由",
  sliding_window: "滑动窗口",
  parent_child: "父子块",
  header_aware: "标题层级",
};

/** 向量库类型 */
export const STORE_TYPES = ["chroma", "faiss", "milvus", "pgvector", "qdrant"] as const;
export type StoreType = (typeof STORE_TYPES)[number];

/** Embedding 供应商 */
export const PROVIDERS = ["auto", "dashscope", "mock"] as const;
export type Provider = (typeof PROVIDERS)[number];

/** 任务类型 */
export const JOB_KINDS: JobKind[] = ["parse", "parse_and_chunk"];

/** Element 类型 → 徽章配色（tailwind class，墨青色系，去蓝紫） */
export const ELEMENT_TYPE_COLORS: Record<string, string> = {
  heading: "bg-brand-100 text-brand-800 ring-brand-200",
  paragraph: "bg-cyan-50 text-cyan-800 ring-cyan-200",
  table: "bg-green-50 text-green-700 ring-green-200",
  code: "bg-stone-100 text-stone-600 ring-stone-200",
  image: "bg-accent-50 text-accent-700 ring-accent-200",
  list_item: "bg-brand-50 text-brand-700 ring-brand-200",
  blockquote: "bg-orange-50 text-orange-800 ring-orange-200",
};

export const DEFAULT_TYPE_COLOR = "bg-stone-100 text-stone-600 ring-stone-200";

/** 知识库标识合法性（与后端 _validate_kb_name 一致） */
export const KB_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;
