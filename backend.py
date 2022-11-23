import tempfile

import SimpleITK as sitk

from utils import *


def transform(input_dicom_folder_1: Path,
              input_mask_file: Path,
              input_dicom_folder_2: Path,
              out_nii_file: Path,
              reverse: bool = False):

    # init SimpleITK reader and writer
    reader = sitk.ImageSeriesReader()
    writer = sitk.ImageFileWriter()

    #
    reverse = False if reverse is None else reverse

    while True:
        dicom_names = split_dcm(reader.GetGDCMSeriesFileNames(input_dicom_folder_2.as_posix()))[0]
        if reverse:
            dicom_names = dicom_names[::-1]

        reader.SetFileNames(dicom_names)
        target = reader.Execute()

        temp_dir_mask_as_dcm = tempfile.TemporaryDirectory()

        mask_to_dicom(input_dicom_folder_1, input_mask_file, Path(temp_dir_mask_as_dcm.name))
        # read mask_file
        reader.SetFileNames(reader.GetGDCMSeriesFileNames(temp_dir_mask_as_dcm.name))
        mask = reader.Execute()
        # cast to float for registration
        mask = sitk.Cast(mask, sitk.sitkFloat32)
        target = sitk.Cast(target, sitk.sitkFloat32)

        # Registration of mask_as_dcm to input_dicom_folder_2
        resampleFilter = sitk.ResampleImageFilter()
        resampleFilter.SetInterpolator(sitk.sitkNearestNeighbor)

        # Transform mask_image
        resampleFilter.SetSize(target.GetSize())
        resampleFilter.SetOutputOrigin(target.GetOrigin())
        resampleFilter.SetOutputSpacing(target.GetSpacing())
        resampleFilter.SetOutputDirection(target.GetDirection())
        resampleFilter.SetOutputPixelType(sitk.sitkInt8)
        resampleFilter.SetDefaultPixelValue(0.0)

        registeredImg = resampleFilter.Execute(mask)
        registeredImg = sitk.Cast(registeredImg, sitk.sitkUInt8)
        writer.SetFileName(out_nii_file.as_posix())

        writer.Execute(registeredImg)
        img_nifti = nib.load(out_nii_file)
        img = img_nifti.get_data()
        if reverse:
            break
        if img.max() == 0:
            reverse = True
        else:
            break
    img_nifti = nib.Nifti1Image(img, img_nifti.affine, img_nifti.header)
    nib.save(img_nifti, out_nii_file)
    temp_dir_mask_as_dcm.cleanup()

