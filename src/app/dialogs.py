from __future__ import annotations

from collections.abc import Callable

import flet as ft

from save.document import SaveDocument, format_path, parse_value


class DialogManager:
    def __init__(self, page: ft.Page) -> None:
        self.page = page

    def show_message(self, title: str, message: str) -> None:
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Text(message, selectable=True),
            actions=[ft.FilledButton("OK", on_click=lambda e: self.page.pop_dialog())],
        )
        self.page.show_dialog(dialog)

    def show_value_editor(
        self,
        *,
        document: SaveDocument,
        path: tuple[str | int, ...],
        on_applied: Callable[[], None],
    ) -> None:
        current = document.get_value(path)
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

        def update_length(e=None) -> None:
            if isinstance(current, str):
                text = field.value or ""
                length.value = f"Longueur : {len(text)} caractères — {len(text.encode('utf-8'))} octets UTF-8"
                self.page.update()

        def apply(e) -> None:
            try:
                new_value = parse_value(field.value or "", current)
                document.set_value(path, new_value)
            except Exception as exc:
                self.show_message("Valeur invalide", str(exc))
                return

            self.page.pop_dialog()
            on_applied()

        if isinstance(current, str):
            field.on_change = update_length
            update_length()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Éditer {format_path(path)}"),
            content=ft.Container(
                ft.Column([length, field], tight=True),
                width=800,
                height=420 if multiline else None,
            ),
            actions=[
                ft.TextButton("Annuler", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton("Appliquer", on_click=apply),
            ],
        )
        self.page.show_dialog(dialog)
