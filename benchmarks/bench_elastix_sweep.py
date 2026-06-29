"""How does elastix Dice scale with iterations on real Lena T0->T1 DESS?

Sweep n_iter to see where Dice plateaus. ~300s budget means we can try
a couple of high-iter settings.
"""

from __future__ import annotations

import time
from pathlib import Path

import nibabel as nib
import numpy as np
import SimpleITK as sitk

from MaskRegistration import transform_deformable
from MaskRegistration.backend import _nifti_to_sitk

FIX = Path(__file__).parent / "fixtures_local"
T0 = FIX / "Knie19_T0"
T1 = FIX / "Knie19_T1"


def _dice(a, b):
    a = a > 0
    b = b > 0
    return 2 * (a & b).sum() / (a.sum() + b.sum() + 1e-9)


def _truth():
    reader = sitk.ImageSeriesReader()
    reader.SetFileNames(reader.GetGDCMSeriesFileNames(str(T1 / "dess")))
    target = sitk.Cast(reader.Execute(), sitk.sitkFloat32)
    m = sitk.Cast(_nifti_to_sitk(T1 / "mask.nii.gz"), sitk.sitkFloat32)
    rf = sitk.ResampleImageFilter()
    rf.SetReferenceImage(target)
    rf.SetInterpolator(sitk.sitkNearestNeighbor)
    rf.SetDefaultPixelValue(0)
    return sitk.GetArrayFromImage(rf.Execute(m)).astype(np.int16)


def main():
    truth = _truth()
    print(f"truth shape: {truth.shape}, positive voxels: {(truth > 0).sum()}")
    print()
    print(f"{'iter':<8} {'time_s':<10} {'Dice':<8}")
    print("-" * 30)
    for n_iter in [100, 500, 1000, 2000, 4000]:
        tmp = Path(f"/tmp/sweep_{n_iter}.nii.gz")
        t = time.perf_counter()
        try:
            transform_deformable(
                input_dicom_folder_1=T0 / "dess",
                input_mask_file=T0 / "mask.nii.gz",
                input_dicom_folder_2=T1 / "dess",
                out_nii_file=tmp,
                backend="elastix",
                n_iterations=n_iter,
                use_demons=False,
            )
            dt = time.perf_counter() - t
            arr = nib.load(str(tmp)).get_fdata().astype(np.int16)
            if arr.shape != truth.shape:
                arr = np.transpose(arr, (2, 1, 0))
            d = _dice(arr, truth)
            print(f"{n_iter:<8} {dt:<10.1f} {d:<8.3f}")
        except Exception as e:
            print(f"{n_iter:<8} FAILED: {e}")


if __name__ == "__main__":
    main()
