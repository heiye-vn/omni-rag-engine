from abc import ABC, abstractmethod

from app.models import ParsedDocument


class BaseParser(ABC):

    @abstractmethod
    def parse(self, file_path: str) -> ParsedDocument:
        pass
