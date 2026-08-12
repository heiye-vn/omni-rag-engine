import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Self


@dataclass
class Location:
    """
    元素在原文档中的精准位置定位信息，用于前端高亮与原文对照
    """

    page_number: int | None = None  # 页码 (1-indexed，适用于 PDF, PPTX, 多页文档)
    bbox: list[float] | None = (
        None  # 坐标盒子 [x0, y0, x1, y1] (适用于 PDF, OCR, 扫描件)
    )
    start_line: int | None = (
        None  # 起始行号 (1-indexed，适用于 Markdown, TXT, Code, CSV)
    )
    end_line: int | None = None  # 结束行号
    start_char: int | None = None  # 字符起始偏移 (Char Offset)
    end_char: int | None = None  # 字符结束偏移
    selector: str | None = None  # DOM 路径 / XPath (适用于 HTML, DOCX, XML)
    start_time: float | None = None  # 起始时间戳 (秒，适用于音频/视频 ASR)
    end_time: float | None = None  # 结束时间戳 (秒)

    def to_dict(self) -> dict[str, Any]:
        """过滤掉 None 值的干净字典格式"""
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def default_element_id() -> str:
    """默认生成 12 位的 UUID 用于切片追踪"""
    return uuid.uuid4().hex[:12]


@dataclass
class Element:
    """
    文档中的一个内容单元（支持切片对照、原文高亮与可渲染序列化）
    """

    type: str  # 元素类型，如 paragraph, heading, table, image, code, list_item 等
    content: str  # 规范化提取后的纯文本内容
    id: str = field(default_factory=default_element_id)  # 元素唯一标识符 (UUID)
    raw_content: str | None = (
        None  # 原始原生内容 (必须是可被前端渲染的 HTML/XML/Markdown 代码片段)
    )
    location: Location | None = None  # 原文位置定位数据 (用于前端高亮与原文对照)
    metadata: dict[str, Any] = field(default_factory=dict)  # 扩展元数据

    def to_dict(self) -> dict[str, Any]:
        res = {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "raw_content": self.raw_content,
            "location": self.location.to_dict() if self.location else None,
            "metadata": self.metadata,
        }
        return {k: v for k, v in res.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        loc_data = data.get("location")
        location = Location.from_dict(loc_data) if isinstance(loc_data, dict) else None
        return cls(
            id=data.get("id", default_element_id()),
            type=data["type"],
            content=data["content"],
            raw_content=data.get("raw_content"),
            location=location,
            metadata=data.get("metadata", {}),
        )


@dataclass
class ParsedDocument:
    """
    解析后的完整文档模型（支持全量原文对比与传输）
    """

    file_name: str  # 文件名
    file_type: str  # 文件类型格式，如 docx, pdf, markdown, txt 等
    raw_text: str | None = None  # 完整原文文本 (适用于纯文本/Markdown 对照)
    file_path: str | None = None  # 原始文件存储/访问路径 (适用于 PDF/音视频/图片渲染)
    total_pages: int | None = None  # 总页数/总时长
    metadata: dict[str, Any] = field(default_factory=dict)  # 文档级别元数据
    elements: list[Element] = field(default_factory=list)  # 解析后的元素节点列表

    def to_dict(self) -> dict[str, Any]:
        """导出为可以直接 json.dumps() 的干净字典格式"""
        res = {
            "file_name": self.file_name,
            "file_type": self.file_type,
            "raw_text": self.raw_text,
            "file_path": self.file_path,
            "total_pages": self.total_pages,
            "metadata": self.metadata,
            "elements": [elem.to_dict() for elem in self.elements],
        }
        return {k: v for k, v in res.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        elements = [Element.from_dict(elem) for elem in data.get("elements", [])]
        return cls(
            file_name=data["file_name"],
            file_type=data["file_type"],
            raw_text=data.get("raw_text"),
            file_path=data.get("file_path"),
            total_pages=data.get("total_pages"),
            metadata=data.get("metadata", {}),
            elements=elements,
        )

    def to_langchain_documents(self) -> list[Any]:
        """
        将 ParsedDocument 中的所有 Element 节点转换为标准 LangChain Document 列表

        每个 LangChain Document 的结构：
          - page_content: Element 节点的纯文本/Markdown/表格数据
          - metadata: 集中包含 source, file_name, file_type, element_id, element_type,
                      raw_content (用于前端渲染) 以及 location (定位/高亮坐标) 等元数据
        """
        try:
            from langchain_core.documents import Document as LCDocument
        except ImportError:

            @dataclass
            class LCDocument:
                page_content: str
                metadata: dict = field(default_factory=dict)

        docs = []
        for elem in self.elements:
            meta = {
                "source": self.file_path or self.file_name,
                "file_name": self.file_name,
                "file_type": self.file_type,
                "element_id": elem.id,
                "element_type": elem.type,
            }
            if elem.raw_content:
                meta["raw_content"] = elem.raw_content
            if elem.location:
                meta.update(elem.location.to_dict())
            if elem.metadata:
                meta.update(elem.metadata)

            docs.append(LCDocument(page_content=elem.content, metadata=meta))

        return docs

    def clean(self, pipeline: Any = None) -> "ParsedDocument":
        """
        对 ParsedDocument 中的 Element 列表执行数据清洗管道

        Args:
            pipeline: 自定义的 CleanerPipeline 实例；若为 None 则默认使用 CleanerPipeline.default()

        Returns:
            包含清洗后 Element 节点的新 ParsedDocument 实例
        """
        if pipeline is None:
            from app.cleaners.pipeline import CleanerPipeline
            pipeline = CleanerPipeline.default()

        cleaned_elements = pipeline.clean(self.elements)

        return ParsedDocument(
            file_name=self.file_name,
            file_type=self.file_type,
            raw_text=self.raw_text,
            file_path=self.file_path,
            total_pages=self.total_pages,
            metadata=self.metadata,
            elements=cleaned_elements,
        )

    def split(self, chunker: Any = None, strategy: str = "auto") -> Any:
        """
        对 ParsedDocument 进行智能切块

        Args:
            chunker: 自定义的切块器实例；若为 None 则默认使用 AutoChunker()
            strategy: 切片策略，可选 'auto', 'sliding_window', 'parent_child', 'header_aware'

        Returns:
            切块后的 LangChain Document 列表或 (child_docs, parent_store) 元组
        """
        if chunker is None:
            from app.chunkers.auto import AutoChunker
            chunker = AutoChunker()

        return chunker.split_document(self, strategy=strategy)

    def describe_images(self, captioner: Any = None, provider: str = "auto", **kwargs: Any) -> "ParsedDocument":
        """
        自动遍历 ParsedDocument 中的所有图片节点，使用多模态视觉大模型 (Vision LLM) 为图片生成自然语言文本描述

        Args:
            captioner: 自定义的 BaseCaptioner 实例；若为 None 则通过 ImageCaptioner 自动匹配
            provider: 供应商名称 ("auto", "dashscope", "openai", "ollama", "mock")

        Returns:
            包含更新后图片描述的新 ParsedDocument 实例
        """
        from app.captioners.helper import describe_document_images
        return describe_document_images(self, captioner=captioner, provider=provider, **kwargs)

    def enrich_context(
        self,
        enricher: Any = None,
        inject_file_name: bool = True,
        inject_header_path: bool = True,
        separator: str = " > ",
    ) -> "ParsedDocument":
        """
        自动为文档中所有非标题节点缝合包含文件名与层级标题大纲路径链的上下文前缀，大幅提升 Contextual Retrieval 召回率

        Args:
            enricher: 自定义语义增强器实例；若为 None 则默认使用 ContextPrefixInjector
            inject_file_name: 是否注入文件名
            inject_header_path: 是否注入标题大纲路径
            separator: 大纲层级分隔符

        Returns:
            上下文前缀增强后的新 ParsedDocument 实例
        """
        if enricher is None:
            from app.enrichers import ContextPrefixInjector
            enricher = ContextPrefixInjector(
                inject_file_name=inject_file_name,
                inject_header_path=inject_header_path,
                separator=separator,
            )
        return enricher.enrich(self)

    def enrich_tables(
        self,
        enhancer: Any = None,
        associate_caption: bool = True,
        generate_kv_summary: bool = True,
    ) -> "ParsedDocument":
        """
        自动关联表格节点上方的标题说明，并抽取 JSON 键值对行记录，极大增强大模型复杂表格问答准确度

        Args:
            enhancer: 自定义表格增强器实例；若为 None 则默认使用 TableEnhancer
            associate_caption: 是否自动关联表格上方标题说明
            generate_kv_summary: 是否提取 Key-Value 行数据 JSON

        Returns:
            表格自解释增强后的新 ParsedDocument 实例
        """
        if enhancer is None:
            from app.enrichers import TableEnhancer
            enhancer = TableEnhancer(
                associate_caption=associate_caption,
                generate_kv_summary=generate_kv_summary,
            )
        return enhancer.enrich(self)

    def to_vectorstore(
        self,
        store_type: str = "chroma",
        chunk_strategy: str = "auto",
        embeddings: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        一键端到端处理：自动将当前 ParsedDocument 切块、计算向量并持久化写入指定的向量数据库

        Args:
            store_type: 目标向量数据库 ('chroma', 'faiss', 'milvus', 'pgvector', 'qdrant')
            chunk_strategy: 切块策略 ('auto', 'sliding_window', 'parent_child', 'header_aware')
            embeddings: 自定义 Embedding 引擎；若为 None 则通过 EmbeddingsFactory 自动识别

        Returns:
            写入成功后的 VectorStore 实例或数据路径
        """
        from app.vectorstores import VectorStoreFactory

        # 1. 智能切块导出 LangChain Documents
        docs = self.split(strategy=chunk_strategy)

        # 2. 统一路由获取 VectorStore 适配器并批量写入
        store_adapter = VectorStoreFactory.get_vectorstore(
            store_type=store_type,
            embeddings=embeddings,
            **kwargs,
        )

        return store_adapter.add_documents(docs)
