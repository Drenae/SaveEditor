import flet as ft

from app import SaveEditorApp


def main(page: ft.Page) -> None:
    SaveEditorApp(page)


if __name__ == "__main__":
    ft.run(main)
