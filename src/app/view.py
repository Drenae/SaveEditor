from __future__ import annotations

from collections.abc import Callable

import flet as ft


class SaveEditorView:
    FIELD_WIDTH = 390
    TYPE_WIDTH = 170

    def __init__(
        self,
        *,
        on_open: Callable,
        on_save_as: Callable,
        on_search_change: Callable,
    ) -> None:
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
            on_change=on_search_change,
        )
        self.tree = ft.ListView(expand=True, spacing=0, padding=0)

        self.root = self._build(on_open=on_open, on_save_as=on_save_as)

    def _build(self, *, on_open: Callable, on_save_as: Callable) -> ft.Control:
        toolbar = ft.Row([
            self.file_label,
            ft.FilledButton("Ouvrir", icon=ft.Icons.FOLDER_OPEN, on_click=on_open),
            ft.OutlinedButton("Enregistrer sous", icon=ft.Icons.SAVE_AS, on_click=on_save_as),
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
