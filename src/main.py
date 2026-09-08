from __future__ import annotations

from pathlib import Path
from typing import Any

import flet as ft

from save.document import SaveDocument, SaveWriteError, format_path, parse_value, value_preview, value_type


class SaveEditorApp:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.document: SaveDocument | None = None
        self.current_file: Path | None = None
        self.selected_path: tuple[str | int, ...] | None = None
        self.filter_text = ""

        page.title = "SaveEditor"
        page.padding = 0
        page.theme_mode = ft.ThemeMode.DARK
        page.window.width = 1280
        page.window.height = 820
        page.window.min_width = 900
        page.window.min_height = 600

        self.file_picker = ft.FilePicker(on_result=self._file_picked)
        self.save_picker = ft.FilePicker(on_result=self._save_picked)
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
            on_change=self._search_changed,
        )
        self.tree = ft.ListView(expand=True, spacing=2, padding=0)

        page.add(self._build_view())

    def _build_view(self) -> ft.Control:
        toolbar = ft.Row(
            [
                self.file_label,
                ft.FilledButton("Ouvrir", icon=ft.Icons.FOLDER_OPEN, on_click=self._open),
                ft.OutlinedButton("Enregistrer sous", icon=ft.Icons.SAVE_AS, on_click=self._save_as),
            ]
        )
        info = ft.Row(
            [self.format_label, ft.VerticalDivider(), self.class_label, self.members_label, self.modified_label],
            spacing=12,
        )
        header = ft.Container(
            content=ft.Column([toolbar, info, self.search], spacing=10),
            padding=16,
            border=ft.Border(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        )
        columns = ft.Container(
            content=ft.Row(
                [
                    ft.Text("Champ", weight=ft.FontWeight.BOLD, width=390),
                    ft.Text("Type", weight=ft.FontWeight.BOLD, width=170),
                    ft.Text("Valeur", weight=ft.FontWeight.BOLD, expand=True),
                ]
            ),
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            bgcolor=ft.Colors.SURFACE_CONTAINER,
        )
        footer = ft.Container(
            content=self.status,
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            border=ft.Border(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        )
        return ft.Column([header, columns, ft.Container(self.tree, expand=True, padding=8), footer], expand=True, spacing=0)

    def _open(self, e: ft.Event) -> None:
        self.file_picker.pick_files(
            dialog_title="Ouvrir une sauvegarde",
            allow_multiple=False,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["dat", "save", "bin"],
        )

    def _file_picked(self, e: ft.FilePickerResultEvent) -> None:
        if not e.files:
            return
        path = Path(e.files[0].path)
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
        self.selected_path = None
        self.file_label.value = str(path)
        self.format_label.value = "Format : NRBF / BinaryFormatter"
        self.class_label.value = f"Classe : {document.root_class or 'inconnue'}"
        self.members_label.value = f"Champs : {document.root_member_count if document.root_member_count is not None else '—'}"
        self._refresh()
        self.status.value = f"Décodé : {path.name}"
        self.page.update()

    def _save_as(self, e: ft.Event) -> None:
        if self.document is None or self.current_file is None:
            self._message("SaveEditor", "Charge d'abord une sauvegarde.")
            return
        suggested = self.current_file.stem + "_edited" + self.current_file.suffix
        self.save_picker.save_file(dialog_title="Enregistrer sous", file_name=suggested)

    def _save_picked(self, e: ft.FilePickerResultEvent) -> None:
        if not e.path or self.document is None:
            return
        target = Path(e.path)
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
                if key != "__class__":
                    self._append_value(str(key), value, (str(key),), 0)
        else:
            self._append_value("Racine", data, (), 0)
        self.page.update()

    def _append_value(self, name: str, value: Any, path: tuple[str | int, ...], depth: int) -> bool:
        children: list[tuple[str, Any, tuple[str | int, ...]]] = []
        if isinstance(value, list):
            children = [(f"[{i}]", child, path + (i,)) for i, child in enumerate(value)]
        elif isinstance(value, dict):
            children = [(str(k), child, path + (str(k),)) for k, child in value.items() if k != "__class__"]

        needle = self.filter_text
        own_text = f"{name} {value_type(value)} {value_preview(value, 10000)}".lower()
        own_match = not needle or needle in own_text
        descendant_match = self._contains_match(value, needle) if needle and children else False
        if needle and not own_match and not descendant_match:
            return False

        modified = path in self.document.changes if self.document and path else False
        color = ft.Colors.ORANGE_600 if modified else None
        row = ft.Row(
            [
                ft.Container(ft.Text(name, weight=ft.FontWeight.BOLD if modified else None, color=color), padding=ft.Padding.only(left=depth * 22), width=390),
                ft.Text(value_type(value), width=170, color=color),
                ft.Text(value_preview(value), expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, color=color),
                ft.IconButton(ft.Icons.EDIT, tooltip="Modifier", on_click=lambda e, p=path: self._edit(p), disabled=isinstance(value, (list, dict)) or value is None),
                ft.IconButton(ft.Icons.RESTORE, tooltip="Restaurer", on_click=lambda e, p=path: self._reset(p), disabled=not modified),
            ],
            spacing=6,
        )
        self.tree.controls.append(ft.Container(row, padding=ft.Padding.symmetric(vertical=3, horizontal=6)))
        for child_name, child, child_path in children:
            self._append_value(child_name, child, child_path, depth + 1)
        return True

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
            actions=[ft.TextButton("Annuler", on_click=lambda e: self.page.pop_dialog()), ft.FilledButton("Appliquer", on_click=apply)],
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
