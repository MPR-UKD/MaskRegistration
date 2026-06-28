"""Deformable (non-rigid) image registration.

When two scans show the same anatomy but the patient moved between
them (or the deformation is not just a rigid shift), a pure affine
resample of the mask gives the wrong overlap. This module fits a dense
displacement vector field that aligns the source image onto the target
image at the voxel level, then warps the mask through that field.

Pipeline (SimpleITK under the hood):
  1. Resample source and target onto a common physical grid.
  2. Multi-resolution registration with a B-spline transform initialised
     from the affine alignment.
  3. Optional Demons refinement that produces a dense displacement field.
  4. Apply the composite transform to the mask via nearest-neighbour.

Output is the warped mask plus the displacement field (X, Y, Z, 3) in
millimetres so downstream code can re-use it (for example to warp a
second mask without re-running the registration).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

import nibabel as nib
import numpy as np
import SimpleITK as sitk

from MaskRegistration.backend import _nifti_to_sitk
from MaskRegistration.utils import clean_dcm_list

log = logging.getLogger("MaskRegistration")


@dataclass
class DeformableResult:
    """What deformable_register returns."""

    warped_mask: sitk.Image
    displacement_field: sitk.Image
    final_metric: float
    iterations: int
    used_demons: bool
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
    """Resample a moving image onto the fixed image's grid (linear interp)."""
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
    n_iterations: int = 200,
    bspline_grid: Tuple[int, int, int] = (8, 8, 4),
    use_demons: bool = True,
    learning_rate: float = 1.0,
) -> DeformableResult:
    """Estimate a deformable transform that maps source onto target.

    Two-stage: a B-spline mutual-information registration, optionally
    followed by a Demons refinement that yields a dense displacement
    field. If ``source_mask`` is provided it is warped with the final
    transform and returned; otherwise the mask field is set to None.

    Args:
        source_image: moving image (will be deformed onto target).
        target_image: fixed reference image. Must be on the same physical
            grid as you want the output to live on.
        source_mask: optional mask in source space. Will be warped using
            nearest-neighbour interpolation.
        n_iterations: max LBFGS-B iterations for the B-spline stage.
        bspline_grid: control-point grid for the B-spline transform.
        use_demons: run a Demons refinement after the B-spline stage.
        learning_rate: B-spline optimiser step size.

    Returns:
        DeformableResult with warped mask, displacement field, final
        metric value and number of iterations.
    """
    fixed = sitk.Cast(target_image, sitk.sitkFloat32)
    moving = sitk.Cast(source_image, sitk.sitkFloat32)

    if moving.GetSize() != fixed.GetSize():
        moving = _resample_to_match(moving, fixed)

    # Initial transform: identity (caller is expected to have aligned the
    # two images roughly already, e.g. via the regular MaskRegistration
    # affine resample).
    transform_domain_mesh_size = list(bspline_grid)
    initial_tx = sitk.BSplineTransformInitializer(
        image1=fixed, transformDomainMeshSize=transform_domain_mesh_size
    )

    R = sitk.ImageRegistrationMethod()
    R.SetMetricAsMattesMutualInformation(numberOfHistogramBins=32)
    R.SetMetricSamplingStrategy(R.RANDOM)
    R.SetMetricSamplingPercentage(0.2)
    R.SetInterpolator(sitk.sitkLinear)
    R.SetOptimizerAsLBFGSB(
        gradientConvergenceTolerance=1e-5,
        numberOfIterations=n_iterations,
        maximumNumberOfCorrections=5,
        maximumNumberOfFunctionEvaluations=1000,
        costFunctionConvergenceFactor=1e7,
    )
    R.SetInitialTransformAsBSpline(initial_tx, inPlace=False)
    R.SetShrinkFactorsPerLevel(shrinkFactors=[4, 2, 1])
    R.SetSmoothingSigmasPerLevel(smoothingSigmas=[2, 1, 0])
    R.SmoothingSigmasAreSpecifiedInPhysicalUnitsOn()

    bspline_tx = R.Execute(fixed, moving)
    final_metric = R.GetMetricValue()
    iters = R.GetOptimizerIteration()
    log.info("deformable B-spline: metric=%.4f, iters=%d", final_metric, iters)

    # Optional Demons refinement on the pre-aligned moving image
    composite = sitk.CompositeTransform(bspline_tx)
    used_demons = False
    if use_demons:
        try:
            pre_aligned = sitk.Resample(moving, fixed, bspline_tx, sitk.sitkLinear, 0.0)
            demons = sitk.FastSymmetricForcesDemonsRegistrationFilter()
            demons.SetNumberOfIterations(50)
            demons.SetStandardDeviations(1.5)
            demons_field = demons.Execute(fixed, pre_aligned)
            demons_tx = sitk.DisplacementFieldTransform(demons_field)
            composite.AddTransform(demons_tx)
            used_demons = True
            log.info("Demons refinement: %d iters", demons.GetNumberOfIterations())
        except Exception as e:
            log.warning("Demons refinement failed (%s), keeping B-spline only", e)

    # Materialise the dense displacement field for downstream re-use.
    displacement_filter = sitk.TransformToDisplacementFieldFilter()
    displacement_filter.SetReferenceImage(fixed)
    displacement_field = displacement_filter.Execute(composite)

    # Warp the mask with the composite transform (nearest-neighbour)
    warped_mask = None
    if source_mask is not None:
        mask_resampler = sitk.ResampleImageFilter()
        mask_resampler.SetReferenceImage(fixed)
        mask_resampler.SetInterpolator(sitk.sitkNearestNeighbor)
        mask_resampler.SetDefaultPixelValue(0)
        mask_resampler.SetTransform(composite)
        warped_mask = sitk.Cast(
            mask_resampler.Execute(sitk.Cast(source_mask, sitk.sitkFloat32)),
            sitk.sitkUInt8,
        )

    return DeformableResult(
        warped_mask=warped_mask,
        displacement_field=displacement_field,
        final_metric=float(final_metric),
        iterations=int(iters),
        used_demons=used_demons,
    )


def transform_deformable(
    input_dicom_folder_1: Path,
    input_mask_file: Path,
    input_dicom_folder_2: Path,
    out_nii_file: Path,
    out_displacement_file: Optional[Path] = None,
    *,
    n_iterations: int = 200,
    use_demons: bool = True,
) -> dict:
    """Full deformable registration of a mask from one DICOM series onto
    another, including patient motion / non-rigid deformation.

    This is the heavy-weight counterpart to ``transform()``. Use it when
    the two acquisitions actually moved against each other (different
    days, between-scan motion, organ shift) and a pure affine resample
    would put the mask in the wrong place.
    """
    log.info("deformable register: %s -> %s", input_dicom_folder_1, input_dicom_folder_2)
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
        n_iterations=n_iterations,
        use_demons=use_demons,
    )

    # Save warped mask as clean uint8 NIfTI
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
        "final_metric": result.final_metric,
        "iterations": result.iterations,
        "used_demons": result.used_demons,
        "displacement_file": str(out_displacement_file) if out_displacement_file else None,
    }
