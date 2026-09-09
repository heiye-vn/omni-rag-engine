/**
 * 后端 API 客户端 —— 统一封装 baseURL / 超时 / 错误归一化
 *
 * 后端已开启 CORS (allow_origins=["*"])，前端可直连，无需代理
 */

import type { IngestResult, Job, JobSummary, ParsedDocument, SearchResult, ChunkOut } from "./types";
import type { Provider, StoreType, Strategy } from "./constants";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const TIMEOUT_MS = 30_000;

/** 引擎 API 错误（非 2xx 响应或网络失败） */
export class EngineApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "EngineApiError";
    this.status = status;
    this.detail = detail;
  }

  /** 是否为后端不可达（网络错误 / 连接拒绝） */
  get unreachable(): boolean {
    return this.status === 0;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  let resp: Response;
  try {
    resp = await fetch(`${BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
    });
  } catch (err) {
    // 网络层失败：后端未启动 / DNS / 中断
    const reason = err instanceof Error ? err.message : String(err);
    throw new EngineApiError(0, `无法连接引擎 (${BASE_URL})，请确认已运行 uv run uvicorn app.server:app — ${reason}`);
  } finally {
    clearTimeout(timer);
  }

  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // 响应体非 JSON，保留默认信息
    }
    throw new EngineApiError(resp.status, detail);
  }
  return resp.json() as Promise<T>;
}

/** 上传 FormData 的便捷方法 */
function apiUpload<T>(path: string, form: FormData): Promise<T> {
  return apiFetch<T>(path, { method: "POST", body: form });
}

// ---------------------------------------------------------------------------- #
//  API 封装（与后端 server.py 端点一一对应）
// ---------------------------------------------------------------------------- #

export const api = {
  /** GET /health */
  health: () => apiFetch<{ status: string }>("/health"),

  /** GET / —— 服务基础信息 */
  root: () => apiFetch<{ service: string; version: string; supported_extensions_count: number }>("/"),

  /** POST /api/v1/documents/parse —— 同步解析（小文件） */
  parse(file: File, enableCleaning = true): Promise<ParsedDocument[]> {
    const form = new FormData();
    form.append("file", file);
    form.append("enable_cleaning", String(enableCleaning));
    return apiUpload("/api/v1/documents/parse", form);
  },

  /** POST /api/v1/documents/parse-and-chunk —— 同步解析并切块（小文件） */
  parseAndChunk(file: File, strategy: Strategy, enableCleaning = true): Promise<ChunkOut[]> {
    const form = new FormData();
    form.append("file", file);
    form.append("strategy", strategy);
    form.append("enable_cleaning", String(enableCleaning));
    return apiUpload("/api/v1/documents/parse-and-chunk", form);
  },

  /** POST /api/v1/jobs —— 提交异步任务（大文件），立即返回 202 */
  submitJob(
    file: File,
    kind: "parse" | "parse_and_chunk",
    opts?: { strategy?: Strategy; enableCleaning?: boolean },
  ): Promise<{ job_id: string; status: string }> {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    form.append("strategy", opts?.strategy ?? "auto");
    form.append("enable_cleaning", String(opts?.enableCleaning ?? true));
    return apiUpload("/api/v1/jobs", form);
  },

  /** GET /api/v1/jobs/{id} —— 轮询任务状态与结果 */
  getJob: (jobId: string) => apiFetch<Job>(`/api/v1/jobs/${jobId}`),

  /** GET /api/v1/jobs —— 最近任务列表 */
  listJobs: (limit = 20) => apiFetch<JobSummary[]>(`/api/v1/jobs?limit=${limit}`),

  /** POST /api/v1/knowledge-bases/{kb}/ingest —— 入库 */
  ingest(
    kb: string,
    file: File,
    opts?: { strategy?: Strategy; storeType?: StoreType; provider?: Provider; enableCleaning?: boolean },
  ): Promise<IngestResult> {
    const form = new FormData();
    form.append("file", file);
    form.append("strategy", opts?.strategy ?? "auto");
    form.append("store_type", opts?.storeType ?? "chroma");
    form.append("provider", opts?.provider ?? "auto");
    form.append("enable_cleaning", String(opts?.enableCleaning ?? true));
    return apiUpload(`/api/v1/knowledge-bases/${encodeURIComponent(kb)}/ingest`, form);
  },

  /** POST /api/v1/knowledge-bases/{kb}/search —— 相似检索 */
  search(
    kb: string,
    query: string,
    opts?: { k?: number; storeType?: StoreType; provider?: Provider },
  ): Promise<SearchResult> {
    return apiFetch(`/api/v1/knowledge-bases/${encodeURIComponent(kb)}/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        k: opts?.k ?? 4,
        store_type: opts?.storeType ?? "chroma",
        provider: opts?.provider ?? "auto",
      }),
    });
  },
};
