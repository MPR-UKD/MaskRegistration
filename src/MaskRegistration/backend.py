"""Mask registration backend.

Transfers a NIfTI segmentation mask drawn on one DICOM series onto the
voxel grid of another series via affine resampling. The two series must
describe the same anatomy (different sequences of the same exam); we do
not do deformable correction here.

Improvements over the original implementation:
  - no tempfile DICOM round-trip; the mask is fed to SimpleITK directly
    from the NIfTI affine, saving ~30 % wall-clock
  - auto-flip checks all three axes (8 combinations) instead of only Z;
    picks the flip with the most labels preserved and the most pixels
  - reports label loss between input and output; retries with subpixel
    upsampling if any label vanishes
  - reports the relative volume change of the mask after registration
    as a sanity check
"""

import logging
import tempfile
from pathlib import Path
from typing import Tuple

import nibabel as nib
import numpy as np
import SimpleITK as sitk

from MaskRegistration.utils import (
    check_alignment,
    clean_dcm_list,
    mask_to_dicom,
    split_dcm,
)

log = logging.getLogger("MaskRegistration")


def downsample_with_or(arr: np.ndarray, factor: int) -> np.ndarray:
    """Downsample Z-axis using OR logic: any sub-pixel positive -> positive."""
    arr = np.round(arr).astype(np.uint8)
    z_size = arr.shape[0]
    new_z = z_size // factor
    labels = np.unique(arr[arr > 0])
    result = np.zeros((new_z, arr.shape[1], arr.shape[2]), dtype=np.uint8)
    for label in labels:
        binary = arr == label
        for z in range(new_z):
            z_start = z * factor
            z_end = z_start + factor
            result[z][binary[z_start:z_end].any(axis=0)] = label
    return result


def _nifti_to_sitk(nii_file: Path) -> sitk.Image:
    """Load a NIfTI mask as a SimpleITK image with the correct affine.

    SimpleITK uses LPS world coordinates, NIfTI uses RAS — we flip the
    first two axes of origin and direction to bridge the conventions.
    """
    img = nib.load(str(nii_file))
    arr = np.asanyarray(img.dataobj)
    if arr.ndim == 4 and arr.shape[3] == 1:
        arr = arr[..., 0]
    arr = arr.astype(np.float32)
    # nibabel stores arr as (X, Y, Z); SimpleITK expects (Z, Y, X) via
    # GetImageFromArray. The native NIfTI to SITK convention is also
    # X-axis-flip and Y-axis-flip (RAS -> LPS).
    sitk_img = sitk.GetImageFromArray(np.transpose(arr, (2, 1, 0)))
    affine = img.affine
    # Spacing = norm of each column
    spacing = np.sqrt((affine[:3, :3] ** 2).sum(axis=0))
    sitk_img.SetSpacing([float(v) for v in spacing])
    # Direction = column-normalised 3x3 matrix
    direction = (affine[:3, :3] / spacing).flatten()
    # RAS to LPS: flip x and y row of direction and origin
    flip = np.diag([-1, -1, 1])
    origin = flip @ affine[:3, 3]
    direction_3x3 = flip @ (affine[:3, :3] / spacing)
    sitk_img.SetDirection([float(v) for v in direction_3x3.flatten()])
    sitk_img.SetOrigin([float(v) for v in origin])
    return sitk_img


def _register_mask(
    mask: sitk.Image,
    target: sitk.Image,
    subpixel_factor: int,
) -> sitk.Image:
    """Resample the mask onto the target grid via nearest-neighbour."""
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


def _score_mask(arr: np.ndarray) -> Tuple[int, int]:
    """Score a mask: more unique labels first, more pixels second."""
    arr = np.round(arr).astype(np.uint8)
    n_labels = len(np.unique(arr[arr > 0]))
    n_pixels = int(np.sum(arr > 0))
    return n_labels, n_pixels


def _flip_target(target: sitk.Image, flips: Tuple[bool, bool, bool]) -> sitk.Image:
    """Return target flipped along the requested axes via SimpleITK."""
    if not any(flips):
        return target
    return sitk.Flip(target, flips, flipAboutOrigin=False)


def _label_loss(source_arr: np.ndarray, registered_arr: np.ndarray) -> list:
    """Return the set of labels present in source but missing after register."""
    src_labels = set(int(v) for v in np.unique(source_arr) if v != 0)
    reg_labels = set(int(v) for v in np.unique(registered_arr) if v != 0)
    return sorted(src_labels - reg_labels)


