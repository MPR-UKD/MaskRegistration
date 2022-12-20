# MaskRegistration
MaskRegistration is a wrapper-tool for [SimpleITK](https://github.com/SimpleITK/SimpleITK) that takes in two DICOM image folders and a mask file, and performs a registration process to align the mask file with the images in the second DICOM folder. The resulting image is then saved in NIFTI format.

**Registration Steps:**

1. Initialize a SimpleITK ImageSeriesReader and ImageFileWriter.
2. Read the DICOM images from input_dicom_folder_2 using the ImageSeriesReader, and store the result in the target variable. If the reverse parameter is True, the images are read in reverse order.
3. Create a temporary directory and use the mask_to_dicom function to convert the mask file to a DICOM image and save it in the temporary directory.
4. Read the mask image from the temporary directory using the ImageSeriesReader and store it in the mask variable.
5. Cast the mask and target images to sitkFloat32 to prepare them for registration.
6. Use a ResampleImageFilter to align the mask image with the target image. The ResampleImageFilter is configured to use nearest neighbor interpolation and to set the output image size, origin, spacing, and direction to match the target image.
7. Cast the registered image to sitkUInt8 and write it to the output NIFTI file using the ImageFileWriter.
8. Load the output NIFTI file using Nibabel, and check if the maximum value is 0. If it is, set the reverse flag to True and repeat the process from step 2. If the maximum value is not 0, exit the loop.
9. Save the image data from Nibabel to the output NIFTI file.
10. Clean up the temporary directory.

## Easy use

MaskRegistration can be easily used by downloading its included exe files:

- [CLI](/dist/MaskRegistration.exe)
- [GUI](/dist/MaskRegistrationGUI.exe)

## Environment Setup

Alternatively, you can use the Soruce code, which has the advantage that you can make changes.

1. Install [python3.10](https://www.python.org/downloads/release/python-3100/)
2. Clone MaskRegistration Repository
 ```bash
git clone https://github.com/ludgerradke/MaskRegistration
 ```
3. Open MaskRegistration
 ```bash
cd MaskRegistration
 ```
4. Install requirements.
 ```bash
 pip install -r requirements.txt
 ```
5. Run Command Line Interface (CLI) or Graphical User Interface (GUI)

## Command Line Interface (MaskRegistration.py)

The command-line tool that performs a registration process to align a mask image with a series of DICOM images. The resulting image is saved in NIFTI format.

### Usage
 ```bash
python MaskRegistration.py -d1 <input_dcm1> -m <input_mask> -d2 <input_dcm2> -o <output_mask>
 ```

Where:

- **input_dcm1** is the path to the first DICOM folder.
- **input_mask** is the path to the mask file.
- **input_dcm2** is the path to the second DICOM folder.
- **output_mask** is the path to the output NIFTI file.

### Example

To align the mask image mask.nii.gz with the images in the DICOM folder dicom_folder_2, using the images in the DICOM folder dicom_folder_1 as reference, and save the resulting image in the file output_mask.nii.gz, run the following command:

 ```bash
python MaskRegistration.py -d1 dicom_folder_1 -m mask.nii.gz -d2 dicom_folder_2 -o output_mask.nii.gz
 ```

## Graphical User Interface (GUI)

![](/images/GUI.png)

The MaskRegistration GUI is a PyQt5-based graphical user interface (GUI) that allows the user to input two DICOM image folders, a mask file, and an output file path, and performs a registration process to align the mask file with the images in the second DICOM folder. The resulting image is then saved in the specified output file.

The GUI consists of several widgets, including buttons, text fields, and a layout. The buttons allow the user to browse for and select the input DICOM folders, mask file, and output file. The text fields display the selected paths. The layout arranges the widgets in a grid.

The GUI also has a "RUN" button that, when clicked, executes the transform function from the backend module with the specified input and output paths.

The __init__ method sets up the main window and its layout, and initializes the widgets. The file_dialog method displays a file dialog and updates the specified text field with the selected file or directory path. The run method is executed when the "RUN" button is clicked, and calls the transform function with the specified input and output paths.

### Usage
 ```bash
python MaskRegistrationGUI.py
```

## License
[GNU General Public License 3](https://www.gnu.org/licenses/gpl-3.0.html)

The GNU General Public License is a free, copyleft license for software and other kinds of works.

### Git hocks
Install "pre-commit"
```bash
pip install pre-commit
```

then run:
```bash
pre-commit install
```

# Support

If you really like this repository and find it useful, please consider (★) starring it, so that it can reach a broader audience of like-minded people.
