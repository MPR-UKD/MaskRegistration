import sys
import os
import winreg as wr
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWidgets import *
from PyQt6.QtCore import QThread, pyqtSignal
from src.MaskRegistration.backend import transform


class RegistrationThread(QThread):
    finished_signal = pyqtSignal(str, bool)

    def __init__(self, dicom_1, mask_1, dicom_2, mask_2):
        super().__init__()
        self.dicom_1 = dicom_1
        self.mask_1 = mask_1
        self.dicom_2 = dicom_2
        self.mask_2 = mask_2

    def run(self):
        try:
            transform(
                input_dicom_folder_1=Path(self.dicom_1),
                input_mask_file=Path(self.mask_1),
                input_dicom_folder_2=Path(self.dicom_2),
                out_nii_file=Path(self.mask_2),
            )
        except Exception as error:
            self.finished_signal.emit(str(error), False)
        else:
            self.finished_signal.emit("Calculations successfully completed.", True)


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

        # Create a QWidget for the popup
        self.popup_widget = QWidget()
        self.popup_widget.setWindowTitle("Registration and Transformation")
        self.popup_widget.setFixedSize(580, 320)
        self.popup_layout = QVBoxLayout()

        # Adding gif animation
        if getattr(sys, 'frozen', False):
            # If it's compiled, adjust the path
            base_path = sys._MEIPASS
        else:
            # Otherwise, the path remains the same
            base_path = os.path.dirname(os.path.abspath(__file__))

            # Now, use this base_path to reference your gif
        gif_path = os.path.join(base_path, 'loading.gif')


        self.movie = QtGui.QMovie(gif_path)
        self.movie.setScaledSize(QtCore.QSize(548, 309))
        self.label = QLabel(self.popup_widget)
        self.label.setMovie(self.movie)
        self.popup_layout.addWidget(self.label)
        self.popup_widget.setLayout(self.popup_layout)

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
        if dialog != "":
            self.save_last_dicom_path(Path(dialog).parent.as_posix())

    def update_dicom_1(self) -> None:
        """Update the dicom_1_text field with the selected directory."""
        self.file_dialog("Select Dicom Path 1", self.dicom_1_text, "DIR")
        if self.dicom_1_text.text() != "" and self.mask_1_text.text() == "":
            if (Path(self.dicom_1_text.text()) / "mask.nii.gz").exists():
                self.mask_1_text.setText(
                    os.path.join(self.dicom_1_text.text(), "mask.nii.gz")
                )

    def update_mask_1(self) -> None:
        """Update the mask_1_text field with the selected file."""
        self.file_dialog("Select Mask File 1", self.mask_1_text, "FILE")

    def update_dicom_2(self) -> None:
        """Update the dicom_2_text field with the selected directory."""
        self.file_dialog("Select Dicom Path 2", self.dicom_2_text, "DIR")
        if self.dicom_2_text.text() != "" and self.mask_2_text.text() == "":
            self.mask_2_text.setText(
                os.path.join(self.dicom_2_text.text(), "mask.nii.gz")
            )

    def update_mask_2(self) -> None:
        """Update the mask_2_text field with the selected file."""
        self.file_dialog("Select Save File Mask", self.mask_2_text, "SAVE_FILE")

    def run_registration(self):
        self.run.setEnabled(False)  # Deactivate RUN button
        self.popup_widget.show()
        self.movie.start()

        # Start registration in a separate thread
        try:
            if (
                not self.dicom_1_text.text()
                or not self.mask_1_text.text()
                or not self.dicom_2_text.text()
                or not self.mask_2_text.text()
            ):
                raise ValueError("Please fill in all the required fields.")
            self.registration_thread = RegistrationThread(
                self.dicom_1_text.text(),
                self.mask_1_text.text(),
                self.dicom_2_text.text(),
                self.mask_2_text.text(),
            )
            self.registration_thread.finished_signal.connect(self.registration_finished)
            self.registration_thread.start()
        except Exception as error:
            self.run.setEnabled(True)  # Deactivate RUN button
            self.popup_widget.close()
            self.movie.stop()
            msg = QMessageBox()
            msg.setWindowTitle("Error")
            msg.setText(f"Calculation failed: {str(error)}")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setStyleSheet("color: red;")
            msg.exec()

    def registration_finished(self, message, success):
        # Reactivate RUN button
        self.run.setEnabled(True)
        # Stop the loading animation
        self.popup_widget.close()
        self.movie.stop()
        # Show message box
        msg = QMessageBox()
        msg.setWindowTitle("Success" if success else "Error")
        if success:
            msg.setText("Calculations successfully completed.")
        msg.setText(message)
        msg.setIcon(
            QMessageBox.Icon.Information if success else QMessageBox.Icon.Warning
        )
        msg.exec()
        # Clear text fields if successful
        if success:
            self.dicom_1_text.setText("")
            self.mask_1_text.setText("")
            self.dicom_2_text.setText("")
            self.mask_2_text.setText("")

    def save_last_dicom_path(self, path: str) -> None:
        """
        Save the last selected DICOM path to the Windows Registry.

        :param path: Path to save
        """
        key = wr.CreateKey(wr.HKEY_CURRENT_USER, r"Software\MaskRegistration")
        wr.SetValueEx(key, "LastDICOMPath", 0, wr.REG_SZ, path)
        wr.CloseKey(key)

    def get_last_dicom_path(self) -> str:
        """
        Retrieve the last selected DICOM path from the Windows Registry.

        :return: Last DICOM path
        """
        try:
            key = wr.OpenKey(wr.HKEY_CURRENT_USER, r"Software\MaskRegistration")
            path, _ = wr.QueryValueEx(key, "LastDICOMPath")
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
