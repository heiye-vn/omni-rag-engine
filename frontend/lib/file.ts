/** 文件相关工具函数 */

/** 提取小写扩展名（含点），如 "test.md" → ".md" */
export function extractExt(name: string): string {
  const idx = name.lastIndexOf(".");
  return idx === -1 ? "" : name.slice(idx).toLowerCase();
}

/** 文件大小是否超过异步阈值（MB） */
export function isLargeFile(file: File, thresholdMb: number): boolean {
  return file.size > thresholdMb * 1024 * 1024;
}

/** 人类可读的文件大小 */
export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
