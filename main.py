import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from appLayout import AppLayout

if __name__ == '__main__':
    if sys.platform == 'win32':
        # Give Windows a separate taskbar identity instead of the Python icon.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Kinova.KDT.App')

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / 'resources/icons/kinova-app-v1.ico')))

    window = AppLayout()
    window.show()

    sys.exit(app.exec())
