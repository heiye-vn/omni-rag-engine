/**
 * 前端类型定义 —— 与后端 app/models.py 的 dataclass 一一对应
 *
 * 注意：后端 to_dict() 会过滤 None 值，因此所有字段均为可选
 */

/** 元素在原文档中的精准位置定位（用于高亮与原文对照） */
export interface Location {
  page_number?: number;
  bbox?: [number, number, number, number];
  start_line?: number;
  end_line?: number;
  start_char?: number;
  end_char?: number;
  selector?: string;
  start_time?: number;
  end_time?: number;
}

/** 文档中的一个内容单元 */
export interface Element {
  id: string;
  type: string; // heading | paragraph | table | code | image | list_item | blockquote | ...
  content: string;
  raw_content?: string;
  location?: Location;
  metadata?: Record<string, unknown>;
}

/** 解析后的完整文档 */
export interface ParsedDocument {
  file_name: string;
  file_type: string;
  raw_text?: string;
  file_path?: string;
  total_pages?: number;
  metadata?: Record<string, unknown>;
  elements: Element[];
}

/** 切片节点（切块产物） */
export interface ChunkOut {
  page_content: string;
  metadata: Record<string, unknown>;
}

/** 相似度检索响应 */
export interface SearchResult {
  query: string;
  total: number;
  results: ChunkOut[];
}

/** 知识库入库结果 */
export interface IngestResult {
  knowledge_base: string;
  store_type: string;
  document_count: number;
  chunk_count: number;
  detail?: unknown;
}

/** 异步任务状态 */
export type JobStatus = "queued" | "running" | "succeeded" | "failed";

/** 异步任务类型 */
export type JobKind = "parse" | "parse_and_chunk";

/** 异步任务快照（GET /api/v1/jobs/{id}） */
export interface Job {
  job_id: string;
  kind: JobKind;
  file_name: string;
  status: JobStatus;
  strategy?: string | null;
  created_at: number;
  started_at?: number | null;
  finished_at?: number | null;
  error?: string | null;
  result?: ParsedDocument[] | ChunkOut[] | null;
}

/** 异步任务列表项（GET /api/v1/jobs，不含 result） */
export type JobSummary = Omit<Job, "result">;
