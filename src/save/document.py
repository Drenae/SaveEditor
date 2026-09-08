from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import nrbf


@dataclass
class SaveDocument:
    path: Path
    data: Any

    @classmethod
    def load(cls, path: str | Path) -> "SaveDocument":
        file_path = Path(path)
        with file_path.open("rb") as stream:
            data = nrbf.load(stream)
        return cls(path=file_path, data=data)

    @property
    def root_class(self) -> str | None:
        if isinstance(self.data, dict):
            value = self.data.get("__class__")
            return str(value) if value is not None else None
        return None

    @property
    def root_member_count(self) -> int | None:
        if isinstance(self.data, dict):
            return len([key for key in self.data.keys() if key != "__class__"])
        return None


def value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "Boolean"
    if isinstance(value, int):
        return "Integer"
    if isinstance(value, float):
        return "Float"
    if isinstance(value, str):
        return "String"
    if isinstance(value, list):
        return f"Array[{len(value)}]"
    if isinstance(value, dict):
        class_name = value.get("__class__")
        return str(class_name) if class_name else "Object"
    return type(value).__name__


def value_preview(value: Any, max_length: int = 180) -> str:
    if value is None:
        return "null"
    if isinstance(value, list):
        return f"{len(value)} éléments"
    if isinstance(value, dict):
        count = len([key for key in value.keys() if key != "__class__"])
        return f"{count} champs"
    if isinstance(value, bool):
        return "true" if value else "false"

    text = str(value).replace("\r", "\\r").replace("\n", "\\n")
    if len(text) > max_length:
        return text[: max_length - 1] + "…"
    return text
