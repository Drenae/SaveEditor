from __future__ import annotations

import io
import math
import struct
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
    length_start: int
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
            return len([key for key in self.data if key != "__class__"])
        return None

    @property
    def modified_count(self) -> int:
        return len(self.changes)

    def get_value(self, path: PathKey) -> Any:
        return _get_path(self.data, path)

    def get_original_value(self, path: PathKey) -> Any:
        return _get_path(self.original_data, path)

    def set_value(self, path: PathKey, value: Any) -> None:
        if not path:
            raise ValueError("La racine ne peut pas être remplacée.")
        _set_path(self.data, path, value)
        original = self.get_original_value(path)
        if _values_equal(value, original):
            self.changes.pop(path, None)
        else:
            self.changes[path] = Change(path=path, original=original, value=value)

    def reset_value(self, path: PathKey) -> None:
        self.set_value(path, deepcopy(self.get_original_value(path)))

    def save_as(self, target: str | Path) -> None:
        """Apply edits directly to the original NRBF stream and verify each edit.

        The writer never accepts a guessed offset. For every possible binary occurrence
        of the original value, it creates a candidate stream, decodes it again with the
        NRBF parser and keeps the candidate only when the *whole decoded object graph*
        is exactly the graph expected after that edit. This makes duplicate values safe.

        Supported editable leaves: String, Boolean, Integer and Float. Strings may
        change UTF-8 length because the BinaryObjectString 7-bit length prefix is rebuilt.
        """
        target_path = Path(target)
        raw = self.path.read_bytes()

        if not self.changes:
            target_path.write_bytes(raw)
            return

        expected = deepcopy(self.original_data)

        # Stable graph order matters only for reproducibility; every result is validated.
        for change in self.changes.values():
            _set_path(expected, change.path, change.value)
            raw = self._apply_verified_change(raw, change, expected)

        # Final full-graph verification before touching the destination file.
        decoded = _decode(raw)
        if not _graphs_equal(decoded, self.data):
            raise SaveWriteError(
                "La validation finale du graphe NRBF a échoué. Aucun fichier n'a été écrit."
            )

        target_path.write_bytes(raw)

    def _apply_verified_change(self, raw: bytes, change: Change, expected: Any) -> bytes:
        old = change.original
        new = change.value
        label = format_path(change.path)

        if isinstance(old, str) and isinstance(new, str):
            candidates = _string_patch_candidates(raw, old, new)
        elif isinstance(old, bool) and isinstance(new, bool):
            candidates = _primitive_patch_candidates(raw, old, new, kind="bool")
        elif isinstance(old, int) and not isinstance(old, bool) and isinstance(new, int) and not isinstance(new, bool):
            candidates = _primitive_patch_candidates(raw, old, new, kind="int")
        elif isinstance(old, float) and isinstance(new, (float, int)) and not isinstance(new, bool):
            candidates = _primitive_patch_candidates(raw, old, float(new), kind="float")
        else:
            raise SaveWriteError(
                f"{label} : type non pris en charge par l'éditeur ({type(old).__name__})."
            )

        if not candidates:
            raise SaveWriteError(
                f"{label} : aucune représentation NRBF candidate de la valeur originale n'a été trouvée."
            )

        # A bad candidate generally fails decoding or changes another path. Only a
        # candidate reproducing the complete expected graph is accepted.
        valid: list[bytes] = []
        for candidate in candidates:
            try:
                decoded = _decode(candidate)
            except Exception:
                continue
            if _graphs_equal(decoded, expected):
                valid.append(candidate)
                if len(valid) > 1:
                    break

        if not valid:
            raise SaveWriteError(
                f"{label} : aucune occurrence n'a produit exactement le graphe attendu. "
                "La modification a été refusée pour éviter de corrompre la sauvegarde."
            )
        if len(valid) > 1:
            raise SaveWriteError(
                f"{label} : plusieurs écritures binaires produisent le même graphe. "
                "La modification est ambiguë et a été refusée."
            )
        return valid[0]


def _decode(raw: bytes) -> Any:
    return nrbf.load(io.BytesIO(raw))


def _get_path(data: Any, path: PathKey) -> Any:
    value = data
    for part in path:
        value = value[part]
    return value


def _set_path(data: Any, path: PathKey, value: Any) -> None:
    container = data
    for part in path[:-1]:
        container = container[part]
    container[path[-1]] = value


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


