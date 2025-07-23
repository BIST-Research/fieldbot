import sys
from PyQt5 import QtWidgets, QtCore
from backend import Backend
from widgets import Spectrogram, Signal, dBScale, FFTWidget

class ControlPanel(QtWidgets.QWidget):
    def __init__(self, initial_values, parent=None):
        super().__init__(parent)
        self.values = initial_values
        self.setup_ui()
        
    def setup_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)

        # Start button
        self.start_btn = QtWidgets.QPushButton("Start")
        self.start_btn.setMaximumWidth(60)
        layout.addWidget(self.start_btn)

        # Single run button
        self.single_run_btn = QtWidgets.QPushButton("Single")
        self.single_run_btn.setMaximumWidth(60)
        layout.addWidget(self.single_run_btn)

        # Stop button
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.setMaximumWidth(60)
        layout.addWidget(self.stop_btn)


        # File path
        layout.addWidget(QtWidgets.QLabel("File:"))
        self.file_edit = QtWidgets.QLineEdit(self.values["fname"])
        layout.addWidget(self.file_edit)
        
        # Save button
        self.save_btn = QtWidgets.QPushButton("Save")
        self.save_btn.setMaximumWidth(60)
        layout.addWidget(self.save_btn)

        # Save button
        self.toggle_absolute_btn = QtWidgets.QPushButton("Toggle Absolute")
        self.toggle_absolute_btn.setMaximumWidth(140)
        layout.addWidget(self.toggle_absolute_btn)

        # Frequency low
        layout.addWidget(QtWidgets.QLabel("FBL (kHz):"))
        self.fbl_edit = QtWidgets.QLineEdit(str(self.values["fbl"] // 1000))
        self.fbl_edit.setMaximumWidth(60)
        layout.addWidget(self.fbl_edit)
        
        # Frequency high
        layout.addWidget(QtWidgets.QLabel("FBH (kHz):"))
        self.fbh_edit = QtWidgets.QLineEdit(str(self.values["fbh"] // 1000))
        self.fbh_edit.setMaximumWidth(60)
        layout.addWidget(self.fbh_edit)
        
        # dB Range
        layout.addWidget(QtWidgets.QLabel("dB Range:"))
        self.dB_edit = QtWidgets.QLineEdit(str(int(self.values["dB_range"] * 2)))
        self.dB_edit.setMaximumWidth(60)
        layout.addWidget(self.dB_edit)
        
        # Apply button
        self.apply_btn = QtWidgets.QPushButton("Apply")
        self.apply_btn.setMaximumWidth(80)
        layout.addWidget(self.apply_btn)

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.parse_args()
        self.setup_ui()
        self.backend = Backend(self.fbl, self.fbh, self.dB_range)
        self.setup_connections()
        
        
    def parse_args(self):
        self.fname = str(self.args[1])
        self.fbl = 1000 * int(self.args[2])
        self.fbh = 1000 * int(self.args[3])
        self.dB_range = int(self.args[4]) / 2
        
    def setup_ui(self):
        self.setWindowTitle("Spectrogram")
        self.resize(1200, 800)
        
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        initial_values = {
            "fname": self.fname,
            "fbl": self.fbl,
            "fbh": self.fbh,
            "dB_range": self.dB_range
        }
        self.control_panel = ControlPanel(initial_values)
        main_layout.addWidget(self.control_panel)

        spectro_container = QtWidgets.QWidget()
        spectro_layout = QtWidgets.QHBoxLayout(spectro_container)
        spectro_layout.setContentsMargins(0, 0, 0, 0)
        spectro_layout.setSpacing(0)
        
        self.spectrogram_widget = Spectrogram(self.fbl, self.fbh, self.dB_range)
        self.db_scale_widget = dBScale(self.dB_range)
        
        spectro_layout.addWidget(self.spectrogram_widget, 90)
        spectro_layout.addWidget(self.db_scale_widget, 10)

        signal_container = QtWidgets.QWidget()
        signal_layout = QtWidgets.QHBoxLayout(signal_container)
        signal_layout.setContentsMargins(0, 0, 0, 0)
        signal_layout.setSpacing(0)
        
        self.signal_widget = Signal()
        self.fft_widget = FFTWidget()
        
        signal_layout.addWidget(self.signal_widget, 80)
        signal_layout.addWidget(self.fft_widget, 20)
        
        main_layout.addWidget(spectro_container, 70)
        main_layout.addWidget(signal_container, 30)
        
    def setup_connections(self):
        self.backend.new_signal_data.connect(
            lambda data: self.signal_widget.update_signal(
                self.backend.time_vector, data
            )
        )
        self.backend.new_spectrogram_data.connect(
            self.spectrogram_widget.update_spectrogram
        )
        
        self.control_panel.apply_btn.clicked.connect(self.apply_settings)
        self.control_panel.toggle_absolute_btn.clicked.connect(self.backend.toggleAbsolute)
        self.control_panel.start_btn.clicked.connect(self.backend.startDataWorker)
        self.control_panel.stop_btn.clicked.connect(self.backend.stopDataWorker)
        
        # Timer
        self.compute_timer = QtCore.QTimer()
        self.compute_timer.timeout.connect(self.backend.compute)
        self.compute_timer.start(20)
        
    def apply_settings(self):
        try:
            new_fbl = 1000 * int(self.control_panel.fbl_edit.text())
            new_fbh = 1000 * int(self.control_panel.fbh_edit.text())
            new_dB_range = int(self.control_panel.dB_edit.text()) / 2
            
            self.backend.fbl = new_fbl
            self.backend.fbh = new_fbh
            self.backend.dB_range = new_dB_range
            
            self.spectrogram_widget.fbl = new_fbl
            self.spectrogram_widget.fbh = new_fbh
            self.spectrogram_widget.dB_range = new_dB_range
            self.spectrogram_widget.setYRange(new_fbl, new_fbh)
            self.spectrogram_widget.hist.setLevels(-new_dB_range, -3)
            
            self.db_scale_widget.dB_range = new_dB_range
            self.db_scale_widget.setYRange(-new_dB_range, -3)
            self.db_scale_widget.img.setRect(QtCore.QRectF(0, -new_dB_range, 1, new_dB_range))
            
            self.backend.reset()
            
        except ValueError:
            return
    
    def closeEvent(self, event):
        self.backend.close()
        event.accept()

def main():
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow(sys.argv)
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()