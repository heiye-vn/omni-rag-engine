import hashlib
import re
from collections import defaultdict
from typing import Any

from app.models import Element
from .base import BaseCleaner


class HeaderFooterCleaner(BaseCleaner):
    """
    跨页页眉页脚智能过滤器：
    基于 Location(page_number, bbox=[x0, y0, x1, y1]) 定位，
    识别出现在页面顶部 (y0 <= max_header_y) 或底部 (y1 >= min_footer_y) 的跨页高频重复文本，自动剔除页眉页脚噪声。
    """

    def __init__(
        self,
        max_header_y: float = 0.15,
        min_footer_y: float = 0.85,
        frequency_threshold: float = 0.25,
    ):
        self.max_header_y = max_header_y
        self.min_footer_y = min_footer_y
        self.frequency_threshold = frequency_threshold

    def clean(self, elements: list[Element]) -> list[Element]:
        if not elements:
            return []

        # 1. 按位置收集顶部与底部的候选页眉页脚节点
        # page_occurrences[text_norm] = set(page_numbers)
        page_occurrences: dict[str, set[int]] = defaultdict(set)
        total_pages = set()

        for elem in elements:
            loc = elem.location
            if loc and loc.page_number:
                total_pages.add(loc.page_number)
                bbox = loc.bbox
                if bbox and len(bbox) == 4:
                    y0, y1 = bbox[1], bbox[3]
                    # 判断是否属于顶部页眉或底部页脚区域
                    if y0 <= self.max_header_y or y1 >= self.min_footer_y:
                        norm_text = self._normalize_text(elem.content)
                        if norm_text:
                            page_occurrences[norm_text].add(loc.page_number)

        num_total_pages = len(total_pages)
        if num_total_pages < 2:
            # 单页文档不进行页眉页脚过滤
            return elements

        # 2. 计算出现频次高于阈值的噪声文本
        noise_texts: set[str] = set()
        for norm_text, page_set in page_occurrences.items():
            freq = len(page_set) / num_total_pages
            if len(page_set) >= 2 and freq >= self.frequency_threshold:
                noise_texts.add(norm_text)

        # 3. 过滤掉被判定为页眉页脚的节点
        cleaned_elements: list[Element] = []
        for elem in elements:
            loc = elem.location
            if loc and loc.bbox and len(loc.bbox) == 4:
                y0, y1 = loc.bbox[1], loc.bbox[3]
                if y0 <= self.max_header_y or y1 >= self.min_footer_y:
                    norm_text = self._normalize_text(elem.content)
                    if norm_text in noise_texts:
                        continue
            cleaned_elements.append(elem)

        return cleaned_elements

    @staticmethod
    def _normalize_text(text: str) -> str:
        """将包含动词页码 (如 '第 3 页', 'Page 5') 的文本归一化为通用特征"""
        s = text.strip().lower()
        # 去除所有空白字符
        s = re.sub(r"\s+", "", s)
        # 将页码数字转换为占位符 #，如 "第1页" 归一化为 "第#页"
        s = re.sub(r"\d+", "#", s)
        return s.strip()


class SimHashDeduplicator(BaseCleaner):
    """
    基于 Exact Match 与 64 位 SimHash 海明距离的重复文本切片去重器：
    自动剔除精确重复或语义极度相似的垃圾段落与切片。
    """

    def __init__(self, distance_threshold: int = 10, hash_bits: int = 64):
        self.distance_threshold = distance_threshold
        self.hash_bits = hash_bits

    def clean(self, elements: list[Element]) -> list[Element]:
        seen_texts: set[str] = set()
        seen_hashes: list[int] = []
        cleaned_elements: list[Element] = []

        for elem in elements:
            text = elem.content.strip()
            if not text:
                continue

            norm_text = re.sub(r"\s+", "", text.lower())

            # 1. 精确重复检查
            if norm_text in seen_texts:
                continue

            # 2. 忽略极短文本 (小于 6 字符不参与 SimHash 近重复去重)
            if len(norm_text) < 6:
                seen_texts.add(norm_text)
                cleaned_elements.append(elem)
                continue

            v_hash = self._simhash(norm_text)

            # 3. 海明距离计算近重复
            is_duplicate = False
            for existing_hash in seen_hashes:
                dist = self._hamming_distance(v_hash, existing_hash)
                if dist <= self.distance_threshold:
                    is_duplicate = True
                    break

            if not is_duplicate:
                seen_texts.add(norm_text)
                seen_hashes.append(v_hash)
                cleaned_elements.append(elem)

        return cleaned_elements

    def _simhash(self, text: str) -> int:
        """计算文本的 64 位 SimHash 值"""
        tokens = self._tokenize(text)
        v = [0] * self.hash_bits

        for token in tokens:
            # 使用 md5 哈希将 token 映射为 64 位整数
            t_hash = int(hashlib.md5(token.encode("utf-8")).hexdigest()[:16], 16)
            for i in range(self.hash_bits):
                bitmask = 1 << i
                if t_hash & bitmask:
                    v[i] += 1
                else:
                    v[i] -= 1

        fingerprint = 0
        for i in range(self.hash_bits):
            if v[i] > 0:
                fingerprint |= 1 << i

        return fingerprint

    @staticmethod
    def _hamming_distance(h1: int, h2: int) -> int:
        """计算两个 SimHash 的海明距离 (二进制异或后 1 的个数)"""
        x = h1 ^ h2
        return bin(x).count("1")

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """简易字符 2-gram / 3-gram 分词器"""
        s = re.sub(r"\s+", "", text.lower())
        if len(s) <= 3:
            return [s]
        tokens = []
        for i in range(len(s) - 1):
            tokens.append(s[i : i + 2])
        return tokens
