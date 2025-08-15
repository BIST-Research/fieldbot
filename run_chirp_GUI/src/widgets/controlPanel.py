from PyQt5 import QtWidgets, QtCore

class ControlPanel(QtWidgets.QWidget):
    def __init__(self, initial_values, parent=None):
        super().__init__(parent)
        self.values = initial_values
        self.setup()

    def setup(self):
        main_lyt = QtWidgets.QHBoxLayout(self)
        main_lyt.setContentsMargins(5, 2, 5, 2)

        # Run Controls Section
        run_grp = QtWidgets.QGroupBox("Run")
        run_lyt = QtWidgets.QHBoxLayout()
        self.setup_run_grp(run_lyt)
        run_grp.setLayout(run_lyt)
        main_lyt.addWidget(run_grp, stretch=0)

        # File Section
        file_grp = QtWidgets.QGroupBox("File Handling")
        file_lyt = QtWidgets.QHBoxLayout()
        self.setup_file_grp(file_lyt)
        file_grp.setLayout(file_lyt)
        main_lyt.addWidget(file_grp, stretch=1)

        # Display Section
        display_grp = QtWidgets.QGroupBox("Display")
        display_lyt = QtWidgets.QHBoxLayout()
        self.setup_display_grp(display_lyt)
        display_grp.setLayout(display_lyt)
        main_lyt.addWidget(display_grp, stretch=0)

    # === Section 1: Run Controls ===
    def setup_run_grp(self, layout):
        self.start_btn = QtWidgets.QPushButton()
        self.start_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_MediaPlay))
        self.start_btn.setCheckable(True)
        layout.addWidget(self.start_btn)

        self.prev_btn = QtWidgets.QPushButton()
        self.prev_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ArrowLeft))
        layout.addWidget(self.prev_btn)

        self.next_btn = QtWidgets.QPushButton()
        self.next_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ArrowRight))
        layout.addWidget(self.next_btn)

    # === Section 2: File Handling ===
    def setup_file_grp(self, layout):
        layout.addWidget(QtWidgets.QLabel("Address:"))
        
        self.file_edit = QtWidgets.QLineEdit(self.values["fname"])
        layout.addWidget(self.file_edit)

        layout.addWidget(QtWidgets.QLabel("Save Cycles:"))
        self.saveCycles_edit = QtWidgets.QLineEdit(str(self.values["saveCycles"]))
        self.saveCycles_edit.setMaximumWidth(30)
        layout.addWidget(self.saveCycles_edit)
        
        self.folder_btn = QtWidgets.QPushButton()
        self.folder_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))
        self.folder_btn.setMaximumWidth(30)
        self.folder_btn.clicked.connect(self.selectFolder)
        layout.addWidget(self.folder_btn)
        
        self.save_btn = QtWidgets.QPushButton("Save")
        self.save_btn.setMaximumWidth(40)
        self.save_btn.setCheckable(True)
        layout.addWidget(self.save_btn)

        self.load_btn = QtWidgets.QPushButton("Load")
        self.load_btn.setMaximumWidth(40)
        self.load_btn.setCheckable(True)
        layout.addWidget(self.load_btn)


    # === Section 3: Display Control ===
    def setup_display_grp(self, layout):
        layout.addWidget(QtWidgets.QLabel("Scale:"))
        self.absolute_btn = QtWidgets.QPushButton("Absolute")
        self.absolute_btn.setMaximumWidth(60)
        self.absolute_btn.setCheckable(True)
        layout.addWidget(self.absolute_btn)
        
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

        # dB range
        layout.addWidget(QtWidgets.QLabel("dB Range:"))
        self.dB_edit = QtWidgets.QLineEdit(str(int(self.values["dB_range"])))
        self.dB_edit.setMaximumWidth(60)
        layout.addWidget(self.dB_edit)

        self.apply_btn = QtWidgets.QPushButton("Apply")
        self.apply_btn.setMaximumWidth(80)
        layout.addWidget(self.apply_btn)

    def selectFolder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Folder",
            self.file_edit.text() or QtCore.QDir.homePath()
        )
        if folder:
            self.file_edit.setText(folder)