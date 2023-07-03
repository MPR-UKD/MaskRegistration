import tempfile

import SimpleITK as sitk

from src.MaskRegistration.utils import *


def transform(
    input_dicom_folder_1: Path,
    input_mask_file: Path,
    input_dicom_folder_2: Path,
    out_nii_file: Path,
    reverse: bool = False,
):
    """
    Transforms the mask image to align with the images in the second DICOM folder, using the images in the first DICOM folder as reference.
    The resulting image is saved in NIFTI format.

    Parameters:
    input_dicom_folder_1 (Path): Path to the first DICOM folder.
    input_mask_file (Path): Path to the mask file.
    input_dicom_folder_2 (Path): Path to the second DICOM folder.
    out_nii_file (Path): Path to the output NIFTI file.
    reverse (bool, optional): Flag to specify whether the images in the second DICOM folder should be read in reverse order. Default is False.
    """

    # Initialize a SimpleITK ImageSeriesReader and ImageFileWriter
    reader = sitk.ImageSeriesReader()
    writer = sitk.ImageFileWriter()

    # Set reverse to False if it is None
    reverse = False if reverse is None else reverse

    while True:
        # Read the images from input_dicom_folder_2 using the ImageSeriesReader
        dicom_names = split_dcm(
            reader.GetGDCMSeriesFileNames(input_dicom_folder_2.as_posix())
        )[0]
        # Reverse the order of the images if reverse is True
        if reverse:
            dicom_names = dicom_names[::-1]
        reader.SetFileNames(dicom_names)
        target = reader.Execute()

        # Create a temporary directory and convert the mask file to a DICOM image using the mask_to_dicom function
        temp_dir_mask_as_dcm = tempfile.TemporaryDirectory()
        mask_to_dicom(
            input_dicom_folder_1, input_mask_file, Path(temp_dir_mask_as_dcm.name)
        )

        # Read the mask image from the temporary directory
        reader.SetFileNames(reader.GetGDCMSeriesFileNames(temp_dir_mask_as_dcm.name))
        mask = reader.Execute()

        # Cast the mask and target images to sitkFloat32 to prepare them for registration
        mask = sitk.Cast(mask, sitk.sitkFloat32)
        target = sitk.Cast(target, sitk.sitkFloat32)

        # Registration of mask_as_dcm to input_dicom_folder_2
        resampleFilter = sitk.ResampleImageFilter()
        # Use nearest neighbor interpolation
        resampleFilter.SetInterpolator(sitk.sitkNearestNeighbor)

        # Transform mask_image
        resampleFilter.SetSize(target.GetSize())
        resampleFilter.SetOutputOrigin(target.GetOrigin())
        resampleFilter.SetOutputSpacing(target.GetSpacing())
        resampleFilter.SetOutputDirection(target.GetDirection())
        resampleFilter.SetOutputPixelType(sitk.sitkInt8)
        resampleFilter.SetDefaultPixelValue(0.0)

        # Generate registered image
        registeredImg = resampleFilter.Execute(mask)
        registeredImg = sitk.Cast(registeredImg, sitk.sitkUInt8)
        writer.SetFileName(out_nii_file.as_posix())

        writer.Execute(registeredImg)
        img_nifti = nib.load(out_nii_file)
        img = img_nifti.get_fdata()
        if reverse:
            break
        if img.max() == 0:
            reverse = True
        else:
            break

    # Save registered mask as NIFTI
    img_nifti = nib.Nifti1Image(img, img_nifti.affine, img_nifti.header)
    nib.save(img_nifti, out_nii_file)
    temp_dir_mask_as_dcm.cleanup()
