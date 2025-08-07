import sys

from PyQt5.QtWidgets import QApplication

from src.mainWindow import MainWindow
from src.connector import Connector
from src.dataManager import DataManager

def main():
    app = QApplication(sys.argv)

    # ================
    #     DEFAULTS
    # ================
    fname = str(__file__[:-8]) + "\\data"
    fbl = 30_000
    fbh = 100_000
    dB_range = 45
    saveCycles = 20

    dataManager = DataManager()
    mainWindow = MainWindow(fbl, fbh, dB_range, saveCycles, fname)
    connector = Connector(mainWindow, dataManager)

    mainWindow.showMaximized()
    app.exec_()
    dataManager.close()

if __name__ == "__main__":
    main()
