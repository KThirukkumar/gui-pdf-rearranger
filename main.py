#!/usr/bin/env python3
import sys
import os
import io
import subprocess
import shutil
import tempfile
from PIL import Image

# PyMuPDF (imported as `fitz`) is required. Show a helpful message and exit
# if it's not installed so users know how to fix it instead of a raw traceback.
try:
    import fitz
except Exception:
    msg = (
        "PyMuPDF (the `fitz` module) is required to run PDF Rearranger.\n"
        "Install it in your environment: `pip install PyMuPDF`\n"
        "If you're using the bundled/packaged app, ensure PyMuPDF is included."
    )
    # Try to show a GUI dialog if PyQt5 is available, otherwise print to stderr.
    try:
        from PyQt5.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication([])
        QMessageBox.critical(None, "Missing dependency", msg)
    except Exception:
        print(msg, file=sys.stderr)
    sys.exit(1)

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QListWidget,
    QListWidgetItem,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, QThreadPool, QRunnable, pyqtSignal, QObject
from PyQt5.QtWidgets import QSlider, QLabel, QCheckBox, QComboBox, QProgressBar


class OCRWorkerSignals(QObject):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(int)


class CentralWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(160, 210))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setWrapping(True)
        self.list.setFlow(QListWidget.LeftToRight)
        self.list.setDragDropMode(QListWidget.InternalMove)
        self.current_thumb_width = 160
        # spacing/grid so icons arrange in clear rows
        default_h = int(self.current_thumb_width * 1.4)
        self.list.setGridSize(QSize(self.current_thumb_width + 24, default_h + 24))
        self.list.setSpacing(12)
        self.list.setUniformItemSizes(True)


        btn_import = QPushButton("Import PDFs")
        btn_import.clicked.connect(self.import_files)

        btn_delete = QPushButton("Delete Selected")
        btn_delete.clicked.connect(self.delete_selected)

        btn_clear = QPushButton("Clear All")
        btn_clear.clicked.connect(self.clear_all)

        btn_save = QPushButton("Save As PDF")
        btn_save.clicked.connect(self.save_as_pdf)

        # Zoom slider controls thumbnail width (affects pages-per-row)
        zoom_label = QLabel("Zoom")
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setMinimum(60)
        self.zoom_slider.setMaximum(400)
        self.zoom_slider.setValue(self.current_thumb_width)
        self.zoom_slider.setTickInterval(10)
        self.zoom_slider.valueChanged.connect(self.update_icon_sizes)


        h = QHBoxLayout()
        h.addWidget(btn_import)
        h.addWidget(btn_delete)
        h.addWidget(btn_clear)
        h.addWidget(btn_save)
        h.addWidget(zoom_label)
        h.addWidget(self.zoom_slider)

        # OCR controls: enable checkbox and language selector
        self.ocr_checkbox = QCheckBox("Enable OCR")
        self.ocr_checkbox.setChecked(False)
        h.addWidget(self.ocr_checkbox)

        self.ocr_lang_combo = QComboBox()
        # common language shortcodes; users can install more Tesseract packs
        langs = ["eng", "fra", "spa", "deu", "ita"]
        self.ocr_lang_combo.addItems(langs)
        h.addWidget(self.ocr_lang_combo)

        layout = QVBoxLayout()
        layout.addLayout(h)
        layout.addWidget(self.list)
        self.setLayout(layout)

        self.setAcceptDrops(True)

    def import_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select PDFs or images to import", "", "PDF and Images (*.pdf *.png *.jpg *.jpeg)")
        for p in paths:
            if p.lower().endswith('.pdf'):
                self.parent_window.load_pdf(p)
            elif p.lower().endswith(('.png', '.jpg', '.jpeg')):
                self.parent_window.load_image(p)

    def delete_selected(self):
        for item in list(self.list.selectedItems()):
            row = self.list.row(item)
            self.list.takeItem(row)

    def clear_all(self):
        self.list.clear()

    def save_as_pdf(self):
        self.parent_window.save_output()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if not path:
                continue
            if path.lower().endswith('.pdf'):
                self.parent_window.load_pdf(path)
            elif path.lower().endswith(('.png', '.jpg', '.jpeg')):
                self.parent_window.load_image(path)

    def update_icon_sizes(self, width: int):
        self.current_thumb_width = width
        # update grid to match new thumbnail width so items wrap into rows
        new_h = int(width * 1.4)
        self.list.setGridSize(QSize(width + 24, new_h + 24))
        for i in range(self.list.count()):
            item = self.list.item(i)
            orig = item.data(Qt.UserRole + 1)
            if isinstance(orig, QPixmap):
                h = max(40, int(orig.height() * (width / max(1, orig.width()))))
                icon = QIcon(orig.scaled(width, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                item.setIcon(icon)


def run_ocr(input_path: str, output_path: str, lang: str = "eng"):
    """Run OCR on `input_path` and write searchable PDF to `output_path`.
    Tries `ocrmypdf` Python API first, falls back to CLI if available.
    """
    try:
        import ocrmypdf
        ocrmypdf.ocr(input_path, output_path, language=lang)
        return
    except Exception:
        # try CLI fallback
        if shutil.which("ocrmypdf"):
            cmd = ["ocrmypdf", "-l", lang, input_path, output_path]
            subprocess.run(cmd, check=True)
            return
        raise RuntimeError("ocrmypdf not available (install python package or CLI)")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('PDF Rearranger')
        self.resize(900, 600)

        # reuse opened documents and thumbnail cache to keep memory and CPU low
        self.open_docs = {}          # path -> fitz.Document
        self.thumb_cache = {}        # (path,page,width) -> QPixmap
        self.threadpool = QThreadPool.globalInstance()

        self.central = CentralWidget(self)
        self.setCentralWidget(self.central)

        # ensure thumbnails updated in main thread
        self._thumb_signal_receiver = self

        # status/progress for long-running tasks (OCR)
        self.ocr_progress = QProgressBar()
        self.ocr_progress.setVisible(False)
        self.ocr_progress.setMaximumWidth(200)
        self.statusBar().addPermanentWidget(self.ocr_progress)
        self.ocr_cancel_btn = QPushButton("Cancel OCR")
        self.ocr_cancel_btn.setVisible(False)
        self.statusBar().addPermanentWidget(self.ocr_cancel_btn)
        self.current_ocr_task = None
        self.current_ocr_signals = None
        self.ocr_cancel_btn.clicked.connect(lambda: self._cancel_current_ocr())

    def _cancel_current_ocr(self):
        try:
            if self.current_ocr_task:
                try:
                    self.current_ocr_task.cancel()
                except Exception:
                    pass
            # hide UI elements immediately
            try:
                self.ocr_progress.setVisible(False)
                self.ocr_cancel_btn.setVisible(False)
                self.statusBar().showMessage("Cancelling OCR...")
            except Exception:
                pass
        except Exception:
            pass

    def load_pdf(self, path):
        # open document once and reuse
        try:
            if path in self.open_docs:
                doc = self.open_docs[path]
            else:
                doc = fitz.open(path)
                self.open_docs[path] = doc
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Cannot open {path}: {e}")
            return

        base = os.path.basename(path)
        for p in range(doc.page_count):
            item = QListWidgetItem(QIcon(), f"{base} — p{p+1}")
            item.setData(Qt.UserRole, (path, p))
            self.central.list.addItem(item)
            # schedule background thumbnail rendering
            self.schedule_thumbnail(path, p, self.central.current_thumb_width)

    def load_image(self, path):
        # convert image to a one-page PDF in memory and store as a document
        try:
            im = Image.open(path)
            if im.mode in ("RGBA", "LA") or im.mode == "P":
                im = im.convert("RGB")
            bio = io.BytesIO()
            im.save(bio, format="PDF")
            pdf_bytes = bio.getvalue()
            doc = fitz.open("pdf", pdf_bytes)
            self.open_docs[path] = doc
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Cannot open image {path}: {e}")
            return

        base = os.path.basename(path)
        item = QListWidgetItem(QIcon(), f"{base} — p1")
        item.setData(Qt.UserRole, (path, 0))
        self.central.list.addItem(item)
        # schedule thumbnail for the newly-created page
        self.schedule_thumbnail(path, 0, self.central.current_thumb_width)

    def save_output(self):
        if self.central.list.count() == 0:
            QMessageBox.information(self, "No pages", "No pages to save. Add or drop PDFs first.")
            return

        out_path, _ = QFileDialog.getSaveFileName(self, "Save output PDF", "output.pdf", "PDF Files (*.pdf)")
        if not out_path:
            return

        new_doc = fitz.open()
        try:
            for i in range(self.central.list.count()):
                item = self.central.list.item(i)
                data = item.data(Qt.UserRole)
                if not data:
                    continue
                src_path, page_no = data
                if src_path in self.open_docs:
                    src = self.open_docs[src_path]
                    new_doc.insert_pdf(src, from_page=page_no, to_page=page_no)
                else:
                    src = fitz.open(src_path)
                    new_doc.insert_pdf(src, from_page=page_no, to_page=page_no)
                    src.close()

            # save to a temporary file first, then optionally run OCR
            tmpf = None
            ocr_started = False
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as t:
                    tmpf = t.name
                new_doc.save(tmpf)

                if getattr(self.central, 'ocr_checkbox', None) and self.central.ocr_checkbox.isChecked():
                    lang = self.central.ocr_lang_combo.currentText() if getattr(self.central, 'ocr_lang_combo', None) else 'eng'

                    # Run OCR in background to keep UI responsive and show progress
                    # We'll run the ocrmypdf CLI in a cancellable subprocess and parse progress
                    import re

                    class OCRTask(QRunnable):
                        def __init__(self, in_path, out_path, lang, signals):
                            super().__init__()
                            self.in_path = in_path
                            self.out_path = out_path
                            self.lang = lang
                            self.signals = signals
                            self._proc = None
                            self._cancelled = False

                        def cancel(self):
                            self._cancelled = True
                            try:
                                if self._proc and self._proc.poll() is None:
                                    self._proc.terminate()
                            except Exception:
                                pass

                        def run(self):
                            try:
                                # prefer CLI for cancellable subprocess
                                exe = shutil.which("ocrmypdf") or shutil.which("ocrmypdf.exe")
                                if not exe:
                                    # fallback to python -m ocrmypdf
                                    exe = sys.executable
                                    cmd = [exe, "-m", "ocrmypdf", "-l", self.lang, self.in_path, self.out_path]
                                else:
                                    cmd = [exe, "-l", self.lang, self.in_path, self.out_path]

                                # run in its own session so signals to the parent
                                # (e.g. accidental SIGINT) don't automatically kill it
                                env = os.environ.copy()
                                # request unbuffered output from python-backed invocations
                                env.setdefault("PYTHONUNBUFFERED", "1")
                                # use line-buffered I/O for real-time progress parsing
                                self._proc = subprocess.Popen(
                                    cmd,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    text=True,
                                    bufsize=1,
                                    start_new_session=True,
                                    env=env,
                                )

                                percent_re = re.compile(r"(\d{1,3})%")
                                # keep a short rolling log of stdout for diagnostics
                                lines = []
                                logfile = os.path.join('/tmp', "pdf_rearranger_ocr.log")
                                # write a start marker so we always have a trace
                                try:
                                    with open(logfile, "a", encoding="utf-8") as lf:
                                        lf.write(f"[{__import__('time').ctime()}] OCR START in={self.in_path} out={self.out_path}\n")
                                except Exception:
                                    pass
                                # Read lines and parse progress
                                # Use select to capture partial lines and carriage-return
                                # updates (ocrmypdf may render progress bars without newlines).
                                try:
                                    import select
                                except Exception:
                                    select = None

                                buf = ''
                                # prefer select on Unix to avoid blocking on readline
                                while True:
                                    if self._proc is None:
                                        break
                                    try:
                                        readable = True
                                        if select:
                                            r, _, _ = select.select([self._proc.stdout], [], [], 0.1)
                                            readable = bool(r)
                                        if not readable:
                                            # check for process exit
                                            if self._proc.poll() is not None:
                                                break
                                            continue
                                        chunk = self._proc.stdout.read(1024)
                                    except Exception:
                                        chunk = ''

                                    if chunk == '' and self._proc.poll() is not None:
                                        break
                                    if not chunk:
                                        continue

                                    # write to rolling buffer and append to logfile
                                    try:
                                        buf += chunk
                                        lines.extend([l for l in chunk.splitlines() if l.strip()])
                                        if len(lines) > 200:
                                            lines = lines[-200:]
                                        with open(logfile, "a", encoding="utf-8") as lf:
                                            for chline in chunk.splitlines(True):
                                                lf.write(f"[{__import__('time').ctime()}] ")
                                                lf.write(chline)
                                    except Exception:
                                        pass

                                    # parse any percent occurrences in the buffer
                                    try:
                                        for m in percent_re.finditer(buf):
                                            try:
                                                p = int(m.group(1))
                                                self.signals.progress.emit(max(0, min(100, p)))
                                            except Exception:
                                                pass
                                        # keep buffer bounded
                                        if len(buf) > 4096:
                                            buf = buf[-4096:]
                                    except Exception:
                                        pass
                                    if self._cancelled:
                                        try:
                                            if self._proc.poll() is None:
                                                self._proc.terminate()
                                        except Exception:
                                            pass
                                        try:
                                            with open(logfile, "a", encoding="utf-8") as lf:
                                                lf.write(f"[{__import__('time').ctime()}] OCR CANCELLED in={self.in_path}\n")
                                        except Exception:
                                            pass
                                        self.signals.finished.emit(False, "Cancelled")
                                        return

                                ret = self._proc.wait()
                                # if process failed, include last few logged lines to help debug
                                if ret == 0:
                                    try:
                                        with open(logfile, "a", encoding="utf-8") as lf:
                                            lf.write(f"[{__import__('time').ctime()}] OCR FINISHED out={self.out_path}\n")
                                    except Exception:
                                        pass
                                    self.signals.finished.emit(True, self.out_path)
                                else:
                                    tail = "\n".join(lines[-20:])
                                    msg = f"ocrmypdf exited {ret}\n--- recent output ---\n{tail}"
                                    # also append to logfile a failure marker
                                    try:
                                        with open(logfile, "a", encoding="utf-8") as lf:
                                            lf.write(f"[{__import__('time').ctime()}] PROCESS EXIT {ret}\n")
                                            lf.write(msg + "\n")
                                    except Exception:
                                        pass
                                    self.signals.finished.emit(False, msg)
                            except Exception as e:
                                self.signals.finished.emit(False, str(e))

                    # instantiate top-level signals and keep a strong reference
                    # on the MainWindow so they persist
                    signals = OCRWorkerSignals()
                    self.current_ocr_signals = signals

                    def _on_progress(p: int):
                        try:
                            if self.ocr_progress.maximum() == 0:
                                self.ocr_progress.setRange(0, 100)
                            self.ocr_progress.setValue(p)
                            self.statusBar().showMessage(f"Running OCR... {p}%")
                        except Exception:
                            pass

                    def _on_ocr_finished(success: bool, msg: str):
                        # hide progress and cancel button
                        try:
                            self.ocr_progress.setVisible(False)
                            self.ocr_cancel_btn.setVisible(False)
                            self.statusBar().clearMessage()
                        except Exception:
                            pass
                        # clear current task reference
                        try:
                            self.current_ocr_task = None
                        except Exception:
                            pass

                        # also clear persistent signals reference so it can be GC'd
                        try:
                            self.current_ocr_signals = None
                        except Exception:
                            pass

                        if success:
                            QMessageBox.information(self, "Saved", f"Saved OCR'd PDF to {msg}")
                        else:
                            # if cancelled, msg may be 'Cancelled'
                            if msg == 'Cancelled':
                                QMessageBox.information(self, "Cancelled", "OCR was cancelled.")
                            else:
                                QMessageBox.critical(self, "OCR Error", f"OCR failed: {msg}")
                                # try to move non-OCR file instead
                                try:
                                    shutil.move(tmpf, out_path)
                                    QMessageBox.information(self, "Saved (no OCR)", f"Saved non-OCR PDF to {out_path}")
                                except Exception:
                                    pass
                        # cleanup temp file if still present
                        try:
                            if tmpf and os.path.exists(tmpf):
                                os.remove(tmpf)
                        except Exception:
                            pass

                    signals.progress.connect(_on_progress)
                    signals.finished.connect(_on_ocr_finished)

                    # show busy indicator and cancel; start determinate (0-100)
                    self.statusBar().showMessage("Running OCR...")
                    self.ocr_progress.setRange(0, 100)
                    self.ocr_progress.setValue(0)
                    self.ocr_progress.setVisible(True)
                    self.ocr_cancel_btn.setVisible(True)

                    task = OCRTask(tmpf, out_path, lang, signals)
                    self.current_ocr_task = task
                    self.threadpool.start(task)
                    ocr_started = True
                    # don't close new_doc here; let outer finally handle it
                    return
                else:
                    shutil.move(tmpf, out_path)
                    QMessageBox.information(self, "Saved", f"Saved rearranged PDF to {out_path}")
            finally:
                # ensure temp file removed if it still exists
                try:
                    # if OCR was started asynchronously, the OCR handler will remove the temp file
                    if not ocr_started and tmpf and os.path.exists(tmpf):
                        os.remove(tmpf)
                except Exception:
                    pass
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save PDF: {e}")
        finally:
            try:
                new_doc.close()
            except Exception:
                pass

    def schedule_thumbnail(self, path: str, page_no: int, width: int):
        key = (path, page_no, width)
        if key in self.thumb_cache:
            # already rendered
            pixmap = self.thumb_cache[key]
            self.set_thumbnail(path, page_no, pixmap)
            return

        # define worker using QRunnable
        class ThumbSignals(QObject):
            finished = pyqtSignal(str, int, QPixmap)

        class ThumbTask(QRunnable):
            def __init__(self, path, page_no, width, signals, open_docs):
                super().__init__()
                self.path = path
                self.page_no = page_no
                self.width = width
                self.signals = signals
                self.open_docs = open_docs

            def run(self):
                try:
                    if self.path in self.open_docs:
                        doc = self.open_docs[self.path]
                    else:
                        doc = fitz.open(self.path)
                    page = doc.load_page(self.page_no)
                    # compute scale to match target width
                    mat = fitz.Matrix(1, 1)
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    img_w = pix.width or 1
                    scale = float(self.width) / img_w
                    mat = fitz.Matrix(scale, scale)
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    png = pix.tobytes("png")
                    qpix = QPixmap()
                    qpix.loadFromData(png)
                    self.signals.finished.emit(self.path, self.page_no, qpix)
                except Exception:
                    # emit empty pixmap on failure
                    self.signals.finished.emit(self.path, self.page_no, QPixmap())

        signals = ThumbSignals()
        signals.finished.connect(self.set_thumbnail)
        task = ThumbTask(path, page_no, width, signals, self.open_docs)
        self.threadpool.start(task)

    def set_thumbnail(self, path: str, page_no: int, pixmap: QPixmap):
        # cache by current width
        width = self.central.current_thumb_width
        key = (path, page_no, width)
        if not pixmap.isNull():
            self.thumb_cache[key] = pixmap

        # find matching items and update icon
        for i in range(self.central.list.count()):
            item = self.central.list.item(i)
            data = item.data(Qt.UserRole)
            if data and data[0] == path and data[1] == page_no:
                if not pixmap.isNull():
                    h = max(40, int(pixmap.height() * (width / max(1, pixmap.width()))))
                    icon = QIcon(pixmap.scaled(width, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    item.setIcon(icon)
                return

    def closeEvent(self, event):
        # close any open documents
        for doc in list(self.open_docs.values()):
            try:
                doc.close()
            except Exception:
                pass
        self.open_docs.clear()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
