from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import nrbf

PathKey = tuple[str | int, ...]


class SaveWriteError(RuntimeError):
    pass


@dataclass
class Change:
    path: PathKey
    original: Any
    value: Any


@dataclass(frozen=True)
class _StringRecordLocation:
    record_start: int
    length_start: int
    payload_start: int
    payload_end: int


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
        """Write a modified save while preserving the original NRBF graph.

        Current writer guarantees:
        - no changes -> byte-perfect copy;
        - BinaryObjectString values are patched by their decoded object path;
        - duplicate strings are supported by matching the Nth decoded leaf with the
          Nth real BinaryObjectString record carrying that exact value;
        - string UTF-8 length may change: the NRBF 7-bit length prefix is rebuilt;
        - unsupported primitive edits are refused rather than guessed.

        This deliberately edits only the serialized records that we can identify
        and validate structurally. It does not reserialize the whole object graph.
        """
        target_path = Path(target)
        original_raw = self.path.read_bytes()

        if not self.changes:
            target_path.write_bytes(original_raw)
            return

        patches: list[tuple[int, int, bytes, str]] = []
        unsupported: list[str] = []

        # String records can be identified reliably because BinaryObjectString is:
        # RecordType(0x06), ObjectId(Int32 LE), Length(7-bit), UTF-8 payload.
        for change in self.changes.values():
            old = change.original
            new = change.value

            if not isinstance(old, str) or not isinstance(new, str):
                unsupported.append(
                    f"{format_path(change.path)} : écriture {type(old).__name__} pas encore supportée"
                )
                continue

            old_bytes = old.encode("utf-8")
            new_bytes = new.encode("utf-8")
            locations = _find_binary_object_string_records(original_raw, old_bytes)
            matching_paths = [
                path
                for path, value in _iter_leaf_values(self.original_data)
                if isinstance(value, str) and value == old
            ]

            if change.path not in matching_paths:
                unsupported.append(
                    f"{format_path(change.path)} : chemin introuvable dans l'objet original"
                )
                continue

            occurrence = matching_paths.index(change.path)
            if len(locations) != len(matching_paths):
                unsupported.append(
                    f"{format_path(change.path)} : {len(matching_paths)} occurrence(s) décodée(s), "
                    f"{len(locations)} enregistrement(s) NRBF validé(s)"
                )
                continue
            if occurrence >= len(locations):
                unsupported.append(
                    f"{format_path(change.path)} : occurrence NRBF #{occurrence} absente"
                )
                continue

            location = locations[occurrence]
            replacement = _encode_7bit_int(len(new_bytes)) + new_bytes
            patches.append(
                (
                    location.length_start,
                    location.payload_end,
                    replacement,
                    format_path(change.path),
                )
            )

        if unsupported:
            details = "\n".join(f"- {item}" for item in unsupported)
            raise SaveWriteError(
                "Certaines modifications ne peuvent pas encore être écrites de façon sûre :\n" + details
            )

        # Overlap would mean our path-to-record mapping is inconsistent. Refuse.
        ordered = sorted(patches, key=lambda p: p[0])
        for previous, current in zip(ordered, ordered[1:]):
            if previous[1] > current[0]:
                raise SaveWriteError(
                    "Deux modifications NRBF se chevauchent : "
                    f"{previous[3]} et {current[3]}"
                )

        # Apply from the end so variable-length strings cannot invalidate earlier offsets.
        raw = bytearray(original_raw)
        for start, end, replacement, _ in sorted(patches, key=lambda p: p[0], reverse=True):
            raw[start:end] = replacement

        # Validate the produced stream immediately with the same parser used on load.
        # If it cannot be decoded, nothing is written to disk.
        import io

        try:
            decoded = nrbf.load(io.BytesIO(bytes(raw)))
        except Exception as exc:
            raise SaveWriteError(
                f"Le flux NRBF modifié ne se redécode pas : {type(exc).__name__}: {exc}"
            ) from exc

        # Also verify every edited path now resolves to the requested value.
        validation_errors: list[str] = []
        for change in self.changes.values():
            if not isinstance(change.original, str):
                continue
            try:
                actual = _get_path(decoded, change.path)
            except Exception as exc:
                validation_errors.append(
                    f"{format_path(change.path)} : chemin illisible après écriture ({exc})"
                )
                continue
            if actual != change.value:
                validation_errors.append(
                    f"{format_path(change.path)} : attendu {change.value!r}, obtenu {actual!r}"
                )

        if validation_errors:
            raise SaveWriteError(
                "Validation après écriture échouée :\n"
                + "\n".join(f"- {item}" for item in validation_errors)
            )

        target_path.write_bytes(raw)


def _get_path(data: Any, path: PathKey) -> Any:
    value = data
    for part in path:
        value = value[part]
    return value


def _iter_leaf_values(value: Any, path: PathKey = ()) -> Iterable[tuple[PathKey, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "__class__":
                continue
            yield from _iter_leaf_values(child, path + (str(key),))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_leaf_values(child, path + (index,))
        return
    yield path, value


def _find_binary_object_string_records(data: bytes, payload: bytes) -> list[_StringRecordLocation]:
    """Locate validated BinaryObjectString records carrying exactly payload.

    We search payload occurrences, then prove that immediately before each payload
    there is a valid NRBF BinaryObjectString header and a 7-bit length equal to the
    payload length. This avoids replacing arbitrary matching bytes elsewhere.
    """
    if not payload:
        # Empty BinaryObjectString payloads have no bytes to search for. Refuse for now.
        return []

    result: list[_StringRecordLocation] = []
    search_from = 0
    while True:
        payload_start = data.find(payload, search_from)
        if payload_start < 0:
            break

        # NRBF 7-bit encoded Int32 uses at most 5 bytes. Try all possible prefix sizes.
        for prefix_size in range(1, 6):
            length_start = payload_start - prefix_size
            record_start = length_start - 5  # 1 byte record type + 4 byte object id
            if record_start < 0 or data[record_start] != 0x06:
                continue

            try:
                decoded_length, consumed = _decode_7bit_int(data, length_start)
            except ValueError:
                continue

            if consumed != prefix_size or decoded_length != len(payload):
                continue
            if length_start + consumed != payload_start:
                continue

            result.append(
                _StringRecordLocation(
                    record_start=record_start,
                    length_start=length_start,
                    payload_start=payload_start,
                    payload_end=payload_start + len(payload),
                )
            )
            break

        search_from = payload_start + 1

    return result


def _decode_7bit_int(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    for index in range(5):
        pos = offset + index
        if pos >= len(data):
            raise ValueError("Préfixe 7-bit tronqué")
        byte = data[pos]
        value |= (byte & 0x7F) << shift
        if byte & 0x80 == 0:
            return value, index + 1
        shift += 7
    raise ValueError("Préfixe 7-bit invalide")


def _encode_7bit_int(value: int) -> bytes:
    if value < 0:
        raise ValueError("Une longueur NRBF ne peut pas être négative")
    encoded = bytearray()
    while value >= 0x80:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value & 0x7F)
    return bytes(encoded)


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
