"""Image preprocessing for better registration.

Standard MRI registration pipelines clean the images before running the
algorithm. Each step removes a confounder that an intensity-based metric
would otherwise chase instead of anatomy:

  - n4_bias_correct        removes RF-coil intensity inhomogeneity
  - histogram_match        aligns source histogram onto target
  - crop_to_mask_bbox      cuts away background (muscle, air, skin) so
                           the metric concentrates on the region of interest
  - smooth                 Gaussian blur, helps coarse-scale convergence

These can be composed: `prepare_for_registration(...)` applies a sensible
default sequence.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import SimpleITK as sitk

log = logging.getLogger("MaskRegistration.preprocess")


def n4_bias_correct(
    img: sitk.Image,
    shrink_factor: int = 4,
    iterations: tuple[int, ...] = (50, 50, 30, 20),
    mask: Optional[sitk.Image] = None,
) -> sitk.Image:
    """N4 bias-field correction. Removes slow intensity gradients caused
    by the RF coil. Shrinks the input for speed, fits the bias field, then
    applies the field at full resolution."""
    img = sitk.Cast(img, sitk.sitkFloat32)
    if mask is None:
        mask = sitk.OtsuThreshold(img, 0, 1, 200)
    else:
        mask = sitk.Cast(mask > 0, sitk.sitkUInt8)
    input_shrunk = sitk.Shrink(img, [shrink_factor] * img.GetDimension())
    mask_shrunk = sitk.Shrink(mask, [shrink_factor] * img.GetDimension())

    corrector = sitk.N4BiasFieldCorrectionImageFilter()
    corrector.SetMaximumNumberOfIterations(list(iterations))
    corrector.Execute(input_shrunk, mask_shrunk)
    log_bias_field = corrector.GetLogBiasFieldAsImage(img)
    corrected = img / sitk.Exp(log_bias_field)
    log.info("n4 bias correction done")
    return sitk.Cast(corrected, sitk.sitkFloat32)


def histogram_match(
    source: sitk.Image,
    target: sitk.Image,
    n_histogram_levels: int = 1024,
    n_match_points: int = 7,
) -> sitk.Image:
    """Map source histogram onto target's. Useful when intensities differ
    in absolute scale (different protocols, vendors)."""
    f = sitk.HistogramMatchingImageFilter()
    f.SetNumberOfHistogramLevels(n_histogram_levels)
    f.SetNumberOfMatchPoints(n_match_points)
    f.ThresholdAtMeanIntensityOn()
    return sitk.Cast(f.Execute(source, target), sitk.sitkFloat32)


def crop_to_mask_bbox(
    img: sitk.Image,
    mask: sitk.Image,
    margin_mm: float = 10.0,
) -> sitk.Image:
    """Crop image to the bounding box of a mask plus a margin in mm.
    Drops irrelevant background voxels."""
    if mask.GetSize() != img.GetSize():
        rf = sitk.ResampleImageFilter()
        rf.SetReferenceImage(img)
        rf.SetInterpolator(sitk.sitkNearestNeighbor)
        rf.SetDefaultPixelValue(0)
        mask = rf.Execute(mask)
    arr = sitk.GetArrayFromImage(mask) > 0
    if not arr.any():
        return img
    nz = np.nonzero(arr)
    # nibabel/sitk order: arr is (Z, Y, X)
    z0, z1 = int(nz[0].min()), int(nz[0].max())
    y0, y1 = int(nz[1].min()), int(nz[1].max())
    x0, x1 = int(nz[2].min()), int(nz[2].max())
    sp = img.GetSpacing()  # (x, y, z)
    mx = int(round(margin_mm / sp[0]))
    my = int(round(margin_mm / sp[1]))
    mz = int(round(margin_mm / sp[2]))
    x0 = max(0, x0 - mx)
    y0 = max(0, y0 - my)
    z0 = max(0, z0 - mz)
    x1 = min(img.GetSize()[0] - 1, x1 + mx)
    y1 = min(img.GetSize()[1] - 1, y1 + my)
    z1 = min(img.GetSize()[2] - 1, z1 + mz)
    return sitk.RegionOfInterest(
        img,
        size=[x1 - x0 + 1, y1 - y0 + 1, z1 - z0 + 1],
        index=[x0, y0, z0],
    )


def smooth(img: sitk.Image, sigma_mm: float = 1.0) -> sitk.Image:
    """Gaussian smoothing with sigma in physical mm."""
    return sitk.SmoothingRecursiveGaussian(sitk.Cast(img, sitk.sitkFloat32), sigma=sigma_mm)


def prepare_for_registration(
    source: sitk.Image,
    target: sitk.Image,
    *,
    do_n4: bool = True,
    do_histogram_match: bool = True,
    smooth_sigma_mm: float = 0.0,
) -> tuple[sitk.Image, sitk.Image]:
    """Apply a sensible default preprocessing sequence to both images.

    Returns the preprocessed (source, target). The geometry is preserved
    so any transform fitted in the cleaned space applies one-to-one to
    the original images.
    """
    src = sitk.Cast(source, sitk.sitkFloat32)
    tgt = sitk.Cast(target, sitk.sitkFloat32)

    if do_n4:
        src = n4_bias_correct(src)
        tgt = n4_bias_correct(tgt)
    if do_histogram_match:
        src = histogram_match(src, tgt)
    if smooth_sigma_mm > 0:
        src = smooth(src, smooth_sigma_mm)
        tgt = smooth(tgt, smooth_sigma_mm)
    return src, tgt
