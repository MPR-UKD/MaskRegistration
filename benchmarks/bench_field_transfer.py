"""Bench: estimate displacement field on low-res T2, apply to high-res DESS.

Compares against the direct deformable register on DESS. Should be
much faster while losing only marginal Dice.
"""

from __future__ import annotations

import time
from pathlib import Path

import nibabel as nib
import numpy as np
import SimpleITK as sitk

from MaskRegistration import (
    available_backends,
    estimate_field_lowres_apply_highres,
    transform_deformable,
)
from MaskRegistration.backend import _nifti_to_sitk

FIX = Path(__file__).parent / "fixtures_local"
T0 = FIX / "Knie19_T0"
T1 = FIX / "Knie19_T1"


def _dice(a, b):
    a = a > 0
    b = b > 0
    inter = (a & b).sum()
    return 2 * inter / (a.sum() + b.sum() + 1e-9)


def _truth_array(target_dess: Path, target_mask: Path):
    reader = sitk.ImageSeriesReader()
    reader.SetFileNames(reader.GetGDCMSeriesFileNames(str(target_dess)))
    target = sitk.Cast(reader.Execute(), sitk.sitkFloat32)
    m = sitk.Cast(_nifti_to_sitk(target_mask), sitk.sitkFloat32)
    rf = sitk.ResampleImageFilter()
    rf.SetReferenceImage(target)
    rf.SetInterpolator(sitk.sitkNearestNeighbor)
    rf.SetDefaultPixelValue(0)
    return sitk.GetArrayFromImage(rf.Execute(m)).astype(np.int16)


def main():
    if not (T0 / "t2").exists() or not (T1 / "t2").exists():
        print("T2 fixtures missing")
        return
    truth = _truth_array(T1 / "dess", T1 / "mask.nii.gz")
    print(f"T1 DESS truth shape: {truth.shape}, positive voxels: {(truth > 0).sum()}")
    print(f"backends: {available_backends()}")
    print()
    print(f"{'mode':<28} {'backend':<10} {'time_s':<8} {'Dice':<8}")
    print("-" * 60)

    rows = []

    # Direct deformable on DESS (reference / slow)
    for backend in available_backends():
        tmp = Path(f"/tmp/direct_dess_{backend}.nii.gz")
        t = time.perf_counter()
        try:
            transform_deformable(
                input_dicom_folder_1=T0 / "dess",
                input_mask_file=T0 / "mask.nii.gz",
                input_dicom_folder_2=T1 / "dess",
                out_nii_file=tmp,
                backend=backend,
                n_iterations=100,
                use_demons=False,
            )
            dt = time.perf_counter() - t
            arr = nib.load(str(tmp)).get_fdata().astype(np.int16)
            if arr.shape != truth.shape:
                arr = np.transpose(arr, (2, 1, 0))
            d = _dice(arr, truth)
            rows.append(("direct_dess", backend, dt, d))
            print(f"{'direct_dess':<28} {backend:<10} {dt:<8.1f} {d:<8.3f}")
        except Exception as e:
            print(f"{'direct_dess':<28} {backend:<10} FAILED: {e}")

    # Low-res T2 -> high-res DESS field transfer
    for backend in available_backends():
        tmp = Path(f"/tmp/lowres_t2_to_dess_{backend}.nii.gz")
        t = time.perf_counter()
        try:
            res = estimate_field_lowres_apply_highres(
                lowres_source_dicom=T0 / "t2",
                lowres_target_dicom=T1 / "t2",
                highres_source_dicom=T0 / "dess",
                highres_target_dicom=T1 / "dess",
                source_mask_file=T0 / "mask.nii.gz",
                out_warped_mask=tmp,
                backend=backend,
                n_iterations=100,
            )
            dt = time.perf_counter() - t
            arr = nib.load(str(tmp)).get_fdata().astype(np.int16)
            if arr.shape != truth.shape:
                arr = np.transpose(arr, (2, 1, 0))
            d = _dice(arr, truth)
            rows.append(("lowres_t2_to_dess", backend, dt, d))
            print(
                f"{'lowres_t2_to_dess':<28} {backend:<10} {dt:<8.1f} {d:<8.3f}"
                f"  speedup_estimate={res.speed_factor:.1f}x"
            )
        except Exception as e:
            print(f"{'lowres_t2_to_dess':<28} {backend:<10} FAILED: {e}")

    print()
    if rows:
        print("Summary (sorted by Dice):")
        rows.sort(key=lambda r: -r[3])
        for r in rows:
            print(f"  {r[0]:<22} {r[1]:<10} time={r[2]:6.1f}s dice={r[3]:.3f}")


if __name__ == "__main__":
    main()
