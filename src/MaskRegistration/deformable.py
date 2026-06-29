"""Deformable (non-rigid) image registration.

When two scans show the same anatomy but the patient moved between them
(e.g. between two MRI visits on consecutive days), a pure affine resample
puts the mask in the wrong place. This module fits a dense displacement
vector field that aligns the source onto the target at the voxel level,
then warps the mask through that field.

Two backends:
  - ``"sitk"`` (default fallback) — pure SimpleITK, no extra dep
  - ``"elastix"`` (recommended when installed) — itk-elastix with
    validated parameter presets; usually more accurate out of the box

Run ``available_backends()`` to see which are installable. ``"auto"``
picks the best one (elastix if installed, otherwise sitk).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import nibabel as nib
import numpy as np
import SimpleITK as sitk

from MaskRegistration.backend import _nifti_to_sitk
from MaskRegistration.backends import (  # noqa: F401 — re-exported below
    available_backends,
    get_backend,
)
from MaskRegistration.utils import clean_dcm_list

log = logging.getLogger("MaskRegistration")


@dataclass
class DeformableResult:
    """Backend-agnostic result of a deformable registration."""

    warped_mask: Optional[sitk.Image]
    displacement_field: sitk.Image
    final_metric: float
    iterations: int
    backend: str = "unknown"
    used_demons: bool = False
    warnings: list[str] = field(default_factory=list)


def _read_dicom_series(folder: Path) -> sitk.Image:
    """Read a DICOM folder as a SimpleITK image, ignoring resource forks."""
    folder = Path(folder)
    files = clean_dcm_list(sorted(str(f) for f in folder.glob("*.dcm")))
    if not files:
        raise FileNotFoundError(f"no DICOM files in {folder}")
    reader = sitk.ImageSeriesReader()
    reader.SetFileNames(reader.GetGDCMSeriesFileNames(str(folder)))
    return sitk.Cast(reader.Execute(), sitk.sitkFloat32)


def _resample_to_match(moving: sitk.Image, fixed: sitk.Image) -> sitk.Image:
    f = sitk.ResampleImageFilter()
    f.SetReferenceImage(fixed)
    f.SetInterpolator(sitk.sitkLinear)
    f.SetDefaultPixelValue(0.0)
    return f.Execute(moving)


def deformable_register(
    source_image: sitk.Image,
    target_image: sitk.Image,
    source_mask: Optional[sitk.Image] = None,
    *,
    backend: str = "auto",
    n_iterations: int = 200,
    use_demons: bool = True,
    initial_alignment: str = "rigid+affine",
    fixed_mask: Optional[sitk.Image] = None,
    moving_mask: Optional[sitk.Image] = None,
) -> DeformableResult:
    """Estimate a deformable transform that maps source onto target.

    Args:
        source_image: moving image.
        target_image: fixed reference image.
        source_mask: optional mask in source space; warped through the
            full composite transform with nearest-neighbour interpolation.
        backend: which engine to use. ``"auto"`` (default) picks elastix
            if installed, otherwise SimpleITK. Pass ``"sitk"`` or
            ``"elastix"`` to force one.
        n_iterations: max iterations per registration stage.
        use_demons: SimpleITK only — refine the B-spline result with
            Symmetric Forces Demons. Ignored by elastix.
        initial_alignment: which pre-stages to run before the deformable
            step. ``"rigid+affine"`` (default, robust to repositioning),
            ``"rigid"``, or ``"none"`` (assume already aligned).

    Returns:
        DeformableResult with the warped mask, the dense displacement
        field, the final metric value and the iteration count.
    """
    eng = get_backend(backend)
    log.info("deformable backend: %s", eng.name)
    raw = eng.register(
        fixed=target_image,
        moving=source_image,
        source_mask=source_mask,
        n_iterations=n_iterations,
        use_demons=use_demons,
        initial_alignment=initial_alignment,
        fixed_mask=fixed_mask,
        moving_mask=moving_mask,
    )
    return DeformableResult(
        warped_mask=raw.warped_mask,
        displacement_field=raw.displacement_field,
        final_metric=raw.final_metric,
        iterations=raw.iterations,
        backend=raw.backend,
        used_demons=raw.extra.get("used_demons", False),
    )


def transform_deformable(
    input_dicom_folder_1: Path,
    input_mask_file: Path,
    input_dicom_folder_2: Path,
    out_nii_file: Path,
    out_displacement_file: Optional[Path] = None,
    *,
    backend: str = "auto",
    n_iterations: int = 200,
    use_demons: bool = True,
    initial_alignment: str = "rigid+affine",
) -> dict:
    """Full deformable registration of a mask from one DICOM series onto
    another, including patient motion / non-rigid deformation.

    See ``deformable_register`` for backend choices.
    """
    log.info(
        "deformable register (%s): %s -> %s",
        backend,
        input_dicom_folder_1,
        input_dicom_folder_2,
    )
    source_img = _read_dicom_series(Path(input_dicom_folder_1))
    target_img = _read_dicom_series(Path(input_dicom_folder_2))
    mask_img = sitk.Cast(_nifti_to_sitk(Path(input_mask_file)), sitk.sitkFloat32)
    # Bring mask to source grid first (mask is in source-space)
    if mask_img.GetSize() != source_img.GetSize():
        rf = sitk.ResampleImageFilter()
        rf.SetReferenceImage(source_img)
        rf.SetInterpolator(sitk.sitkNearestNeighbor)
        rf.SetDefaultPixelValue(0)
        mask_img = sitk.Cast(rf.Execute(mask_img), sitk.sitkUInt8)

    result = deformable_register(
        source_img,
        target_img,
        source_mask=mask_img,
        backend=backend,
        n_iterations=n_iterations,
        use_demons=use_demons,
        initial_alignment=initial_alignment,
    )

    # Save warped mask as clean uint8 NIfTI (scl_slope=1, scl_inter=0)
    sitk.WriteImage(result.warped_mask, str(out_nii_file))
    raw = nib.load(str(out_nii_file))
    arr = np.asanyarray(raw.dataobj).astype(np.uint8)
    header = raw.header.copy()
    header.set_data_dtype(np.uint8)
    header.set_slope_inter(1.0, 0.0)
    nib.save(nib.Nifti1Image(arr, raw.affine, header), out_nii_file)

    if out_displacement_file is not None:
        sitk.WriteImage(result.displacement_field, str(out_displacement_file))

    return {
        "backend": result.backend,
        "final_metric": result.final_metric,
        "iterations": result.iterations,
        "used_demons": result.used_demons,
        "displacement_file": str(out_displacement_file) if out_displacement_file else None,
    }
