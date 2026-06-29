"""Estimate a displacement field on a low-resolution sequence and apply
it to a higher-resolution sequence.

The patient deformation between two scans (e.g. T0 and T1 the next day)
is a property of the anatomy, not of the imaging sequence. If we estimate
the field on T2 maps (128x128x48) instead of DESS (256x256x176), we cut
registration time by ~10x while keeping the same anatomical accuracy at
the resolution scale that matters for mask transfer.

Pipeline:
  1. Register low-res source to low-res target -> displacement field A
     (in low-res world coords)
  2. Resample A onto the high-res target grid -> field A' (same physical
     coords, denser sampling)
  3. Apply A' to warp a mask defined on the high-res source

Caveats:
  - The two low-res scans must describe the same anatomy as the high-res
    scans (i.e. same patient, same body part, same physical positioning).
    The within-day relative position between the low-res and high-res
    sequence is taken from their DICOM affines — both must be valid.
  - If the patient moved a lot between the low-res and high-res
    acquisition within one session, the field transfer will be off by
    that intra-session motion. For a same-session protocol this is
    typically < 1 mm.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import nibabel as nib
import numpy as np
import SimpleITK as sitk

from MaskRegistration.backend import _nifti_to_sitk
from MaskRegistration.backends import get_backend
from MaskRegistration.utils import clean_dcm_list

log = logging.getLogger("MaskRegistration.field_transfer")


@dataclass
class FieldTransferResult:
    warped_mask: Optional[sitk.Image]
    displacement_field_lowres: sitk.Image
    displacement_field_highres: sitk.Image
    final_metric: float
    iterations: int
    backend: str
    speed_factor: float  # estimated speedup vs registering at high-res


def _read_dicom(folder: Path) -> sitk.Image:
    folder = Path(folder)
    files = clean_dcm_list(sorted(str(f) for f in folder.glob("*.dcm")))
    if not files:
        raise FileNotFoundError(f"no DICOM files in {folder}")
    reader = sitk.ImageSeriesReader()
    reader.SetFileNames(reader.GetGDCMSeriesFileNames(str(folder)))
    return sitk.Cast(reader.Execute(), sitk.sitkFloat32)


def _first_3d(img: sitk.Image) -> sitk.Image:
    """If a multi-echo image is 4D, take the first echo (highest SNR usually)."""
    if img.GetDimension() == 4:
        return img[:, :, :, 0]
    return img


def _resample_displacement_field(
    field_lowres: sitk.Image,
    target_grid: sitk.Image,
) -> sitk.Image:
    """Resample a 3-component displacement field onto a new grid.

    The field stores physical displacement in mm, so the resampling is
    just a geometric re-interpolation — the values themselves stay valid
    in physical units.
    """
    f = sitk.ResampleImageFilter()
    f.SetReferenceImage(target_grid)
    f.SetInterpolator(sitk.sitkLinear)
    f.SetDefaultPixelValue(0.0)
    # Cast displacement field to sitkVectorFloat64 if needed for resample
    field_cast = sitk.Cast(field_lowres, sitk.sitkVectorFloat64)
    return f.Execute(field_cast)


def estimate_field_lowres_apply_highres(
    lowres_source_dicom: Path,
    lowres_target_dicom: Path,
    highres_source_dicom: Path,
    highres_target_dicom: Path,
    source_mask_file: Path,
    out_warped_mask: Path,
    out_displacement_highres: Optional[Path] = None,
    *,
    backend: str = "auto",
    n_iterations: int = 200,
) -> FieldTransferResult:
    """Estimate the deformation on the low-res sequence, apply to high-res.

    Args:
        lowres_source_dicom: e.g. T2_T0 folder
        lowres_target_dicom: e.g. T2_T1 folder
        highres_source_dicom: e.g. DESS_T0 folder
        highres_target_dicom: e.g. DESS_T1 folder
        source_mask_file: NIfTI mask in highres-source space
        out_warped_mask: where to write the warped mask
        out_displacement_highres: optional, write the high-res field as NIfTI
        backend: registration engine ("auto", "sitk", "elastix")
        n_iterations: iterations for the registration stage

    Returns:
        FieldTransferResult with both the low-res and high-res field.
    """
    lowres_src = _first_3d(_read_dicom(lowres_source_dicom))
    lowres_tgt = _first_3d(_read_dicom(lowres_target_dicom))
    highres_tgt = _first_3d(_read_dicom(highres_target_dicom))
    mask_img = sitk.Cast(_nifti_to_sitk(source_mask_file), sitk.sitkFloat32)

    log.info(
        "field-transfer: low-res grid %s, high-res grid %s",
        lowres_src.GetSize(),
        highres_tgt.GetSize(),
    )

    # Speedup is a function of voxel-count ratio (registration cost ~ N).
    n_low = float(np.prod(lowres_src.GetSize()))
    n_high = float(np.prod(highres_tgt.GetSize()))
    speed_factor = n_high / n_low if n_low > 0 else 1.0

    eng = get_backend(backend)
    log.info("estimating field on low-res with backend=%s", eng.name)
    low_res_result = eng.register(
        fixed=lowres_tgt,
        moving=lowres_src,
        source_mask=None,
        n_iterations=n_iterations,
        use_demons=False,
        initial_alignment="rigid+affine",
    )
    field_lowres = low_res_result.displacement_field

    # Resample field onto high-res target grid
    log.info("resampling displacement field onto high-res grid")
    field_highres = _resample_displacement_field(field_lowres, highres_tgt)

    # Bring the source mask to the high-res target grid via the field
    # (the field describes target->source motion in physical mm, so we
    # use it as a DisplacementFieldTransform).
    composite_tx = sitk.DisplacementFieldTransform(sitk.Cast(field_highres, sitk.sitkVectorFloat64))
    mask_rf = sitk.ResampleImageFilter()
    mask_rf.SetReferenceImage(highres_tgt)
    mask_rf.SetInterpolator(sitk.sitkNearestNeighbor)
    mask_rf.SetDefaultPixelValue(0)
    mask_rf.SetTransform(composite_tx)
    warped = sitk.Cast(mask_rf.Execute(mask_img), sitk.sitkUInt8)

    # Write outputs
    sitk.WriteImage(warped, str(out_warped_mask))
    raw = nib.load(str(out_warped_mask))
    arr = np.asanyarray(raw.dataobj).astype(np.uint8)
    header = raw.header.copy()
    header.set_data_dtype(np.uint8)
    header.set_slope_inter(1.0, 0.0)
    nib.save(nib.Nifti1Image(arr, raw.affine, header), out_warped_mask)

    if out_displacement_highres is not None:
        sitk.WriteImage(field_highres, str(out_displacement_highres))

    return FieldTransferResult(
        warped_mask=warped,
        displacement_field_lowres=field_lowres,
        displacement_field_highres=field_highres,
        final_metric=low_res_result.final_metric,
        iterations=low_res_result.iterations,
        backend=low_res_result.backend,
        speed_factor=speed_factor,
    )
