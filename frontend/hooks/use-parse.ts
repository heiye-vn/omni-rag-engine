"use client";

import { api } from "@/lib/api-client";
import type { ParsedDocument } from "@/lib/types";
import { useMutation } from "@tanstack/react-query";

/** 同步解析（小文件 ≤5MB）：上传 → ParsedDocument[] */
export function useParse() {
  return useMutation({
    mutationFn: (file: File) => api.parse(file),
  });
}
