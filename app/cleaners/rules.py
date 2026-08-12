import re
import unicodedata
from app.models import Element
from .base import BaseCleaner


class ControlCharCleaner(BaseCleaner):
    """剔除不可见 Unicode 控制字符与 NULL 乱码字符"""

    _CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

    def clean_element(self, element: Element) -> Element | None:
        if element.content:
            element.content = self._CONTROL_CHAR_RE.sub("", element.content)
        if element.raw_content:
            element.raw_content = self._CONTROL_CHAR_RE.sub("", element.raw_content)
        return element


class WhitespaceCleaner(BaseCleaner):
    """全半角 Unicode 归一化，规范化连续冗余空格与无意义空行"""

    def clean_element(self, element: Element) -> Element | None:
        # 表格或代码块保持格式，不合并内部连续多格缩进
        if element.type in ("code", "table"):
            return element

        if element.content:
            # NFKC 全半角归一化
            text = unicodedata.normalize("NFKC", element.content)
            # 按行清理每行前后空格并压缩同行多余空格
            lines = [re.sub(r"[ \t]+", " ", line.strip()) for line in text.splitlines()]
            text = "\n".join(lines)
            # 压缩多余的连续换行符 (超过 2 个换行转为 2 个换行)
            text = re.sub(r"\n{3,}", "\n\n", text)
            element.content = text.strip()

        return element


class PIIMaskerCleaner(BaseCleaner):
    """敏感隐私信息脱敏（手机号、身份证号、电子邮箱）"""

    # 中国手机号正则
    _PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
    # 身份证正则
    _ID_CARD_RE = re.compile(r"(?<!\d)([1-9]\d{5})\d{8}(\d{3}[\dXx])(?!\d)")
    # 电子邮箱正则
    _EMAIL_RE = re.compile(r"([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")

    def clean_element(self, element: Element) -> Element | None:
        if element.content:
            element.content = self._mask_text(element.content)
        return element

    @classmethod
    def _mask_text(cls, text: str) -> str:
        # 手机号脱敏: 13812345678 -> 138****5678
        text = cls._PHONE_RE.sub(r"\1****\2", text)
        # 身份证号脱敏: 110101199003072345 -> 110101********2345
        text = cls._ID_CARD_RE.sub(r"\1********\2", text)
        # 邮箱脱敏: user@example.com -> u***r@example.com
        def _mask_email(match):
            name, domain = match.group(1), match.group(2)
            if len(name) <= 2:
                masked_name = name[0] + "*"
            else:
                masked_name = name[0] + "*" * (len(name) - 2) + name[-1]
            return f"{masked_name}@{domain}"

        text = cls._EMAIL_RE.sub(_mask_email, text)
        return text


class LengthFilterCleaner(BaseCleaner):
    """过滤缺乏语义价值的极短文本或全标点字符节点"""

    def __init__(self, min_length: int = 3, filter_punctuation_only: bool = True):
        self.min_length = min_length
        self.filter_punctuation_only = filter_punctuation_only
        # 标点符号正则
        self._punct_re = re.compile(r"^[^\w\u4e00-\u9fa5]+$")

    def clean_element(self, element: Element) -> Element | None:
        # 图片、表格、代码、分隔线不按纯文本字数过滤
        if element.type in ("image", "table", "code", "hr"):
            return element

        content = element.content.strip() if element.content else ""

        # 1. 过滤字数少于最小阈值的文本
        if len(content) < self.min_length:
            return None

        # 2. 过滤全是标点符号的节点 (如 "...", "---", "###")
        if self.filter_punctuation_only and self._punct_re.match(content):
            return None

        return element
