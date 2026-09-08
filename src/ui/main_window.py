from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SaveEditor")
        self.resize(1200, 760)
        self._current_file: Path | None = None

        self._build_menu()
        self._build_ui()
        self.statusBar().showMessage("Prêt")

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("Fichier")

        open_action = QAction("Ouvrir…", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        save_as_action = QAction("Enregistrer sous…", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self.save_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        quit_action = QAction("Quitter", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _build_ui(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        top = QHBoxLayout()
        self.file_label = QLabel("Aucun fichier chargé")
        self.file_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top.addWidget(self.file_label, 1)

        open_button = QPushButton("Ouvrir une sauvegarde")
        open_button.clicked.connect(self.open_file)
        top.addWidget(open_button)

        layout.addLayout(top)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher un champ ou une valeur…")
        self.search.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Champ", "Type", "Valeur"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.header().setStretchLastSection(True)
        self.tree.setColumnWidth(0, 320)
        self.tree.setColumnWidth(1, 150)
        layout.addWidget(self.tree, 1)

        self.setCentralWidget(root)

    def open_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Ouvrir une sauvegarde",
            "",
            "Sauvegardes (*.dat *.save *.bin);;Tous les fichiers (*.*)",
        )
        if not filename:
            return

        self._current_file = Path(filename)
        self.file_label.setText(str(self._current_file))
        self.statusBar().showMessage(f"Chargé : {self._current_file.name}")

        self.tree.clear()
        placeholder = QTreeWidgetItem([
            "NRBF",
            "BinaryFormatter",
            "Moteur de décodage en cours d'intégration",
        ])
        placeholder.setFlags(placeholder.flags() & ~Qt.ItemIsEditable)
        self.tree.addTopLevelItem(placeholder)

    def save_as(self) -> None:
        if self._current_file is None:
            QMessageBox.information(self, "SaveEditor", "Charge d'abord une sauvegarde.")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Enregistrer sous",
            str(self._current_file.with_name(self._current_file.stem + "_edited" + self._current_file.suffix)),
            "Sauvegardes (*.dat *.save *.bin);;Tous les fichiers (*.*)",
        )
        if not filename:
            return

        # Phase 0: copie byte-perfect tant qu'aucune modification n'est appliquée.
        Path(filename).write_bytes(self._current_file.read_bytes())
        self.statusBar().showMessage(f"Copie enregistrée : {Path(filename).name}")

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            self._filter_item(item, needle)

    def _filter_item(self, item: QTreeWidgetItem, needle: str) -> bool:
        own_match = not needle or any(needle in item.text(col).lower() for col in range(3))
        child_match = False
        for i in range(item.childCount()):
            if self._filter_item(item.child(i), needle):
                child_match = True
        visible = own_match or child_match
        item.setHidden(not visible)
        return visible
