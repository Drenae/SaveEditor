from __future__ import annotations

from pathlib import Path
from typing import Any

import flet as ft

from save.document import SaveDocument, SaveWriteError, format_path, parse_value, value_preview, value_type


class SaveEditorApp:
    FIELD_WIDTH = 390
    TYPE_WIDTH = 170

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.document: SaveDocument | None = None
        self.current_file: Path | None = None
        self.filter_text = ""

        page.title = "SaveEditor"
        page.padding = 0
        page.theme_mode = ft.ThemeMode.DARK
        page.window.width = 1280
        page.window.height = 820
        page.window.min_width = 900
        page.window.min_height = 600

        self.file_picker = ft.FilePicker()
        self.save_picker = ft.FilePicker()
        page.services.extend([self.file_picker, self.save_picker])

        self.file_label = ft.Text("Aucun fichier chargé", selectable=True, expand=True)
        self.format_label = ft.Text("Format : —")
        self.class_label = ft.Text("Classe : —", expand=True)
        self.members_label = ft.Text("Champs : —")
        self.modified_label = ft.Text("Modifiés : 0")
        self.status = ft.Text("Prêt", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.search = ft.TextField(
            hint_text="Rechercher un champ ou une valeur…",
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            border_radius=10,
            on_change=self._search_changed,
        )
        self.tree = ft.ListView(expand=True, spacing=0, padding=0)
        page.add(self._build_view())

    def _build_view(self) -> ft.Control:
        toolbar = ft.Row([
            self.file_label,
            ft.FilledButton("Ouvrir", icon=ft.Icons.FOLDER_OPEN, on_click=self._open),
            ft.OutlinedButton("Enregistrer sous", icon=ft.Icons.SAVE_AS, on_click=self._save_as),
        ])
        info = ft.Row([
            self.format_label,
            ft.VerticalDivider(),
            self.class_label,
            self.members_label,
            self.modified_label,
        ], spacing=12)
        header = ft.Container(
            content=ft.Column([toolbar, info, self.search], spacing=10),
            padding=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border=ft.Border(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        )
        columns = ft.Container(
            content=ft.Row([
                ft.Text("Champ", weight=ft.FontWeight.W_600, width=self.FIELD_WIDTH),
                ft.Text("Type", weight=ft.FontWeight.W_600, width=self.TYPE_WIDTH),
                ft.Text("Valeur", weight=ft.FontWeight.W_600, expand=True),
                ft.Container(width=88),
            ], spacing=8),
            padding=ft.Padding.symmetric(horizontal=16, vertical=11),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            border=ft.Border(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        )
        table = ft.Container(
            content=self.tree,
            expand=True,
            margin=ft.Margin.all(12),
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=12,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )
        footer = ft.Container(
            content=self.status,
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border=ft.Border(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        )
        return ft.Column([header, columns, table, footer], expand=True, spacing=0)

    async def _open(self, e: ft.Event) -> None:
        files = await self.file_picker.pick_files(
            dialog_title="Ouvrir une sauvegarde",
            allow_multiple=False,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["dat", "save", "bin"],
        )
        if not files or not files[0].path:
            return
        path = Path(files[0].path)
        self.status.value = f"Décodage de {path.name}…"
        self.page.update()
        try:
            document = SaveDocument.load(path)
        except Exception as exc:
            self._message("Erreur de décodage", f"Impossible de décoder cette sauvegarde NRBF/BinaryFormatter.\n\n{type(exc).__name__}: {exc}")
            self.status.value = "Échec du décodage"
            self.page.update()
            return
        self.current_file = path
        self.document = document
        self.file_label.value = str(path)
        self.format_label.value = "Format : NRBF / BinaryFormatter"
        self.class_label.value = f"Classe : {document.root_class or 'inconnue'}"
        self.members_label.value = f"Champs : {document.root_member_count if document.root_member_count is not None else '—'}"
        self._refresh()
        self.status.value = f"Décodé : {path.name}"
        self.page.update()

    async def _save_as(self, e: ft.Event) -> None:
        if self.document is None or self.current_file is None:
            self._message("SaveEditor", "Charge d'abord une sauvegarde.")
            return
        suggested = self.current_file.stem + "_edited" + self.current_file.suffix
        selected_path = await self.save_picker.save_file(dialog_title="Enregistrer sous", file_name=suggested)
        if not selected_path:
            return
        target = Path(selected_path)
        try:
            self.document.save_as(target)
        except SaveWriteError as exc:
            self._message("Écriture refusée", str(exc) + "\n\nLe fichier n'a pas été écrit afin d'éviter une sauvegarde corrompue.")
            self.status.value = "Sauvegarde refusée : validation NRBF échouée"
        except Exception as exc:
            self._message("Erreur d'écriture", f"{type(exc).__name__}: {exc}")
            self.status.value = "Échec de l'enregistrement"
        else:
            self.status.value = f"Sauvegarde NRBF validée : {target.name} — {self.document.modified_count} changement(s)"
        self.page.update()

    def _search_changed(self, e: ft.Event[ft.TextField]) -> None:
        self.filter_text = (e.control.value or "").strip().lower()
        self._refresh()

    def _refresh(self) -> None:
        self.tree.controls.clear()
        if self.document is None:
            self.modified_label.value = "Modifiés : 0"
            self.page.update()
            return
        self.modified_label.value = f"Modifiés : {self.document.modified_count}"
        data = self.document.data
        if isinstance(data, dict):
            for key, value in data.items():
                if key == "__class__":
                    continue
                control = self._build_value_control(str(key), value, (str(key),), 0)
                if control is not None:
                    self.tree.controls.append(control)
        else:
            control = self._build_value_control("Racine", data, (), 0)
            if control is not None:
                self.tree.controls.append(control)
        self.page.update()

    def _build_value_control(self, name: str, value: Any, path: tuple[str | int, ...], depth: int) -> ft.Control | None:
        is_collection = isinstance(value, (list, dict))
        needle = self.filter_text
        own_text = f"{name} {value_type(value)} {value_preview(value, 10000)}".lower()
        if needle and needle not in own_text and not self._contains_match(value, needle):
            return None

        modified = bool(self.document and path in self.document.changes)
        descendant_modified = self._has_modified_descendant(path)
        accent = ft.Colors.ORANGE_400 if modified or descendant_modified else None

        if is_collection:
            if isinstance(value, list):
                entries = [(f"[{i}]", child, path + (i,)) for i, child in enumerate(value)]
                count_text = f"{len(value)} élément{'s' if len(value) != 1 else ''}"
            else:
                entries = [(str(k), child, path + (str(k),)) for k, child in value.items() if k != "__class__"]
                count_text = f"{len(entries)} champ{'s' if len(entries) != 1 else ''}"

            children = []
            for child_name, child, child_path in entries:
                control = self._build_value_control(child_name, child, child_path, depth + 1)
                if control is not None:
                    children.append(control)

            title = self._row_content(name, value_type(value), count_text, path, depth, accent, collection=True)
            return ft.ExpansionTile(
                title=title,
                controls=children,
                expanded=bool(needle),
                tile_padding=ft.Padding.only(left=8, right=8),
                controls_padding=ft.Padding.only(left=18),
                bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
                collapsed_bgcolor=ft.Colors.SURFACE_CONTAINER_LOWEST,
                shape=ft.RoundedRectangleBorder(radius=0),
                collapsed_shape=ft.RoundedRectangleBorder(radius=0),
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
        modified = bool(self.document and path in self.document.changes)
        return ft.Row([
            ft.Container(
                content=ft.Text(name, weight=ft.FontWeight.W_600 if collection or modified else ft.FontWeight.NORMAL, color=accent),
                padding=ft.Padding.only(left=max(0, depth - 1) * 8),
                width=self.FIELD_WIDTH - (32 if collection else 0),
            ),
            ft.Container(
                content=ft.Text(type_name, color=accent or ft.Colors.ON_SURFACE_VARIANT),
                width=self.TYPE_WIDTH,
            ),
            ft.Text(preview, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, color=accent),
            ft.Row([
                ft.IconButton(
                    ft.Icons.EDIT_OUTLINED,
                    tooltip="Modifier",
                    on_click=None if collection else lambda e, p=path: self._edit(p),
                    disabled=collection,
                    icon_size=19,
                ),
                ft.IconButton(
                    ft.Icons.RESTORE,
                    tooltip="Restaurer",
                    on_click=lambda e, p=path: self._reset(p),
                    disabled=not modified,
                    icon_size=19,
                ),
            ], width=88, spacing=0, alignment=ft.MainAxisAlignment.END),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _has_modified_descendant(self, path: tuple[str | int, ...]) -> bool:
        if self.document is None:
            return False
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

    def _edit(self, path: tuple[str | int, ...]) -> None:
        if self.document is None:
            return
        current = self.document.get_value(path)
        multiline = isinstance(current, str) and len(current) > 120
        field = ft.TextField(
            value=str(current).lower() if isinstance(current, bool) else str(current),
            multiline=multiline,
            min_lines=8 if multiline else 1,
            max_lines=16 if multiline else 1,
            autofocus=True,
            expand=multiline,
        )
        length = ft.Text()

        def update_length(e=None):
            if isinstance(current, str):
                text = field.value or ""
                length.value = f"Longueur : {len(text)} caractères — {len(text.encode('utf-8'))} octets UTF-8"
                self.page.update()

        def apply(e):
            try:
                new_value = parse_value(field.value or "", current)
                self.document.set_value(path, new_value)
            except Exception as exc:
                self._message("Valeur invalide", str(exc))
                return
            self.page.pop_dialog()
            self._refresh()
            self.status.value = f"Valeur modifiée — {self.document.modified_count} changement(s)"
            self.page.update()

        if isinstance(current, str):
            field.on_change = update_length
            update_length()
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Éditer {format_path(path)}"),
            content=ft.Container(ft.Column([length, field], tight=True), width=800, height=420 if multiline else None),
            actions=[
                ft.TextButton("Annuler", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton("Appliquer", on_click=apply),
            ],
        )
        self.page.show_dialog(dialog)

    def _reset(self, path: tuple[str | int, ...]) -> None:
        if self.document is None or path not in self.document.changes:
            return
        self.document.reset_value(path)
        self._refresh()
        self.status.value = "Valeur restaurée"
        self.page.update()

    def _message(self, title: str, message: str) -> None:
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Text(message, selectable=True),
            actions=[ft.FilledButton("OK", on_click=lambda e: self.page.pop_dialog())],
        )
        self.page.show_dialog(dialog)


def main(page: ft.Page) -> None:
    SaveEditorApp(page)


if __name__ == "__main__":
    ft.run(main)
