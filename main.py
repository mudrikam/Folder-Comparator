from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QLabel,
    QLineEdit, QPushButton, QHBoxLayout, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar, QStyle, QStatusBar, QMessageBox
)
from PySide6.QtGui import QIcon, QBrush, QColor, QPalette
from PySide6.QtCore import Qt, Signal, QObject, Slot, QThread
import sys
import os
import shutil
import ctypes
from datetime import datetime

import qtawesome as qta

def populate_table(folder, table_widget):
    if not folder:
        table_widget.setRowCount(0)
        return set()
    if not os.path.exists(folder):
        QMessageBox.warning(None, "Folder not found", f"Folder not found: {folder}")
        table_widget.setRowCount(0)
        return set()
    if not os.path.isdir(folder):
        QMessageBox.warning(None, "Not a folder", f"Path is not a directory: {folder}")
        table_widget.setRowCount(0)
        return set()
    if not os.access(folder, os.R_OK):
        QMessageBox.critical(None, "Permission denied", f"Cannot access folder {folder}")
        table_widget.setRowCount(0)
        return set()
    entries = sorted(os.listdir(folder))

    files = [f for f in entries if os.path.isfile(os.path.join(folder, f))]
    table_widget.setRowCount(len(files))
    table_widget.setColumnCount(1)
    table_widget.setHorizontalHeaderLabels(["Name"])
    table_widget.horizontalHeader().setStretchLastSection(True)
    for row, name in enumerate(files):
        table_widget.setItem(row, 0, QTableWidgetItem(name))
    return set(files)

def get_table_items(table_widget):
    items = set()
    for row in range(table_widget.rowCount()):
        it = table_widget.item(row, 0)
        if it:
            items.add(it.text())
    return items


def update_compare_stats(src_table, dst_table, missing_label):
    src_items = get_table_items(src_table)
    dst_items = get_table_items(dst_table)
    missing = src_items - dst_items
    missing_label.setText(f"Missing: {len(missing)}")
    palette = src_table.palette()
    default_color = palette.color(QPalette.Text)
    for row in range(src_table.rowCount()):
        it = src_table.item(row, 0)
        if not it:
            continue
        name = it.text()
        if name in missing:
            it.setForeground(QBrush(QColor('red')))
        else:
            it.setForeground(QBrush(default_color))


def browse_folder(line_edit, table_widget=None, status_label=None, src_table=None, dst_table=None, missing_label=None):
    folder = QFileDialog.getExistingDirectory(None, "Select Folder", line_edit.text() or "")
    if folder:
        line_edit.setText(folder)
        if table_widget is not None:
            files = populate_table(folder, table_widget)
            if status_label is not None:
                prefix = status_label.text().split(':')[0]
                status_label.setText(f"{prefix}: {len(files)}")
            if missing_label is not None and src_table is not None and dst_table is not None:
                update_compare_stats(src_table, dst_table, missing_label)


class DropTable(QTableWidget):
    """QTableWidget that accepts folder/file drops and emits the dropped path."""
    pathDropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            super().dropEvent(event)
            return
        path = urls[0].toLocalFile()
        if os.path.isfile(path):
            path = os.path.dirname(path)
        self.pathDropped.emit(path)
        event.acceptProposedAction()


def load_folder(folder, line_edit, table_widget=None, status_label=None, src_table=None, dst_table=None, missing_label=None):
    """Load a folder path into the given widgets (used for drops)."""
    if folder:
        line_edit.setText(folder)
        if table_widget is not None:
            files = populate_table(folder, table_widget)
            if status_label is not None:
                prefix = status_label.text().split(':')[0]
                status_label.setText(f"{prefix}: {len(files)}")
        if missing_label is not None and src_table is not None and dst_table is not None:
            update_compare_stats(src_table, dst_table, missing_label)


class CopyWorker(QObject):
    """Worker that copies files in a separate thread and emits progress."""
    progress = Signal(int, str, int)
    finished = Signal()
    error = Signal(str)

    def __init__(self, src_folder, dst_folder, files):
        super().__init__()
        self.src = src_folder
        self.dst = dst_folder
        self.files = files
        self._running = True

    @Slot()
    def run(self):
        total = len(self.files)
        for idx, name in enumerate(self.files):
            if not self._running:
                break
            src_path = os.path.join(self.src, name)
            dst_path = os.path.join(self.dst, name)
            if not os.path.isfile(src_path):
                self.error.emit(f"Source file not found: {src_path}")
                continue
            if not os.access(src_path, os.R_OK):
                self.error.emit(f"No read access to source file: {src_path}")
                continue
            parent = os.path.dirname(dst_path) or self.dst
            if not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            if not os.access(parent, os.W_OK):
                self.error.emit(f"No write access to destination folder: {parent}")
                continue
            shutil.copy2(src_path, dst_path)
            self.progress.emit(idx + 1, name, total)
        self.finished.emit()

    def stop(self):
        self._running = False


