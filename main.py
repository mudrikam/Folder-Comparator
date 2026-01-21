from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QLabel,
    QLineEdit, QPushButton, QHBoxLayout, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar, QStyle, QStatusBar, QMessageBox
)
from PySide6.QtGui import QIcon, QBrush, QColor, QPalette
from PySide6.QtCore import Qt, Signal, QObject, Slot, QThread, QTimer
import sys
import os
import shutil
import ctypes
import traceback
import threading
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
    match_color = QColor('#2e7d32')
    for row in range(src_table.rowCount()):
        it = src_table.item(row, 0)
        if not it:
            continue
        name = it.text()
        if name in missing:
            it.setForeground(QBrush(QColor('red')))
        else:
            it.setForeground(QBrush(match_color))
    matched = src_items & dst_items
    for row in range(dst_table.rowCount()):
        it = dst_table.item(row, 0)
        if not it:
            continue
        name = it.text()
        if name in matched:
            it.setForeground(QBrush(match_color))
        else:
            it.setForeground(QBrush(QColor('red')))


def browse_folder(line_edit, table_widget=None, status_label=None, src_table=None, dst_table=None, missing_label=None):
    home = os.path.expanduser("~")
    start_dir = line_edit.text() or home
    folder = QFileDialog.getExistingDirectory(None, "Select Folder", start_dir)
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
        try:
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
        except Exception as e:
            tb = traceback.format_exc()
            self.error.emit(f"Unhandled worker error: {e}\n{tb}")
        finally:
            self.finished.emit()

    def stop(self):
        self._running = False



class CopyController(QObject):
    progress = Signal(int, str, int)
    error = Signal(str)
    finished = Signal()
    started = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._thread = None
        self._running = False

    def start(self, src_folder, dst_folder, files):
        if self._running:
            self.error.emit("Copy already running")
            return
        if not files:
            self.error.emit("No files to copy")
            return
        print(f"[Controller] start requested: {len(files)} files", file=sys.stderr)
        worker = CopyWorker(src_folder, dst_folder, files)
        thread = QThread()
        worker.moveToThread(thread)
        worker.progress.connect(self.progress, Qt.QueuedConnection)
        worker.error.connect(self.error, Qt.QueuedConnection)
        worker.finished.connect(self._on_worker_finished, Qt.QueuedConnection)
        thread.finished.connect(self._cleanup, Qt.QueuedConnection)
        thread.started.connect(worker.run)
        self._worker = worker
        self._thread = thread
        self._running = True
        self.started.emit()
        thread.start()

    def _on_worker_finished(self):
        print("[Controller] worker finished -> quitting thread", file=sys.stderr)
        if self._thread is not None:
            self._thread.quit()

    def _cleanup(self):
        print("[Controller] cleanup", file=sys.stderr)
        if self._worker is not None:
            try:
                self._worker.deleteLater()
            except Exception as e:
                print(traceback.format_exc(), file=sys.stderr)
        if self._thread is not None:
            try:
                self._thread.deleteLater()
            except Exception as e:
                print(traceback.format_exc(), file=sys.stderr)
        self._worker = None
        self._thread = None
        self._running = False
        self.finished.emit()

    def stop(self, wait=False, timeout=2000):
        if self._worker is not None:
            self._worker.stop()
        if self._thread is not None:
            try:
                self._thread.quit()
                if wait:
                    self._thread.wait(timeout)
            except Exception as e:
                tb = traceback.format_exc()
                print(tb, file=sys.stderr)
                self.error.emit(f"Stop error: {e}")

    def is_running(self):
        return self._running


