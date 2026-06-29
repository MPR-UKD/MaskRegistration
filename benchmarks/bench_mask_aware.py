"""Mask-aware elastix: only register inside the knee region.

Dilate the source/target masks by a generous margin so elastix has
context but skips the irrelevant background (muscle, air, skin).
"""

from __future__ import annotations

import time
from pathlib import Path

import nibabel as nib
import numpy as np
import SimpleITK as sitk

from MaskRegistration.backend import _nifti_to_sitk
from MaskRegistration.deformable import deformable_register, _read_dicom_series

FIX = Path(__file__).parent / "fixtures_local"
T0 = FIX / "Knie19_T0"
T1 = FIX / "Knie19_T1"


def _dice(a, b):
    a = a > 0
    b = b > 0
    return 2 * (a & b).sum() / (a.sum() + b.sum() + 1e-9)


def _truth():
    t = _read_dicom_series(T1 / "dess")
    m = sitk.Cast(_nifti_to_sitk(T1 / "mask.nii.gz"), sitk.sitkFloat32)
    rf = sitk.ResampleImageFilter()
    rf.SetReferenceImage(t)
    rf.SetInterpolator(sitk.sitkNearestNeighbor)
    rf.SetDefaultPixelValue(0)
    return sitk.GetArrayFromImage(rf.Execute(m)).astype(np.int16)


def _dilated_mask(mask_path: Path, ref_image: sitk.Image, dilate_mm: float = 15.0):
    """Load a mask, resample to reference grid, binarise and dilate by N mm."""
    m = sitk.Cast(_nifti_to_sitk(mask_path), sitk.sitkFloat32)
    rf = sitk.ResampleImageFilter()
    rf.SetReferenceImage(ref_image)
    rf.SetInterpolator(sitk.sitkNearestNeighbor)
    rf.SetDefaultPixelValue(0)
    m = rf.Execute(m)
    binary = sitk.BinaryThreshold(m, lowerThreshold=0.5, insideValue=1, outsideValue=0)
    # Dilate by N mm in each direction (radius in voxels)
    sp = ref_image.GetSpacing()
    radius = [max(1, int(round(dilate_mm / s))) for s in sp]
    dilated = sitk.BinaryDilate(binary, radius)
    return sitk.Cast(dilated, sitk.sitkUInt8)


def main():
    truth = _truth()
    print(f"truth voxels: {(truth > 0).sum()}\n")
    print(f"{'mode':<32} {'iter':<6} {'time':<8} {'Dice':<8}")
    print("-" * 60)

    source = _read_dicom_series(T0 / "dess")
    target = _read_dicom_series(T1 / "dess")
    source_mask_img = sitk.Cast(_nifti_to_sitk(T0 / "mask.nii.gz"), sitk.sitkFloat32)

    # Bring source mask onto source grid
    rf = sitk.ResampleImageFilter()
    rf.SetReferenceImage(source)
    rf.SetInterpolator(sitk.sitkNearestNeighbor)
    rf.SetDefaultPixelValue(0)
    source_mask_img = rf.Execute(source_mask_img)

    def run(label, **kwargs):
        t = time.perf_counter()
        try:
            res = deformable_register(
                source_image=source,
                target_image=target,
                source_mask=source_mask_img,
                backend="elastix",
                n_iterations=kwargs.pop("n_iter", 500),
                use_demons=False,
                **kwargs,
            )
            dt = time.perf_counter() - t
            arr = sitk.GetArrayFromImage(res.warped_mask).astype(np.int16)
            if arr.shape != truth.shape:
                arr = np.transpose(arr, (2, 1, 0))
            d = _dice(arr, truth)
            print(f"{label:<32} {500:<6} {dt:<8.1f} {d:<8.3f}")
        except Exception as e:
            print(f"{label:<32} FAILED: {e!r}")

    # Baseline: no mask
    run("elastix no mask")

    # With fixed mask (dilated T1 mask)
    fixed_mask = _dilated_mask(T1 / "mask.nii.gz", target, dilate_mm=15.0)
    run("elastix fixed_mask 15mm dilation", fixed_mask=fixed_mask)

    # With moving mask
    moving_mask = _dilated_mask(T0 / "mask.nii.gz", source, dilate_mm=15.0)
    run("elastix moving_mask 15mm dilation", moving_mask=moving_mask)

    # Both masks
    run(
        "elastix both masks 15mm",
        fixed_mask=fixed_mask,
        moving_mask=moving_mask,
    )

    # Tighter dilation
    fm5 = _dilated_mask(T1 / "mask.nii.gz", target, dilate_mm=5.0)
    mm5 = _dilated_mask(T0 / "mask.nii.gz", source, dilate_mm=5.0)
    run("elastix both masks 5mm", fixed_mask=fm5, moving_mask=mm5)


if __name__ == "__main__":
    main()
