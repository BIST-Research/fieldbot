from PyQt5.QtCore import QRectF
from PyQt5.QtWidgets import QStyle

class Connector:
    def __init__(self, mainWindow, dataManager):
        self.mainWindow = mainWindow
        self.dataManager = dataManager
        self.setup_connections()

    def setup_connections(self):
        self.dataManager.dataReady.connect(
            lambda raw_data: self.mainWindow.update(raw_data)
        )

        # Start/pause toggle
        self.mainWindow.control_panel.start_btn.toggled.connect(
            lambda checked: (
                self.dataManager.resume() if checked else self.dataManager.pause(),
                self.mainWindow.control_panel.start_btn.setIcon(
                    self.mainWindow.style().standardIcon(
                        QStyle.SP_MediaPause if checked else QStyle.SP_MediaPlay
                    )
                )
            )
        )

        # Single run
        self.mainWindow.control_panel.next_btn.clicked.connect(
            self.dataManager.next
        )

        self.mainWindow.control_panel.next_btn.clicked.connect(
            self.dataManager.prev
        )


        # Save toggle
        self.mainWindow.control_panel.save_btn.clicked.connect(
            lambda checked: (
                self.dataManager.save(
                    int(self.mainWindow.control_panel.saveCycles_edit.text()),
                    self.mainWindow.control_panel.file_edit.text()
                ) if checked else self.dataManager.unsave(),
                self.mainWindow.control_panel.save_btn.setText("Stop" if checked else "Save")
            )
        )

        # Load/unload toggle
        self.mainWindow.control_panel.load_btn.clicked.connect(
            lambda checked: (
                self.dataManager.load(self.mainWindow.control_panel.file_edit.text()) if checked else self.dataManager.unload(),
                self.mainWindow.update(self.mainWindow._currentData),
                self.mainWindow.control_panel.load_btn.setText("Unload" if checked else "Load")
            )
        )

        # Absolute/relative scaling toggle
        self.mainWindow.control_panel.absolute_btn.clicked.connect(
            lambda checked: (
                setattr(self.mainWindow.processor, 'absolute_scaling', not checked),
                self.mainWindow.update(self.mainWindow._currentData),
                self.mainWindow.control_panel.absolute_btn.setText("Relative" if checked else "Absolute")
            )
        )
        # Apply settings
        self.mainWindow.control_panel.apply_btn.clicked.connect(self.apply_settings)
        self.mainWindow.control_panel.fbl_edit.returnPressed.connect(self.apply_settings)
        self.mainWindow.control_panel.fbh_edit.returnPressed.connect(self.apply_settings)
        self.mainWindow.control_panel.dB_edit.returnPressed.connect(self.apply_settings)


    def apply_settings(self):
        try:
            fbl = 1000 * int(self.mainWindow.control_panel.fbl_edit.text())
            fbh = 1000 * int(self.mainWindow.control_panel.fbh_edit.text())
            dB_range = int(self.mainWindow.control_panel.dB_edit.text())
        except ValueError:
            return

        self.mainWindow.processor.reconfigure(fbl, fbh, dB_range)

        self.mainWindow.spectrogram.fbl = fbl
        self.mainWindow.spectrogram.fbh = fbh
        self.mainWindow.spectrogram.dB_range = dB_range
        self.mainWindow.spectrogram.setYRange(fbl, fbh)
        self.mainWindow.spectrogram.hist.setLevels(-dB_range, -3)

        self.mainWindow.dB_scale.dB_range = dB_range
        self.mainWindow.dB_scale.setYRange(-dB_range, -3)
        self.mainWindow.dB_scale.img.setRect(QRectF(0, -dB_range, 1, dB_range - 3))

        try:
            self.mainWindow.update(self.mainWindow._currentData)
        except:
            pass
