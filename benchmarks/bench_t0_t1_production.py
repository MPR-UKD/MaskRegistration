"""Production benchmark: deformable T0 mask -> T1 DESS with real iter counts.

Not a pytest — run directly with `uv run python test/bench_t0_t1_production.py`.
Reports Dice + wall time per backend and per iteration setting.
"""

from __future__ import annotations

import time
from pathlib import Path

import nibabel as nib
import numpy as np
import SimpleITK as sitk

from MaskRegistration import transform_deformable, available_backends
from MaskRegistration.backend import _nifti_to_sitk

FIX = Path(__file__).parent / "fixtures_local"
T0 = FIX / "Knie19_T0"
T1 = FIX / "Knie19_T1"


def _dice(a, b):
    a = a > 0
    b = b > 0
    inter = (a & b).sum()
    return 2 * inter / (a.sum() + b.sum() + 1e-9)


def _truth_array(t1_dess: Path, t1_mask: Path):
    reader = sitk.ImageSeriesReader()
    reader.SetFileNames(reader.GetGDCMSeriesFileNames(str(t1_dess)))
    target = sitk.Cast(reader.Execute(), sitk.sitkFloat32)
    m = sitk.Cast(_nifti_to_sitk(t1_mask), sitk.sitkFloat32)
    rf = sitk.ResampleImageFilter()
    rf.SetReferenceImage(target)
    rf.SetInterpolator(sitk.sitkNearestNeighbor)
    rf.SetDefaultPixelValue(0)
    return sitk.GetArrayFromImage(rf.Execute(m)).astype(np.int16)


def main():
    if not T0.exists() or not T1.exists():
        print("Lena fixtures missing, skipping.")
        return
    truth = _truth_array(T1 / "dess", T1 / "mask.nii.gz")
    print(f"backends available: {available_backends()}")
    print(f"truth shape: {truth.shape}, positive voxels: {(truth > 0).sum()}")
    print()
    print(f"{'backend':<10} {'iter':<6} {'demons':<8} {'time_s':<8} {'Dice':<8} {'max_disp':<10}")
    print("-" * 60)

    rows = []
    for backend in available_backends():
        for n_iter, demons in [(50, False), (200, False), (200, True)]:
            if backend == "elastix" and demons:
                # elastix doesn't use the Demons option
                continue
            tmp = Path("/tmp") / f"bench_{backend}_{n_iter}_{int(demons)}.nii.gz"
            t = time.perf_counter()
            try:
                res = transform_deformable(
                    input_dicom_folder_1=T0 / "dess",
                    input_mask_file=T0 / "mask.nii.gz",
                    input_dicom_folder_2=T1 / "dess",
                    out_nii_file=tmp,
                    backend=backend,
                    n_iterations=n_iter,
                    use_demons=demons,
                )
                dt = time.perf_counter() - t
                arr = nib.load(str(tmp)).get_fdata().astype(np.int16)
                if arr.shape != truth.shape:
                    arr = np.transpose(arr, (2, 1, 0))
                d = _dice(arr, truth)
                # Field displacement we can read from a separate run if needed;
                # skip the field for benchmark brevity.
                rows.append((backend, n_iter, demons, dt, d))
                print(f"{backend:<10} {n_iter:<6} {str(demons):<8} {dt:<8.1f} {d:<8.3f}")
            except Exception as e:
                print(f"{backend:<10} {n_iter:<6} {str(demons):<8} FAILED: {e}")

    print()
    print("affine baseline:", end=" ")
    # Affine baseline once
    reader = sitk.ImageSeriesReader()
    reader.SetFileNames(reader.GetGDCMSeriesFileNames(str(T1 / "dess")))
    target = sitk.Cast(reader.Execute(), sitk.sitkFloat32)
    src = sitk.Cast(_nifti_to_sitk(T0 / "mask.nii.gz"), sitk.sitkFloat32)
    rf = sitk.ResampleImageFilter()
    rf.SetReferenceImage(target)
    rf.SetInterpolator(sitk.sitkNearestNeighbor)
    rf.SetDefaultPixelValue(0)
    aff_arr = sitk.GetArrayFromImage(rf.Execute(src)).astype(np.int16)
    if aff_arr.shape != truth.shape:
        aff_arr = np.transpose(aff_arr, (2, 1, 0))
    print(f"Dice {_dice(aff_arr, truth):.3f}")


if __name__ == "__main__":
    main()