def main():
    app = QApplication(sys.argv)
    def excepthook(exc_type, exc_value, exc_tb):
        tb = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
        if threading.current_thread() is threading.main_thread():
            QMessageBox.critical(None, "Unhandled Exception", tb)
        else:
            print(tb, file=sys.stderr)
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = excepthook
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
    clear_btn = QPushButton("Clear")
    clear_btn.setStyleSheet("background-color: #6c757d; color: white; padding: 6px 10px;")
    clear_btn.setIcon(qta.icon('fa6s.broom'))
    clear_btn.setToolTip("Reset application to initial state")
    action_layout.addWidget(clear_btn)
    action_widget.setFixedHeight(44)
    main_layout.addWidget(action_widget)

    status_bar = QStatusBar()
    window.setStatusBar(status_bar)

    progress_state = {"idx": 0, "name": "", "total": 0, "dirty": False}
    progress_timer = QTimer()
    def progress_timer_tick():
        if not progress_state["dirty"]:
            return
        idx = progress_state["idx"]
        name = progress_state["name"]
        total = progress_state["total"]
        if total:
            progress_bar.setMaximum(total)
            progress_bar.setValue(idx)
            status_bar.showMessage(f"Copying: {name} ({idx}/{total})")
        progress_state["dirty"] = False
    progress_timer.timeout.connect(progress_timer_tick)

    left_table.pathDropped.connect(lambda p: load_folder(p, src_input, left_table, src_count_label, left_table, right_table, missing_label))
    right_table.pathDropped.connect(lambda p: load_folder(p, dst_input, right_table, dst_count_label, left_table, right_table, missing_label))

    controller = CopyController()

    def close_handler(event):
        if controller.is_running():
            controller.stop(wait=True, timeout=2000)
        event.accept()

    window.closeEvent = close_handler

    def on_progress(idx, name, total):
        progress_state["idx"] = idx
        progress_state["name"] = name
        progress_state["total"] = total
        progress_state["dirty"] = True
        print(f"[Progress] queued {idx}/{total}: {name}", file=sys.stderr)

    def on_error(msg):
        progress_state["name"] = msg
        progress_state["dirty"] = True
        print(f"[Error] {msg}", file=sys.stderr)
        QMessageBox.critical(window, "Copy error", msg)

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
        try:
            progress_bar.setFormat("%v/%m")
        except Exception:
            pass
        progress_state["idx"] = 0
        progress_state["name"] = ""
        progress_state["total"] = len(missing)
        progress_state["dirty"] = True
        progress_timer.start(100)

        controller.start(src_folder, dst_folder, missing)

        copy_btn.setText("Stop")
        copy_btn.setStyleSheet("background-color: #dc3545; color: white; padding: 6px 12px;")
        copy_btn.setIcon(qta.icon('fa6s.stop'))

    def stop_copy():
        controller.stop(wait=False)
        progress_state["name"] = "Stopping..."
        progress_state["dirty"] = True
        copy_btn.setText("Stopping...")
        copy_btn.setEnabled(False)
        progress_timer.stop()

    def toggle_copy():
        if controller.is_running():
            stop_copy()
        else:
            start_copy()

    copy_btn.clicked.connect(toggle_copy)

    def clear_all():
        if controller.is_running():
            controller.stop(wait=True, timeout=2000)
        src_input.clear()
        dst_input.clear()
        left_table.setRowCount(0)
        right_table.setRowCount(0)
        src_count_label.setText("Source: 0")
        dst_count_label.setText("Destination: 0")
        missing_label.setText("Missing: 0")
        progress_bar.setValue(0)
        progress_state["idx"] = 0
        progress_state["name"] = ""
        progress_state["total"] = 0
        progress_state["dirty"] = False
        progress_timer.stop()
        copy_btn.setEnabled(True)
        copy_btn.setText("Copy missing to Destination")
        copy_btn.setStyleSheet("background-color: #28a745; color: white; padding: 6px 12px;")
        copy_btn.setIcon(qta.icon('fa6s.copy'))
        update_compare_stats(left_table, right_table, missing_label)

    clear_btn.clicked.connect(clear_all)

    def on_finished():
        print("[UI] on_finished invoked", file=sys.stderr)
        dst_files = populate_table(dst_input.text(), right_table)
        dst_count_label.setText(f"Destination: {len(dst_files)}")
        update_compare_stats(left_table, right_table, missing_label)
        progress_bar.setValue(0)
        try:
            progress_bar.setFormat("%p%")
        except Exception:
            pass
        progress_state["idx"] = 0
        progress_state["name"] = ""
        progress_state["total"] = 0
        progress_state["dirty"] = False
        progress_timer.stop()
        copy_btn.setEnabled(True)
        copy_btn.setText("Copy missing to Destination")
        copy_btn.setStyleSheet("background-color: #28a745; color: white; padding: 6px 12px;")
        copy_btn.setIcon(qta.icon('fa6s.copy'))

    controller.progress.connect(on_progress, Qt.QueuedConnection)
    controller.error.connect(on_error, Qt.QueuedConnection)
    controller.finished.connect(on_finished, Qt.QueuedConnection)
    controller.started.connect(lambda: progress_timer.start(100), Qt.QueuedConnection)

    window.setCentralWidget(central)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
