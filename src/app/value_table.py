from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from save.document import SaveDocument, value_preview, value_type


class ValueTableBuilder:
    def __init__(
        self,
        *,
        document: SaveDocument,
        filter_text: str,
        field_width: int,
        type_width: int,
        on_edit: Callable[[tuple[str | int, ...]], None],
        on_reset: Callable[[tuple[str | int, ...]], None],
    ) -> None:
        self.document = document
        self.filter_text = filter_text
        self.field_width = field_width
        self.type_width = type_width
        self.on_edit = on_edit
        self.on_reset = on_reset

    def build_root(self) -> list[ft.Control]:
        controls: list[ft.Control] = []
        data = self.document.data
        if isinstance(data, dict):
            for key, value in data.items():
                if key == "__class__":
                    continue
                control = self._build_value_control(str(key), value, (str(key),), 0)
                if control is not None:
                    controls.append(control)
        else:
            control = self._build_value_control("Racine", data, (), 0)
            if control is not None:
                controls.append(control)
        return controls

    def _build_value_control(
        self,
        name: str,
        value: Any,
        path: tuple[str | int, ...],
        depth: int,
    ) -> ft.Control | None:
        is_collection = isinstance(value, (list, dict))
        needle = self.filter_text
        own_text = f"{name} {value_type(value)} {value_preview(value, 10000)}".lower()
        if needle and needle not in own_text and not self._contains_match(value, needle):
            return None

        modified = path in self.document.changes
        descendant_modified = self._has_modified_descendant(path)
        accent = ft.Colors.ORANGE_400 if modified or descendant_modified else None

        if is_collection:
            if isinstance(value, list):
                entries = [(f"[{i}]", child, path + (i,)) for i, child in enumerate(value)]
                count_text = f"{len(value)} élément{'s' if len(value) != 1 else ''}"
            else:
                entries = [(str(k), child, path + (str(k),)) for k, child in value.items() if k != "__class__"]
                count_text = f"{len(entries)} champ{'s' if len(entries) != 1 else ''}"

            children: list[ft.Control] = []
            for child_name, child, child_path in entries:
                control = self._build_value_control(child_name, child, child_path, depth + 1)
                if control is not None:
                    children.append(control)

            title = self._row_content(name, value_type(value), count_text, path, depth, accent, collection=True)
            tile = ft.ExpansionTile(
                title=title,
                controls=children,
                expanded=bool(needle),
                tile_padding=ft.Padding.only(left=8, right=8),
                bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
                collapsed_bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
                shape=ft.RoundedRectangleBorder(radius=0),
                collapsed_shape=ft.RoundedRectangleBorder(radius=0),
            )
            return ft.Container(
                content=tile,
                border=ft.Border(bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.35, ft.Colors.OUTLINE_VARIANT))),
            )

        row = self._row_content(name, value_type(value), value_preview(value), path, depth, accent, collection=False)
        return ft.Container(
            content=row,
            padding=ft.Padding.symmetric(horizontal=8, vertical=5),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
            border=ft.Border(bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.35, ft.Colors.OUTLINE_VARIANT))),
        )

    def _row_content(
        self,
        name: str,
        type_name: str,
        preview: str,
        path: tuple[str | int, ...],
        depth: int,
        accent: str | None,
        collection: bool,
    ) -> ft.Control:
        modified = path in self.document.changes
        actions = ft.Container(width=88) if collection else ft.Row([
            ft.IconButton(
                ft.Icons.EDIT_OUTLINED,
                tooltip="Modifier",
                on_click=lambda e, p=path: self.on_edit(p),
                icon_size=19,
            ),
            ft.IconButton(
                ft.Icons.RESTORE,
                tooltip="Restaurer",
                on_click=lambda e, p=path: self.on_reset(p),
                disabled=not modified,
                icon_size=19,
            ),
        ], width=88, spacing=0, alignment=ft.MainAxisAlignment.END)

        return ft.Row([
            ft.Container(
                content=ft.Text(name, weight=ft.FontWeight.W_600 if collection or modified else ft.FontWeight.NORMAL, color=accent),
                padding=ft.Padding.only(left=max(0, depth - 1) * 8),
                width=self.field_width - (32 if collection else 0),
            ),
            ft.Container(
                content=ft.Text(type_name, color=accent or ft.Colors.ON_SURFACE_VARIANT),
                width=self.type_width,
            ),
            ft.Text(preview, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, color=accent),
            actions,
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _has_modified_descendant(self, path: tuple[str | int, ...]) -> bool:
        size = len(path)
        return any(changed[:size] == path for changed in self.document.changes)

    def _contains_match(self, value: Any, needle: str) -> bool:
        if not needle:
            return True
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "__class__":
                    continue
                if needle in f"{key} {value_type(child)} {value_preview(child, 10000)}".lower() or self._contains_match(child, needle):
                    return True
        elif isinstance(value, list):
            for index, child in enumerate(value):
                if needle in f"[{index}] {value_type(child)} {value_preview(child, 10000)}".lower() or self._contains_match(child, needle):
                    return True
        return False
