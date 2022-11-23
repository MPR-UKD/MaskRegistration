from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5.QtCore import QSize
from pathlib import Path
from PyQt5.QtWidgets import *
import sys
from backend import transform


class MaskRegistration(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            "MaskRegistration - Wrapper for SimpleITK")
        myFont = QtGui.QFont()
        myFont.setPointSize(8)
        self.setFont(myFont)

        layout = QGridLayout()

        ###############################################################################################################
        #                                           input dicom 1                                                     #
        ###############################################################################################################
        dicom_1_button = QPushButton()
        dicom_1_button.setText('Load DICOM 1')
        layout.addWidget(dicom_1_button, 0, 0, 1, 1)
        dicom_1_text = QLineEdit()
        layout.addWidget(dicom_1_text, 0, 1, 1, 1)

        def update_dicom_1():
            self.file_dialog('Select Dicom path 1', dicom_1_text, 'DIR')
        dicom_1_button.clicked.connect(update_dicom_1)

        ###############################################################################################################
        #                                           input mask 1                                                      #
        ###############################################################################################################
        mask_1_button = QPushButton()
        mask_1_button.setText('Load mask 1')
        layout.addWidget(mask_1_button, 1, 0, 1, 1)
        mask_1_text = QLineEdit()
        layout.addWidget(mask_1_text, 1, 1, 1, 1)

        def update_mask_1():
            self.file_dialog('Select mask file 1', mask_1_text, 'FILE')
        mask_1_button.clicked.connect(update_mask_1)

        ###############################################################################################################
        #                                           input dicom 2                                                     #
        ###############################################################################################################
        dicom_2_button = QPushButton()
        dicom_2_button.setText('Load DICOM 2')
        layout.addWidget(dicom_2_button, 2, 0, 1, 1)
        dicom_2_text = QLineEdit()
        layout.addWidget(dicom_2_text, 2, 1, 1, 1)

        def update_dicom_2():
            self.file_dialog('Select Dicom path 2', dicom_2_text, 'DIR')
        dicom_2_button.clicked.connect(update_dicom_2)

        ###############################################################################################################
        #                                           input mask 2                                                      #
        ###############################################################################################################
        mask_2_button = QPushButton()
        mask_2_button.setText('Mask file 2')
        layout.addWidget(mask_2_button, 3, 0, 1, 1)
        mask_2_text = QLineEdit()
        layout.addWidget(mask_2_text, 3, 1, 1, 1)

        def update_mask_2():
            self.file_dialog('Select save file mask', mask_2_text, 'SAVE_FILE')
        mask_2_button.clicked.connect(update_mask_2)

        ###############################################################################################################
        #                                           input dicom 1                                                     #
        ###############################################################################################################
        run = QPushButton()
        run.setText('RUN')
        run.setMinimumHeight(80)
        myFont = QtGui.QFont()
        myFont.setPointSize(12)
        myFont.setBold(True)
        run.setFont(myFont)
        run.setStyleSheet("background-color : red")
        layout.addWidget(run, 0, 2, 4, 1)

        def run_registration():
            try:
                if dicom_1_text.text() == "" or mask_1_text.text() == "" or dicom_2_text.text() == "" or \
                        mask_2_text.text() == "":
                    raise TypeError(
                        "At least one argument (dicom_1, mask_1, dicom_2 or out_mask) is missing!"
                    )

                transform(input_dicom_folder_1=Path(dicom_1_text.text()),
                          input_mask_file=Path(mask_1_text.text()),
                          input_dicom_folder_2=Path(dicom_2_text.text()),
                          out_nii_file=Path(mask_2_text.text()))
            except Exception as error:
                msg = QMessageBox()
                msg.setWindowTitle("ERROR message")
                msg.setText(f"Calculation failed: with {error=}")
                msg.setIcon(QMessageBox.Warning)
                msg.setStyleSheet("color: rgb(255, 0, 0);")
                msg.exec_()
                return None

            msg = QMessageBox()
            msg.setWindowTitle("User massage")
            msg.setText("Calculations successfully completed")
            msg.setIcon(QMessageBox.Ok)
            msg.exec_()

            dicom_1_text.setText("")
            mask_1_text.setText("")
            dicom_2_text.setText("")
            mask_2_text.setText("")

        run.clicked.connect(run_registration)

        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)
        self.setMinimumSize(QSize(1200, 100))

    def file_dialog(self, text, line_edit, mode):
        path = QtCore.QDir.currentPath()
        if mode == 'DIR':
            dialog = QFileDialog.getExistingDirectory(self, text, path)
        elif mode == 'FILE':
            dialog = QFileDialog.getOpenFileName(self, text, path, 'NIFTI files (*.nii*)')[0]
        elif mode == 'SAVE_FILE':
            dialog = QFileDialog.getSaveFileName(self, text, path, 'NIFTI files (*.nii*)')[0]
        line_edit.setText(dialog)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('QtCurve')
    window = MaskRegistration()
    window.show()
    app.exec()
