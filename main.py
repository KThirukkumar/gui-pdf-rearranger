#!/usr/bin/env python3
import sys
import os
import fitz
import io
import subprocess
import shutil
import tempfile
from PIL import Image

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
from PyQt5.QtWidgets import QSlider, QLabel, QCheckBox, QComboBox


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
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as t:
                    tmpf = t.name
                new_doc.save(tmpf)

                if getattr(self.central, 'ocr_checkbox', None) and self.central.ocr_checkbox.isChecked():
                    lang = self.central.ocr_lang_combo.currentText() if getattr(self.central, 'ocr_lang_combo', None) else 'eng'
                    try:
                        run_ocr(tmpf, out_path, lang)
                        QMessageBox.information(self, "Saved", f"Saved OCR'd PDF to {out_path}")
                    except Exception as e:
                        QMessageBox.critical(self, "OCR Error", f"OCR failed: {e}")
                        # if OCR failed, offer to move the original non-OCR file instead
                        try:
                            shutil.move(tmpf, out_path)
                            QMessageBox.information(self, "Saved (no OCR)", f"Saved non-OCR PDF to {out_path}")
                        except Exception:
                            pass
                else:
                    shutil.move(tmpf, out_path)
                    QMessageBox.information(self, "Saved", f"Saved rearranged PDF to {out_path}")
            finally:
                # ensure temp file removed if it still exists
                try:
                    if tmpf and os.path.exists(tmpf):
                        os.remove(tmpf)
                except Exception:
                    pass
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save PDF: {e}")
        finally:
            new_doc.close()

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