def main():
    app = QApplication(sys.argv)
    if os.name == 'nt':
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.qtawesome.foldercomparator")
    app_icon = qta.icon('fa6s.folder', color='#c62828')
    app.setWindowIcon(app_icon)
    window = QMainWindow()
    window.setWindowIcon(app_icon)
    window.setWindowTitle("Folder Comparator")
    window.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    window.resize(640, 360)
    window.setMinimumSize(640, 360)

    central = QWidget()
    main_layout = QVBoxLayout(central)
    main_layout.setContentsMargins(8, 8, 8, 8)
    main_layout.setSpacing(6)

    top_layout = QHBoxLayout()
    top_layout.setContentsMargins(0, 0, 0, 0)
    top_layout.setSpacing(6)

    src_label = QLabel("Source:")
    src_input = QLineEdit()
    src_input.setReadOnly(True)
    src_input.setPlaceholderText("Select source folder")
    src_btn = QPushButton("Browse...")
    src_btn.setIcon(qta.icon('fa6s.folder-open'))
    src_btn.clicked.connect(lambda: browse_folder(src_input, left_table, src_count_label, left_table, right_table, missing_label))

    dst_label = QLabel("Destination:")
    dst_input = QLineEdit()
    dst_input.setReadOnly(True)
    dst_input.setPlaceholderText("Select destination folder")
    dst_btn = QPushButton("Browse...")
    dst_btn.setIcon(qta.icon('fa6s.folder-open'))
    dst_btn.clicked.connect(lambda: browse_folder(dst_input, right_table, dst_count_label, left_table, right_table, missing_label))

    top_layout.addWidget(src_label)
    top_layout.addWidget(src_input, 1)
    top_layout.addWidget(src_btn)
    top_layout.addSpacing(6)
    top_layout.addWidget(dst_label)
    top_layout.addWidget(dst_input, 1)
    top_layout.addWidget(dst_btn)

    main_layout.addLayout(top_layout)

    splitter = QSplitter(Qt.Horizontal)

    left = QWidget()
    left_layout = QVBoxLayout(left)
    left_layout.setContentsMargins(0, 0, 0, 0)
    left_layout.setSpacing(0)
    left_table = DropTable()
    left_table.setColumnCount(1)
    left_table.setHorizontalHeaderLabels(["Name"])
    left_table.horizontalHeader().setStretchLastSection(True)
    left_table.setContentsMargins(0, 0, 0, 0)
    left_table.verticalHeader().setDefaultSectionSize(24)
    left_table.setToolTip("Drop a folder here to set Source")
    left_layout.addWidget(left_table)

    right = QWidget()
    right_layout = QVBoxLayout(right)
    right_layout.setContentsMargins(0, 0, 0, 0)
    right_layout.setSpacing(0)
    right_table = DropTable()
    right_table.setColumnCount(1)
    right_table.setHorizontalHeaderLabels(["Name"])
    right_table.horizontalHeader().setStretchLastSection(True)
    right_table.setContentsMargins(0, 0, 0, 0)
    right_table.verticalHeader().setDefaultSectionSize(24)
    right_table.setToolTip("Drop a folder here to set Destination")
    right_layout.addWidget(right_table)

    splitter.addWidget(left)
    splitter.addWidget(right)
    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(1, 1)
    splitter.setSizes([1, 1])

    main_layout.addWidget(splitter)

    stats_widget = QWidget()
    stats_layout = QHBoxLayout(stats_widget)
    stats_layout.setContentsMargins(4, 4, 4, 4)
    stats_layout.setSpacing(12)
    src_count_label = QLabel("Source: 0")
    dst_count_label = QLabel("Destination: 0")
    missing_label = QLabel("Missing: 0")
    stats_layout.addWidget(src_count_label)
    stats_layout.addSpacing(12)
    stats_layout.addWidget(dst_count_label)
    stats_layout.addSpacing(12)
    stats_layout.addWidget(missing_label)
    stats_layout.setAlignment(Qt.AlignLeft)
    stats_widget.setFixedHeight(36)
    main_layout.addWidget(stats_widget)

    action_widget = QWidget()
    action_layout = QHBoxLayout(action_widget)
    action_layout.setContentsMargins(4, 0, 4, 0)
    action_layout.setSpacing(8)
    progress_bar = QProgressBar()
    progress_bar.setRange(0, 100)
    progress_bar.setValue(0)
    progress_bar.setTextVisible(True)
    copy_btn = QPushButton("Copy missing to Destination")
    copy_btn.setStyleSheet("background-color: #28a745; color: white; padding: 6px 12px;")
    copy_btn.setIcon(qta.icon('fa6s.copy'))
    copy_btn.setEnabled(True)
    copy_btn.setToolTip("Copy missing files from Source to Destination")
    action_layout.addWidget(progress_bar, 1)
    action_layout.addWidget(copy_btn)
    action_widget.setFixedHeight(44)
    main_layout.addWidget(action_widget)

    status_bar = QStatusBar()
    window.setStatusBar(status_bar)

    left_table.pathDropped.connect(lambda p: load_folder(p, src_input, left_table, src_count_label, left_table, right_table, missing_label))
    right_table.pathDropped.connect(lambda p: load_folder(p, dst_input, right_table, dst_count_label, left_table, right_table, missing_label))

    state = {"worker": None, "thread": None, "running": False}

    def on_progress(idx, name, total):
        progress_bar.setValue(idx)
        status_bar.showMessage(f"Copying: {name} ({idx}/{total})")
        dst_files = populate_table(dst_input.text(), right_table)
        dst_count_label.setText(f"Destination: {len(dst_files)}")
        update_compare_stats(left_table, right_table, missing_label)

    def on_error(msg):
        status_bar.showMessage(msg, 5000)
        QMessageBox.critical(window, "Copy error", msg)

    def on_finished():
        copy_btn.setEnabled(True)
        status_bar.showMessage("Copy finished", 5000)
        progress_bar.setValue(0)
        dst_files = populate_table(dst_input.text(), right_table)
        dst_count_label.setText(f"Destination: {len(dst_files)}")
        update_compare_stats(left_table, right_table, missing_label)

    def start_copy():
        src_folder = src_input.text()
        dst_folder = dst_input.text()
        if not src_folder or not dst_folder:
            QMessageBox.warning(window, "Missing folder", "Please set both Source and Destination folders before copying.")
            return
        if not os.path.isdir(src_folder) or not os.access(src_folder, os.R_OK):
            QMessageBox.critical(window, "Source folder error", f"Source folder is not accessible: {src_folder}")
            return
        if not os.path.isdir(dst_folder) or not os.access(dst_folder, os.W_OK):
            QMessageBox.critical(window, "Destination folder error", f"Destination folder is not writable or does not exist: {dst_folder}")
            return
        missing = sorted(list(get_table_items(left_table) - get_table_items(right_table)))
        if not missing:
            QMessageBox.information(window, "Nothing to copy", "No missing files to copy.")
            return
        copy_btn.setEnabled(True)
        progress_bar.setRange(0, len(missing))
        progress_bar.setValue(0)
        worker = CopyWorker(src_folder, dst_folder, missing)
        thread = QThread()
        worker.moveToThread(thread)
        worker.progress.connect(on_progress)
        worker.error.connect(on_error)
        worker.finished.connect(on_finished)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        state["worker"] = worker
        state["thread"] = thread
        state["running"] = True
        copy_btn.setText("Stop")
        copy_btn.setStyleSheet("background-color: #dc3545; color: white; padding: 6px 12px;")
        copy_btn.setIcon(qta.icon('fa6s.stop'))
        thread.start()

    def stop_copy():
        if state["worker"] is not None:
            state["worker"].stop()
            status_bar.showMessage("Stopping...", 3000)
            copy_btn.setText("Stopping...")
            copy_btn.setEnabled(False)

    def toggle_copy():
        if state["running"]:
            stop_copy()
        else:
            start_copy()

    copy_btn.clicked.connect(toggle_copy)

    def on_finished():
        copy_btn.setEnabled(True)
        status_bar.showMessage("Copy finished", 5000)
        progress_bar.setValue(0)
        dst_files = populate_table(dst_input.text(), right_table)
        dst_count_label.setText(f"Destination: {len(dst_files)}")
        update_compare_stats(left_table, right_table, missing_label)
        state["worker"] = None
        state["thread"] = None
        state["running"] = False
        copy_btn.setText("Copy missing to Destination")
        copy_btn.setStyleSheet("background-color: #28a745; color: white; padding: 6px 12px;")
        copy_btn.setIcon(qta.icon('fa6s.copy'))

    window.setCentralWidget(central)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
