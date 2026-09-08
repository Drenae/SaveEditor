from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QBrush, QColor, QFont
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

from src.save.document import (
    PathKey,
    SaveDocument,
    SaveWriteError,
    parse_value,
    value_preview,
    value_type,
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SaveEditor")
        self.resize(1280, 800)
        self._current_file: Path | None = None
        self._document: SaveDocument | None = None
        self._loading_tree = False
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

        edit_menu = self.menuBar().addMenu("Édition")
        reset_action = QAction("Restaurer la valeur sélectionnée", self)
        reset_action.setShortcut("Ctrl+R")
        reset_action.triggered.connect(self.reset_selected_value)
        edit_menu.addAction(reset_action)

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

        info = QHBoxLayout()
        self.format_label = QLabel("Format : —")
        self.class_label = QLabel("Classe : —")
        self.members_label = QLabel("Champs : —")
        self.modified_label = QLabel("Modifiés : 0")
        info.addWidget(self.format_label)
        info.addWidget(self.class_label, 1)
        info.addWidget(self.members_label)
        info.addSpacing(20)
        info.addWidget(self.modified_label)
        layout.addLayout(info)

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
        self.tree.setColumnWidth(0, 360)
        self.tree.setColumnWidth(1, 190)
        self.tree.setColumnWidth(2, 650)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree, 1)

        hint = QLabel(
            "Double-clique sur une valeur simple pour la modifier. String, Integer, Float et Boolean sont pris en charge. "
            "À l'enregistrement, chaque modification est réinjectée dans le flux NRBF puis le fichier entier est redécodé "
            "et comparé au graphe attendu avant d'être écrit. Ctrl+R restaure la valeur sélectionnée."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
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
        path = Path(filename)
        self.statusBar().showMessage(f"Décodage de {path.name}…")
        try:
            document = SaveDocument.load(path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Erreur de décodage",
                f"Impossible de décoder cette sauvegarde NRBF/BinaryFormatter.\n\n{type(exc).__name__}: {exc}",
            )
            self.statusBar().showMessage("Échec du décodage")
            return

        self._current_file = path
        self._document = document
        self.file_label.setText(str(path))
        self.format_label.setText("Format : NRBF / BinaryFormatter")
        self.class_label.setText(f"Classe : {document.root_class or 'inconnue'}")
        count = document.root_member_count
        self.members_label.setText(f"Champs : {count if count is not None else '—'}")
        self._update_modified_label()
        self._populate_tree(document.data)
        self.statusBar().showMessage(
            f"Décodé : {path.name} — {count if count is not None else '?'} champs racine"
        )

    def _populate_tree(self, data: Any) -> None:
        self._loading_tree = True
        self.tree.setUpdatesEnabled(False)
        try:
            self.tree.clear()
            if isinstance(data, dict):
                for key, value in data.items():
                    if key == "__class__":
                        continue
                    self._add_value(None, str(key), value, (str(key),))
            else:
                self._add_value(None, "Racine", data, ())
        finally:
            self.tree.setUpdatesEnabled(True)
            self._loading_tree = False

    def _add_value(self, parent: QTreeWidgetItem | None, name: str, value: Any, path: PathKey) -> QTreeWidgetItem:
        item = QTreeWidgetItem([name, value_type(value), value_preview(value)])
        item.setData(0, Qt.UserRole, path)
        editable = isinstance(value, (str, int, float, bool)) and path
        flags = item.flags()
        if editable:
            flags |= Qt.ItemIsEditable
        else:
            flags &= ~Qt.ItemIsEditable
        item.setFlags(flags)
        if parent is None:
            self.tree.addTopLevelItem(item)
        else:
            parent.addChild(item)
        if isinstance(value, list):
            for index, child in enumerate(value):
                self._add_value(item, f"[{index}]", child, path + (index,))
        elif isinstance(value, dict):
            for key, child in value.items():
                if key == "__class__":
                    continue
                self._add_value(item, str(key), child, path + (str(key),))
        self._refresh_item_style(item)
        return item

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._loading_tree or column != 2 or self._document is None:
            return
        path = item.data(0, Qt.UserRole)
        if not path:
            return
        current = self._document.get_value(path)
        if isinstance(current, (list, dict)):
            return
        try:
            new_value = parse_value(item.text(2), current)
        except Exception as exc:
            self._restore_item_text(item, current)
            QMessageBox.warning(self, "Valeur invalide", str(exc))
            return
        self._document.set_value(path, new_value)
        self._loading_tree = True
        try:
            item.setText(1, value_type(new_value))
            item.setText(2, value_preview(new_value, max_length=10000))
            self._refresh_item_style(item)
        finally:
            self._loading_tree = False
        self._update_modified_label()
        self.statusBar().showMessage(f"Valeur modifiée — {self._document.modified_count} changement(s)")

    def _restore_item_text(self, item: QTreeWidgetItem, value: Any) -> None:
        self._loading_tree = True
        try:
            item.setText(2, value_preview(value, max_length=10000))
        finally:
            self._loading_tree = False

    def _refresh_item_style(self, item: QTreeWidgetItem) -> None:
        if self._document is None:
            return
        path = item.data(0, Qt.UserRole)
        modified = bool(path and path in self._document.changes)
        font = QFont(item.font(0))
        font.setBold(modified)
        for col in range(3):
            item.setFont(col, font)
            item.setForeground(col, QBrush(QColor("#d97706")) if modified else QBrush())

    def reset_selected_value(self) -> None:
        if self._document is None:
            return
        item = self.tree.currentItem()
        if item is None:
            return
        path = item.data(0, Qt.UserRole)
        if not path or path not in self._document.changes:
            return
        self._document.reset_value(path)
        value = self._document.get_value(path)
        self._loading_tree = True
        try:
            item.setText(1, value_type(value))
            item.setText(2, value_preview(value, max_length=10000))
            self._refresh_item_style(item)
        finally:
            self._loading_tree = False
        self._update_modified_label()
        self.statusBar().showMessage("Valeur restaurée")

    def _update_modified_label(self) -> None:
        count = self._document.modified_count if self._document is not None else 0
        self.modified_label.setText(f"Modifiés : {count}")

    def save_as(self) -> None:
        if self._current_file is None or self._document is None:
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
        target = Path(filename)
        try:
            self._document.save_as(target)
        except SaveWriteError as exc:
            QMessageBox.warning(
                self,
                "Écriture refusée",
                str(exc) + "\n\nLe fichier n'a pas été écrit, afin de ne jamais produire volontairement une sauvegarde corrompue.",
            )
            self.statusBar().showMessage("Sauvegarde refusée : validation NRBF échouée")
            return
        except Exception as exc:
            QMessageBox.critical(self, "Erreur d'écriture", f"{type(exc).__name__}: {exc}")
            self.statusBar().showMessage("Échec de l'enregistrement")
            return

        if self._document.modified_count == 0:
            identical = target.read_bytes() == self._current_file.read_bytes()
            self.statusBar().showMessage(
                f"Copie enregistrée : {target.name} — byte-perfect={'oui' if identical else 'NON'}"
            )
        else:
            self.statusBar().showMessage(
                f"Sauvegarde NRBF validée : {target.name} — {self._document.modified_count} changement(s)"
            )

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
        if needle and child_match:
            item.setExpanded(True)
        return visible