def _graphs_equal(left: Any, right: Any) -> bool:
    if isinstance(left, float) and isinstance(right, float):
        if math.isnan(left) and math.isnan(right):
            return True
        return left == right
    if type(left) is not type(right):
        # nrbf can expose a numeric edit as int/float-compatible in a few primitive
        # cases; numeric equality is sufficient here as long as bool is excluded.
        if isinstance(left, (int, float)) and not isinstance(left, bool) and isinstance(right, (int, float)) and not isinstance(right, bool):
            return left == right
        return False
    if isinstance(left, dict):
        if left.keys() != right.keys():
            return False
        return all(_graphs_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_graphs_equal(a, b) for a, b in zip(left, right))
    return left == right


def _values_equal(left: Any, right: Any) -> bool:
    return _graphs_equal(left, right)


def _string_patch_candidates(raw: bytes, old: str, new: str) -> list[bytes]:
    old_bytes = old.encode("utf-8")
    new_bytes = new.encode("utf-8")
    if old == "":
        return []

    candidates: list[bytes] = []
    for location in _find_binary_object_string_records(raw, old_bytes):
        replacement = _encode_7bit_int(len(new_bytes)) + new_bytes
        candidate = raw[: location.length_start] + replacement + raw[location.payload_end :]
        candidates.append(candidate)
    return candidates


def _primitive_patch_candidates(raw: bytes, old: Any, new: Any, kind: str) -> list[bytes]:
    encodings: list[tuple[bytes, bytes]] = []

    if kind == "bool":
        encodings.append((b"\x01" if old else b"\x00", b"\x01" if new else b"\x00"))
    elif kind == "int":
        # BinaryFormatter primitive integral types are little-endian. Try all widths
        # compatible with both values; the graph-verification step identifies the real one.
        for fmt, minimum, maximum in (
            ("<b", -128, 127),
            ("<B", 0, 255),
            ("<h", -32768, 32767),
            ("<H", 0, 65535),
            ("<i", -(2**31), 2**31 - 1),
            ("<I", 0, 2**32 - 1),
            ("<q", -(2**63), 2**63 - 1),
            ("<Q", 0, 2**64 - 1),
        ):
            if minimum <= old <= maximum and minimum <= new <= maximum:
                encodings.append((struct.pack(fmt, old), struct.pack(fmt, new)))
    elif kind == "float":
        for fmt in ("<f", "<d"):
            try:
                old_bytes = struct.pack(fmt, old)
                new_bytes = struct.pack(fmt, new)
            except (OverflowError, struct.error):
                continue
            # Only keep representations that round-trip to the value decoded by nrbf.
            roundtrip = struct.unpack(fmt, old_bytes)[0]
            if roundtrip == old:
                encodings.append((old_bytes, new_bytes))
    else:
        return []

    # Remove identical encoding pairs (signed/unsigned often produce the same bytes).
    unique_pairs: list[tuple[bytes, bytes]] = []
    seen_pairs: set[tuple[bytes, bytes]] = set()
    for pair in encodings:
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            unique_pairs.append(pair)

    candidates: list[bytes] = []
    seen_candidate_hashes: set[bytes] = set()

    for old_bytes, new_bytes in unique_pairs:
        if old_bytes == new_bytes:
            continue
        start = 0
        occurrences = 0
        while True:
            pos = raw.find(old_bytes, start)
            if pos < 0:
                break
            occurrences += 1
            # Very common one-byte/zero patterns can have thousands of matches. We do
            # not guess: cap brute-force work and let the user know when a field cannot
            # be located safely from raw primitive bytes alone.
            if occurrences > 2500:
                break
            candidate = raw[:pos] + new_bytes + raw[pos + len(old_bytes) :]
            marker = candidate[pos : pos + len(new_bytes)] + pos.to_bytes(8, "little")
            if marker not in seen_candidate_hashes:
                seen_candidate_hashes.add(marker)
                candidates.append(candidate)
            start = pos + 1

    return candidates


def _find_binary_object_string_records(data: bytes, payload: bytes) -> list[_StringRecordLocation]:
    result: list[_StringRecordLocation] = []
    search_from = 0
    while True:
        payload_start = data.find(payload, search_from)
        if payload_start < 0:
            break
        for prefix_size in range(1, 6):
            length_start = payload_start - prefix_size
            record_start = length_start - 5
            if record_start < 0 or data[record_start] != 0x06:
                continue
            try:
                decoded_length, consumed = _decode_7bit_int(data, length_start)
            except ValueError:
                continue
            if consumed == prefix_size and decoded_length == len(payload) and length_start + consumed == payload_start:
                result.append(
                    _StringRecordLocation(
                        length_start=length_start,
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
        raise ValueError("Une valeur null ne peut pas encore changer de type.")
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
        count = len([key for key in value if key != "__class__"])
        return f"{count} champs"
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).replace("\r", "\\r").replace("\n", "\\n")
    if len(text) > max_length:
        return text[: max_length - 1] + "…"
    return text
