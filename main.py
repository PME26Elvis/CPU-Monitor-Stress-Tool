import sys
from PyQt5.QtWidgets import QApplication
from main_window import MainWindow

def main():
    """
    The main entry point for the CPU-Monitor-Stress-Tool application.
    """
    # Create the application instance
    app = QApplication(sys.argv)

    # Create and show the main window
    window = MainWindow()
    window.show()

    # Start the application's event loop
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()