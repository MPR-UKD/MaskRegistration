import sys
import os
import winreg as wr
from pathlib import Path

from pydicom.encoders import gdcm, pylibjpeg  # Important import for pyinstaller!
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWidgets import *
from backend import transform


class MaskRegistration(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MaskRegistration - Wrapper for SimpleITK")
        myFont = QtGui.QFont()
        myFont.setPointSize(8)
        self.setFont(myFont)

        layout = QGridLayout()

        # Input DICOM
        dicom_1_button = QPushButton("Select Segmented DICOM")
        layout.addWidget(dicom_1_button, 0, 0, 1, 1)
        self.dicom_1_text = QLineEdit()
        layout.addWidget(self.dicom_1_text, 0, 1, 1, 1)
        dicom_1_button.clicked.connect(self.update_dicom_1)

        # Input Mask
        mask_1_button = QPushButton("Select Input Mask")
        layout.addWidget(mask_1_button, 1, 0, 1, 1)
        self.mask_1_text = QLineEdit()
        layout.addWidget(self.mask_1_text, 1, 1, 1, 1)
        mask_1_button.clicked.connect(self.update_mask_1)

        # Registration DICOM
        dicom_2_button = QPushButton("Select Registration DICOM")
        layout.addWidget(dicom_2_button, 2, 0, 1, 1)
        self.dicom_2_text = QLineEdit()
        layout.addWidget(self.dicom_2_text, 2, 1, 1, 1)
        dicom_2_button.clicked.connect(self.update_dicom_2)

        # Output Mask
        mask_2_button = QPushButton("Select Output Mask")
        layout.addWidget(mask_2_button, 3, 0, 1, 1)
        self.mask_2_text = QLineEdit()
        layout.addWidget(self.mask_2_text, 3, 1, 1, 1)
        mask_2_button.clicked.connect(self.update_mask_2)

        # Run Button
        self.run = QPushButton("RUN")
        self.run.setMinimumHeight(80)
        myFont = QtGui.QFont()
        myFont.setPointSize(12)
        myFont.setBold(True)
        self.run.setFont(myFont)
        self.run.setStyleSheet("background-color : red")
        layout.addWidget(self.run, 0, 2, 4, 1)
        self.run.clicked.connect(self.run_registration)

        # Adding gif animation
        self.movie = QtGui.QMovie("loading.gif")
        self.label = QtWidgets.QLabel(self)
        self.label.setMovie(self.movie)

        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)
        self.setMinimumSize(QtCore.QSize(1200, 100))

    def file_dialog(self, text: str, line_edit: QLineEdit, mode: str) -> None:
        """
        File Dialog method to handle file/folder selection.

        :param text: Dialog Title
        :param line_edit: Line Edit Widget
        :param mode: Mode (DIR, FILE, SAVE_FILE)
        """
        last_path = self.get_last_dicom_path()
        if mode == "DIR":
            dialog = QFileDialog.getExistingDirectory(self, text, last_path)
        elif mode == "FILE":
            dialog = QFileDialog.getOpenFileName(
                self, text, last_path, "NIFTI files (*.nii*)"
            )[0]
        elif mode == "SAVE_FILE":
            dialog = QFileDialog.getSaveFileName(
                self, text, last_path, "NIFTI files (*.nii*)"
            )[0]
        line_edit.setText(dialog)

    def update_dicom_1(self) -> None:
        """Update the dicom_1_text field with the selected directory."""
        self.file_dialog("Select Dicom Path 1", self.dicom_1_text, "DIR")
        if self.dicom_1_text.text() != "" and self.mask_1_text.text() == "":
            self.mask_1_text.setText(os.path.join(self.dicom_1_text.text(), "mask.nii.gz"))

    def update_mask_1(self) -> None:
        """Update the mask_1_text field with the selected file."""
        self.file_dialog("Select Mask File 1", self.mask_1_text, "FILE")

    def update_dicom_2(self) -> None:
        """Update the dicom_2_text field with the selected directory."""
        self.file_dialog("Select Dicom Path 2", self.dicom_2_text, "DIR")
        if self.dicom_2_text.text() != "" and self.mask_2_text.text() == "":
            self.mask_2_text.setText(os.path.join(self.dicom_2_text.text(), "mask.nii.gz"))

    def update_mask_2(self) -> None:
        """Update the mask_2_text field with the selected file."""
        self.file_dialog("Select Save File Mask", self.mask_2_text, "SAVE_FILE")

    def run_registration(self) -> None:
        """Run the registration process."""
        # Start the loading animation
        self.label.show()
        self.movie.start()
        try:
            if not self.dicom_1_text.text() or not self.mask_1_text.text() or not self.dicom_2_text.text() or not self.mask_2_text.text():
                raise ValueError("Please fill in all the required fields.")
            transform(
                input_dicom_folder_1=Path(self.dicom_1_text.text()),
                input_mask_file=Path(self.mask_1_text.text()),
                input_dicom_folder_2=Path(self.dicom_2_text.text()),
                out_nii_file=Path(self.mask_2_text.text()),
            )
        except Exception as error:
            msg = QMessageBox()
            msg.setWindowTitle("Error")
            msg.setText(f"Calculation failed: {str(error)}")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setStyleSheet("color: red;")
            msg.exec()
        else:
            msg = QMessageBox()
            msg.setWindowTitle("Success")
            msg.setText("Calculations successfully completed.")
            msg.exec()

            # Clear text fields
            self.dicom_1_text.setText("")
            self.mask_1_text.setText("")
            self.dicom_2_text.setText("")
            self.mask_2_text.setText("")
        finally:
            # Stop the loading animation
            self.movie.stop()
            self.label.hide()
            # Save the last selected DICOM path
            if self.dicom_1_text.text():
                self.save_last_dicom_path(os.path.dirname(self.dicom_1_text.text()))

    def save_last_dicom_path(self, path: str) -> None:
        """
        Save the last selected DICOM path to the Windows Registry.

        :param path: Path to save
        """
        key = wr.CreateKey(wr.HKEY_CURRENT_USER, r'Software\MaskRegistration')
        wr.SetValueEx(key, 'LastDICOMPath', 0, wr.REG_SZ, path)
        wr.CloseKey(key)

    def get_last_dicom_path(self) -> str:
        """
        Retrieve the last selected DICOM path from the Windows Registry.

        :return: Last DICOM path
        """
        try:
            key = wr.OpenKey(wr.HKEY_CURRENT_USER, r'Software\MaskRegistration')
            path, _ = wr.QueryValueEx(key, 'LastDICOMPath')
            wr.CloseKey(key)
            return path
        except Exception:
            return QtCore.QDir.currentPath()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MaskRegistration()
    window.show()
    app.exec()
