import sys

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow


def run() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("SaveEditor")
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())
