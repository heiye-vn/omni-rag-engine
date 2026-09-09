/** 最近知识库记忆（localStorage，后端补 KB 列表端点后可替换数据源） */

const KEY = "rag-console:kbs";

export function loadRecentKbs(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === "string").slice(0, 10) : [];
  } catch {
    return [];
  }
}

export function rememberKb(name: string): void {
  if (typeof window === "undefined") return;
  const prev = loadRecentKbs().filter((x) => x !== name);
  try {
    window.localStorage.setItem(KEY, JSON.stringify([name, ...prev].slice(0, 10)));
  } catch {
    // localStorage 不可用时静默降级（无记忆功能）
  }
}

/** 文件条目类型占位（页面内部使用的上传状态结构） */
export interface FileEntry {
  name: string;
  size: number;
}