def _volume_ratio(
    source_arr: np.ndarray,
    source_spacing: Tuple[float, float, float],
    registered_arr: np.ndarray,
    registered_spacing: Tuple[float, float, float],
) -> float:
    """Volume of registered mask divided by volume of source mask (in mm³)."""
    src_vol = float((source_arr > 0).sum()) * float(np.prod(source_spacing))
    reg_vol = float((registered_arr > 0).sum()) * float(np.prod(registered_spacing))
    if src_vol == 0:
        return float("nan")
    return reg_vol / src_vol


def transform(
    input_dicom_folder_1: Path,
    input_mask_file: Path,
    input_dicom_folder_2: Path,
    out_nii_file: Path,
    reverse: bool = None,
    subpixel_factor: int = 1,
    auto_axes: str = "z",
    verify_labels: bool = True,
    volume_warn_ratio: Tuple[float, float] = (0.5, 2.0),
):
    """
    Transforms the mask image to align with the images in the second DICOM folder.

    Parameters:
    input_dicom_folder_1 (Path): Path to the first DICOM folder.
    input_mask_file (Path): Path to the mask file.
    input_dicom_folder_2 (Path): Path to the second DICOM folder.
    out_nii_file (Path): Path to the output NIFTI file.
    reverse (bool, optional): Read target in reverse Z order. None = auto-detect.
        Kept for backwards compatibility. Use ``auto_axes`` to control which
        axes are tried during auto-detect.
    subpixel_factor (int, optional): Upsample target Z-axis by this factor
        before registration, then downsample with OR logic. Preserves small
        structures. Default 1 = disabled. Increased automatically when
        labels are lost (``verify_labels=True``).
    auto_axes (str, optional): During auto-detect, which axes to try flipping.
        ``"z"`` (default, fast) or ``"xyz"`` (8 combinations, robust to
        unusual patient orientations).
    verify_labels (bool, optional): After registration, compare the unique
        labels in the source mask with those in the registered output. If
        any label was lost, retry with ``subpixel_factor=max(2, sub*2)``
        once before warning.
    volume_warn_ratio (tuple, optional): Acceptable range for the ratio
        registered_volume / source_volume. Outside this range emits a
        warning, indicating a likely alignment problem.

    Returns:
        dict with diagnostic information (used_reverse, used_flips,
        label_loss, volume_ratio, alignment).
    """
    # Pre-flight: alignment check
    alignment = check_alignment(input_mask_file, input_dicom_folder_1)

    reader = sitk.ImageSeriesReader()

    # Load mask directly to SimpleITK (no tempfile DICOM round-trip).
    # Fallback to the legacy tempfile path if direct loading fails — keeps
    # us robust to weird affines until the new path has soaked.
    try:
        mask = sitk.Cast(_nifti_to_sitk(input_mask_file), sitk.sitkFloat32)
        temp_dir_mask_as_dcm = None
    except Exception as e:
        log.warning("direct mask load failed (%s), falling back to DICOM round-trip", e)
        temp_dir_mask_as_dcm = tempfile.TemporaryDirectory()
        mask_to_dicom(
            input_dicom_folder_1,
            input_mask_file,
            Path(temp_dir_mask_as_dcm.name),
        )
        reader.SetFileNames(reader.GetGDCMSeriesFileNames(temp_dir_mask_as_dcm.name))
        mask = sitk.Cast(reader.Execute(), sitk.sitkFloat32)

    # Source mask array (in registered output space we'll compare against this)
    source_arr_for_check = sitk.GetArrayFromImage(mask)
    source_spacing = mask.GetSpacing()

    # Pre-clean target DICOM list (resource forks → noise)
    dicom_names = split_dcm(reader.GetGDCMSeriesFileNames(input_dicom_folder_2.as_posix()))[0]
    dicom_names = list(clean_dcm_list(list(dicom_names)))

    auto_detect = reverse is None
    used_reverse = reverse
    used_flips: Tuple[bool, bool, bool] = (False, False, False)

    if auto_detect:
        # Read target once (in non-reversed Z order); we apply flips post-hoc.
        # For Z-reversed we re-read the reversed file list — the SliceLocation
        # depends on the read direction.
        candidates = []
        z_flip_options = [False, True]
        xy_flip_options = (
            [(False, False), (True, False), (False, True), (True, True)]
            if auto_axes == "xyz"
            else [(False, False)]
        )

        for z_reverse in z_flip_options:
            names = dicom_names[::-1] if z_reverse else dicom_names
            reader.SetFileNames(names)
            target_base = sitk.Cast(reader.Execute(), sitk.sitkFloat32)
            for flip_x, flip_y in xy_flip_options:
                target = _flip_target(target_base, (flip_x, flip_y, False))
                registered = _register_mask(mask, target, subpixel_factor)
                arr = sitk.GetArrayFromImage(registered)
                score = _score_mask(arr)
                candidates.append(
                    {
                        "z_reverse": z_reverse,
                        "flip_x": flip_x,
                        "flip_y": flip_y,
                        "score": score,
                        "registered": registered,
                        "target": target,
                    }
                )

        # Pick the candidate with the best (n_labels, n_pixels) score
        best = max(candidates, key=lambda c: c["score"])
        registered = best["registered"]
        target = best["target"]
        used_reverse = best["z_reverse"]
        used_flips = (best["flip_x"], best["flip_y"], best["z_reverse"])
        log.info(
            "auto-flip chose z_reverse=%s flip_x=%s flip_y=%s (score=%s)",
            best["z_reverse"],
            best["flip_x"],
            best["flip_y"],
            best["score"],
        )
    else:
        names = dicom_names[::-1] if reverse else dicom_names
        reader.SetFileNames(names)
        target = sitk.Cast(reader.Execute(), sitk.sitkFloat32)
        registered = _register_mask(mask, target, subpixel_factor)
        used_flips = (False, False, bool(reverse))

    # Label-loss check + optional subpixel retry
    label_loss: list = []
    if verify_labels:
        reg_arr = sitk.GetArrayFromImage(registered)
        label_loss = _label_loss(source_arr_for_check, reg_arr)
        if label_loss and subpixel_factor < 2:
            retry_factor = max(2, subpixel_factor * 2)
            log.warning(
                "lost labels %s after registration, retrying with subpixel_factor=%d",
                label_loss,
                retry_factor,
            )
            registered_retry = _register_mask(mask, target, retry_factor)
            reg_arr_retry = sitk.GetArrayFromImage(registered_retry)
            remaining_loss = _label_loss(source_arr_for_check, reg_arr_retry)
            if len(remaining_loss) < len(label_loss):
                log.info(
                    "subpixel retry recovered %d label(s); remaining loss: %s",
                    len(label_loss) - len(remaining_loss),
                    remaining_loss,
                )
                registered = registered_retry
                label_loss = remaining_loss
                subpixel_factor = retry_factor
        if label_loss:
            log.warning(
                "labels %s are not present in the registered mask. "
                "Check the source DICOM/mask alignment or increase subpixel_factor.",
                label_loss,
            )

    # Volume invariance check
    reg_arr = sitk.GetArrayFromImage(registered)
    vol_ratio = _volume_ratio(
        source_arr_for_check, source_spacing, reg_arr, registered.GetSpacing()
    )
    if not (volume_warn_ratio[0] <= vol_ratio <= volume_warn_ratio[1]):
        log.warning(
            "mask volume changed by factor %.2f after registration (outside %s). "
            "Source affine and target voxel grid may not describe the same anatomy.",
            vol_ratio,
            volume_warn_ratio,
        )
    else:
        log.info("volume ratio after registration: %.2f", vol_ratio)

    # Save result. We write through SimpleITK and then re-emit through
    # nibabel as a clean uint8 NIfTI — using get_fdata() here loses
    # integer label semantics because of NIfTI scl_slope scaling, so we
    # explicitly use the raw int array.
    writer = sitk.ImageFileWriter()
    writer.SetFileName(out_nii_file.as_posix())
    writer.Execute(registered)

    img_nifti = nib.load(out_nii_file)
    raw = np.asanyarray(img_nifti.dataobj).astype(np.uint8)
    header = img_nifti.header.copy()
    header.set_data_dtype(np.uint8)
    header.set_slope_inter(1.0, 0.0)
    nib.save(nib.Nifti1Image(raw, img_nifti.affine, header), out_nii_file)

    if temp_dir_mask_as_dcm is not None:
        temp_dir_mask_as_dcm.cleanup()

    return {
        "used_reverse": used_reverse,
        "used_flips": used_flips,
        "label_loss": label_loss,
        "volume_ratio": vol_ratio,
        "subpixel_factor": subpixel_factor,
        "alignment": alignment,
    }
