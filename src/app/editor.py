from __future__ import annotations

from pathlib import Path

import flet as ft

from app.dialogs import DialogManager
from app.value_table import ValueTableBuilder
from app.view import SaveEditorView
from save.document import SaveDocument, SaveWriteError


class SaveEditorApp:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.document: SaveDocument | None = None
        self.current_file: Path | None = None
        self.filter_text = ""

        self._configure_page()

        self.file_picker = ft.FilePicker()
        self.save_picker = ft.FilePicker()
        page.services.extend([self.file_picker, self.save_picker])

        self.dialogs = DialogManager(page)
        self.view = SaveEditorView(
            on_open=self._open,
            on_save_as=self._save_as,
            on_search_change=self._search_changed,
        )
        page.add(self.view.root)

    def _configure_page(self) -> None:
        self.page.title = "SaveEditor"
        self.page.padding = 0
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.window.width = 1280
        self.page.window.height = 820
        self.page.window.min_width = 900
        self.page.window.min_height = 600

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
        self.view.status.value = f"Décodage de {path.name}…"
        self.page.update()

        try:
            document = SaveDocument.load(path)
        except Exception as exc:
            self.dialogs.show_message(
                "Erreur de décodage",
                f"Impossible de décoder cette sauvegarde NRBF/BinaryFormatter.\n\n{type(exc).__name__}: {exc}",
            )
            self.view.status.value = "Échec du décodage"
            self.page.update()
            return

        self.current_file = path
        self.document = document
        self.view.file_label.value = str(path)
        self.view.format_label.value = "Format : NRBF / BinaryFormatter"
        self.view.class_label.value = f"Classe : {document.root_class or 'inconnue'}"
        self.view.members_label.value = (
            f"Champs : {document.root_member_count if document.root_member_count is not None else '—'}"
        )
        self._refresh()
        self.view.status.value = f"Décodé : {path.name}"
        self.page.update()

    async def _save_as(self, e: ft.Event) -> None:
        if self.document is None or self.current_file is None:
            self.dialogs.show_message("SaveEditor", "Charge d'abord une sauvegarde.")
            return

        suggested = self.current_file.stem + "_edited" + self.current_file.suffix
        selected_path = await self.save_picker.save_file(
            dialog_title="Enregistrer sous",
            file_name=suggested,
        )
        if not selected_path:
            return

        target = Path(selected_path)
        try:
            self.document.save_as(target)
        except SaveWriteError as exc:
            self.dialogs.show_message(
                "Écriture refusée",
                str(exc) + "\n\nLe fichier n'a pas été écrit afin d'éviter une sauvegarde corrompue.",
            )
            self.view.status.value = "Sauvegarde refusée : validation NRBF échouée"
        except Exception as exc:
            self.dialogs.show_message("Erreur d'écriture", f"{type(exc).__name__}: {exc}")
            self.view.status.value = "Échec de l'enregistrement"
        else:
            self.view.status.value = (
                f"Sauvegarde NRBF validée : {target.name} — "
                f"{self.document.modified_count} changement(s)"
            )
        self.page.update()

    def _search_changed(self, e: ft.Event[ft.TextField]) -> None:
        self.filter_text = (e.control.value or "").strip().lower()
        self._refresh()

    def _refresh(self) -> None:
        self.view.tree.controls.clear()
        if self.document is None:
            self.view.modified_label.value = "Modifiés : 0"
            self.page.update()
            return

        self.view.modified_label.value = f"Modifiés : {self.document.modified_count}"
        builder = ValueTableBuilder(
            document=self.document,
            filter_text=self.filter_text,
            field_width=self.view.FIELD_WIDTH,
            type_width=self.view.TYPE_WIDTH,
            on_edit=self._edit,
            on_reset=self._reset,
        )
        self.view.tree.controls.extend(builder.build_root())
        self.page.update()

    def _edit(self, path: tuple[str | int, ...]) -> None:
        if self.document is None:
            return

        def applied() -> None:
            self._refresh()
            self.view.status.value = (
                f"Valeur modifiée — {self.document.modified_count} changement(s)"
            )
            self.page.update()

        self.dialogs.show_value_editor(
            document=self.document,
            path=path,
            on_applied=applied,
        )

    def _reset(self, path: tuple[str | int, ...]) -> None:
        if self.document is None or path not in self.document.changes:
            return
        self.document.reset_value(path)
        self._refresh()
        self.view.status.value = "Valeur restaurée"
        self.page.update()
