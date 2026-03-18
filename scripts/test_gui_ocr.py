import os
import sys
import time

# run headless if possible
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication, QFileDialog
from PyQt5.QtCore import QTimer

# ensure we import the app code from the workspace
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import main

PDF_IN = os.path.join('pdf', 'Pimsleur_book.pdf')
PDF_OUT = os.path.join('pdf', 'Pimsleur_book_ocr_gui_test.pdf')
LOGFILE = os.path.join('/tmp', 'pdf_rearranger_ocr.log')

app = QApplication([])
win = main.MainWindow()
win.show()

# load document pages into the list
win.load_pdf(PDF_IN)

# enable OCR in the UI
if getattr(win.central, 'ocr_checkbox', None):
    win.central.ocr_checkbox.setChecked(True)
if getattr(win.central, 'ocr_lang_combo', None):
    # choose English
    idx = win.central.ocr_lang_combo.findText('eng')
    if idx >= 0:
        win.central.ocr_lang_combo.setCurrentIndex(idx)

# monkeypatch file dialog to avoid user interaction
orig_getSave = QFileDialog.getSaveFileName
QFileDialog.getSaveFileName = lambda *args, **kwargs: (PDF_OUT, 'PDF Files (*.pdf)')

# start save (this triggers OCR asynchronously)
QTimer.singleShot(0, win.save_output)

# schedule a cancel shortly after OCR starts
def do_cancel():
    try:
        print('Attempting cancel...')
        # prefer well-known cancel method
        win._cancel_current_ocr()
    except Exception as e:
        print('Cancel failed:', e)

QTimer.singleShot(1500, do_cancel)

# quit after a few seconds so test ends
QTimer.singleShot(8000, app.quit)

ret = app.exec_()

# print logfile tail
print('\n=== logfile tail ===\n')
if os.path.exists(LOGFILE):
    with open(LOGFILE, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        for line in lines[-200:]:
            sys.stdout.write(line)
else:
    print('No logfile found at', LOGFILE)

sys.exit(ret)
