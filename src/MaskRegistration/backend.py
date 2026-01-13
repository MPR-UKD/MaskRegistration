import tempfile

import numpy as np
import SimpleITK as sitk

from MaskRegistration.utils import *


def downsample_with_or(arr: np.ndarray, factor: int) -> np.ndarray:
    """Downsample Z-axis using OR logic: if any sub-pixel is positive, result is positive."""
    arr = np.round(arr).astype(np.uint8)
    z_size = arr.shape[0]
    new_z = z_size // factor
    labels = np.unique(arr[arr > 0])
    result = np.zeros((new_z, arr.shape[1], arr.shape[2]), dtype=np.uint8)

    for label in labels:
        binary = (arr == label)
        for z in range(new_z):
            z_start = z * factor
            z_end = z_start + factor
            result[z][binary[z_start:z_end].any(axis=0)] = label

    return result


def _register_mask(
    mask: sitk.Image,
    target: sitk.Image,
    subpixel_factor: int,
) -> sitk.Image:
    """Internal function to perform the actual registration."""
    resampleFilter = sitk.ResampleImageFilter()
    resampleFilter.SetInterpolator(sitk.sitkNearestNeighbor)
    resampleFilter.SetDefaultPixelValue(0.0)

    target_size = list(target.GetSize())
    target_spacing = list(target.GetSpacing())

    if subpixel_factor > 1:
        target_size[2] = target_size[2] * subpixel_factor
        target_spacing[2] = target_spacing[2] / subpixel_factor

    resampleFilter.SetSize(target_size)
    resampleFilter.SetOutputOrigin(target.GetOrigin())
    resampleFilter.SetOutputSpacing(target_spacing)
    resampleFilter.SetOutputDirection(target.GetDirection())
    resampleFilter.SetOutputPixelType(sitk.sitkInt8)

    registered = resampleFilter.Execute(mask)

    if subpixel_factor > 1:
        arr = sitk.GetArrayFromImage(registered)
        arr = downsample_with_or(arr, subpixel_factor)
        registered = sitk.GetImageFromArray(arr)
        registered.SetOrigin(target.GetOrigin())
        registered.SetSpacing(target.GetSpacing())
        registered.SetDirection(target.GetDirection())

    return sitk.Cast(registered, sitk.sitkUInt8)


def _score_mask(arr: np.ndarray) -> tuple[int, int]:
    """Score a mask by number of unique labels and total pixels."""
    arr = np.round(arr).astype(np.uint8)
    n_labels = len(np.unique(arr[arr > 0]))
    n_pixels = np.sum(arr > 0)
    return n_labels, n_pixels


def transform(
    input_dicom_folder_1: Path,
    input_mask_file: Path,
    input_dicom_folder_2: Path,
    out_nii_file: Path,
    reverse: bool = None,
    subpixel_factor: int = 1,
):
    """
    Transforms the mask image to align with the images in the second DICOM folder.

    Parameters:
    input_dicom_folder_1 (Path): Path to the first DICOM folder.
    input_mask_file (Path): Path to the mask file.
    input_dicom_folder_2 (Path): Path to the second DICOM folder.
    out_nii_file (Path): Path to the output NIFTI file.
    reverse (bool, optional): Read target in reverse order. None = auto-detect (default).
    subpixel_factor (int, optional): Upsample target Z-axis by this factor before registration,
        then downsample with OR logic. Preserves small structures. Default is 1 (disabled).
    """
    reader = sitk.ImageSeriesReader()

    # Prepare mask as DICOM
    temp_dir_mask_as_dcm = tempfile.TemporaryDirectory()
    mask_to_dicom(input_dicom_folder_1, input_mask_file, Path(temp_dir_mask_as_dcm.name))
    reader.SetFileNames(reader.GetGDCMSeriesFileNames(temp_dir_mask_as_dcm.name))
    mask = sitk.Cast(reader.Execute(), sitk.sitkFloat32)

    # Get target DICOM names
    dicom_names = split_dcm(reader.GetGDCMSeriesFileNames(input_dicom_folder_2.as_posix()))[0]

    auto_detect = reverse is None

    if auto_detect:
        # Try both directions, pick the better one
        results = {}
        for try_reverse in [False, True]:
            names = dicom_names[::-1] if try_reverse else dicom_names
            reader.SetFileNames(names)
            target = sitk.Cast(reader.Execute(), sitk.sitkFloat32)
            registered = _register_mask(mask, target, subpixel_factor)
            arr = sitk.GetArrayFromImage(registered)
            score = _score_mask(arr)
            results[try_reverse] = (registered, target, score)

        # Pick direction with more labels, then more pixels
        score_normal = results[False][2]
        score_reverse = results[True][2]

        if score_reverse > score_normal:
            registered, target, _ = results[True]
        else:
            registered, target, _ = results[False]
    else:
        # Use specified direction
        names = dicom_names[::-1] if reverse else dicom_names
        reader.SetFileNames(names)
        target = sitk.Cast(reader.Execute(), sitk.sitkFloat32)
        registered = _register_mask(mask, target, subpixel_factor)

    # Save result
    writer = sitk.ImageFileWriter()
    writer.SetFileName(out_nii_file.as_posix())
    writer.Execute(registered)

    img_nifti = nib.load(out_nii_file)
    img = img_nifti.get_fdata()
    img_nifti = nib.Nifti1Image(img, img_nifti.affine, img_nifti.header)
    nib.save(img_nifti, out_nii_file)

    temp_dir_mask_as_dcm.cleanup()
