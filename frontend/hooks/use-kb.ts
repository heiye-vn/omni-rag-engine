"use client";

import { api } from "@/lib/api-client";
import { KB_NAME_PATTERN, type Provider, type StoreType } from "@/lib/constants";
import type { IngestResult, SearchResult } from "@/lib/types";
import { useMutation } from "@tanstack/react-query";

export interface IngestVars {
  kb: string;
  file: File;
  storeType?: StoreType;
  provider?: Provider;
}

/** 入库（单文件）：kb 名称前端先行校验 */
export function useIngest() {
  return useMutation<IngestResult, Error, IngestVars>({
    mutationFn: (vars) => {
      if (!KB_NAME_PATTERN.test(vars.kb)) {
        throw new Error(
          "知识库名称仅允许 1~64 位字母、数字、下划线与连字符，且以字母或数字开头",
        );
      }
      return api.ingest(vars.kb, vars.file, {
        storeType: vars.storeType,
        provider: vars.provider,
      });
    },
  });
}

export interface SearchVars {
  kb: string;
  query: string;
  k?: number;
  storeType?: StoreType;
  provider?: Provider;
}

/** 相似度检索 */
export function useSearch() {
  return useMutation<SearchResult, Error, SearchVars>({
    mutationFn: (vars) => {
      if (!KB_NAME_PATTERN.test(vars.kb)) {
        throw new Error("知识库名称不合法，请检查后重试");
      }
      return api.search(vars.kb, vars.query, {
        k: vars.k,
        storeType: vars.storeType,
        provider: vars.provider,
      });
    },
  });
}
