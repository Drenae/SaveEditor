from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import nrbf

PathKey = tuple[str | int, ...]


class SaveWriteError(RuntimeError):
    pass


@dataclass
class Change:
    path: PathKey
    original: Any
    value: Any


@dataclass
class SaveDocument:
    path: Path
    data: Any
    original_data: Any
    changes: dict[PathKey, Change] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "SaveDocument":
        file_path = Path(path)
        with file_path.open("rb") as stream:
            data = nrbf.load(stream)
        return cls(path=file_path, data=data, original_data=deepcopy(data))

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

    @property
    def modified_count(self) -> int:
        return len(self.changes)

    def get_value(self, path: PathKey) -> Any:
        value = self.data
        for part in path:
            value = value[part]
        return value

    def get_original_value(self, path: PathKey) -> Any:
        value = self.original_data
        for part in path:
            value = value[part]
        return value

    def set_value(self, path: PathKey, value: Any) -> None:
        if not path:
            raise ValueError("La racine ne peut pas être remplacée.")

        container = self.data
        for part in path[:-1]:
            container = container[part]
        container[path[-1]] = value

        original = self.get_original_value(path)
        if value == original:
            self.changes.pop(path, None)
        else:
            self.changes[path] = Change(path=path, original=original, value=value)

    def reset_value(self, path: PathKey) -> None:
        self.set_value(path, deepcopy(self.get_original_value(path)))

    def save_as(self, target: str | Path) -> None:
        """Write the document while preserving the original NRBF stream.

        Phase 2 writer: unchanged documents are byte-perfect copies. Edited strings
        are patched in-place only when their UTF-8 payload has the same byte length
        and occurs exactly once in the original stream. This is deliberately strict:
        ambiguous/unsafe changes are refused instead of producing a corrupt save.
        """
        target_path = Path(target)
        raw = bytearray(self.path.read_bytes())

        if not self.changes:
            target_path.write_bytes(raw)
            return

        unsupported: list[str] = []

        for change in self.changes.values():
            old = change.original
            new = change.value

            if not isinstance(old, str) or not isinstance(new, str):
                unsupported.append(f"{format_path(change.path)} : {type(old).__name__}")
                continue

            old_bytes = old.encode("utf-8")
            new_bytes = new.encode("utf-8")
            if len(old_bytes) != len(new_bytes):
                unsupported.append(
                    f"{format_path(change.path)} : longueur UTF-8 {len(old_bytes)} -> {len(new_bytes)}"
                )
                continue

            positions = _find_all(raw, old_bytes)
            if len(positions) != 1:
                unsupported.append(
                    f"{format_path(change.path)} : valeur trouvée {len(positions)} fois dans le flux"
                )
                continue

            pos = positions[0]
            raw[pos : pos + len(old_bytes)] = new_bytes

        if unsupported:
            details = "\n".join(f"- {item}" for item in unsupported)
            raise SaveWriteError(
                "Certaines modifications ne peuvent pas encore être écrites de façon sûre :\n" + details
            )

        target_path.write_bytes(raw)


def _find_all(data: bytes | bytearray, needle: bytes) -> list[int]:
    if not needle:
        return []
    result: list[int] = []
    start = 0
    while True:
        pos = data.find(needle, start)
        if pos < 0:
            return result
        result.append(pos)
        start = pos + 1


def format_path(path: PathKey) -> str:
    parts: list[str] = []
    for part in path:
        if isinstance(part, int):
            parts.append(f"[{part}]")
        elif parts:
            parts.append("." + part)
        else:
            parts.append(part)
    return "".join(parts)


def parse_value(text: str, original: Any) -> Any:
    if isinstance(original, bool):
        lowered = text.strip().lower()
        if lowered in {"true", "1", "yes", "oui"}:
            return True
        if lowered in {"false", "0", "no", "non"}:
            return False
        raise ValueError("Valeur booléenne attendue : true ou false.")
    if isinstance(original, int) and not isinstance(original, bool):
        return int(text.strip(), 0)
    if isinstance(original, float):
        return float(text.strip().replace(",", "."))
    if isinstance(original, str):
        return text
    if original is None:
        if text.strip().lower() in {"null", "none", ""}:
            return None
        raise ValueError("Cette valeur null n'est pas encore éditable vers un autre type.")
    raise ValueError(f"Type non éditable : {type(original).__name__}")


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
