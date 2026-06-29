"""How much does preprocessing + metric tuning help?

Pipeline knobs to try on top of the elastix default 500-iter baseline:
  - n4 bias correction
  - histogram matching
  - crop to knee bounding box (mask + margin)
  - smoothing
  - NCC metric (instead of MI) for same-modality DESS-DESS
"""

from __future__ import annotations

import time
from pathlib import Path

import nibabel as nib
import numpy as np
import SimpleITK as sitk

from MaskRegistration import (
    crop_to_mask_bbox,
    histogram_match,
    n4_bias_correct,
)
from MaskRegistration.backend import _nifti_to_sitk
from MaskRegistration.backends import ElastixBackend
from MaskRegistration.deformable import _read_dicom_series

FIX = Path(__file__).parent / "fixtures_local"
T0 = FIX / "Knie19_T0"
T1 = FIX / "Knie19_T1"


def _dice(a, b):
    a = a > 0
    b = b > 0
    return 2 * (a & b).sum() / (a.sum() + b.sum() + 1e-9)


def _resample(mask, ref):
    rf = sitk.ResampleImageFilter()
    rf.SetReferenceImage(ref)
    rf.SetInterpolator(sitk.sitkNearestNeighbor)
    rf.SetDefaultPixelValue(0)
    return rf.Execute(mask)


def main():
    source = _read_dicom_series(T0 / "dess")
    target = _read_dicom_series(T1 / "dess")
    src_mask = sitk.Cast(_nifti_to_sitk(T0 / "mask.nii.gz"), sitk.sitkFloat32)
    tgt_mask = sitk.Cast(_nifti_to_sitk(T1 / "mask.nii.gz"), sitk.sitkFloat32)
    src_mask = _resample(src_mask, source)
    tgt_mask_in_t1 = _resample(tgt_mask, target)
    truth = sitk.GetArrayFromImage(tgt_mask_in_t1).astype(np.int16)
    print(f"truth voxels: {(truth > 0).sum()}\n")
    print(f"{'config':<55} {'iter':<5} {'time':<7} {'Dice':<7}")
    print("-" * 80)

    def run(label, fixed, moving, src_mask_now, n_iter=500, metric="mi", preset="default"):
        t = time.perf_counter()
        try:
            eng = ElastixBackend(preset=preset, metric=metric)
            res = eng.register(
                fixed=fixed,
                moving=moving,
                source_mask=src_mask_now,
                n_iterations=n_iter,
            )
            dt = time.perf_counter() - t
            arr = sitk.GetArrayFromImage(res.warped_mask).astype(np.int16)
            # If we cropped the fixed image, the warped_mask is in the
            # cropped grid — resample to truth grid for fair Dice.
            if arr.shape != truth.shape:
                # Convert warped_mask back to truth's grid for fair comparison
                rf = sitk.ResampleImageFilter()
                rf.SetReferenceImage(tgt_mask_in_t1)
                rf.SetInterpolator(sitk.sitkNearestNeighbor)
                rf.SetDefaultPixelValue(0)
                arr = sitk.GetArrayFromImage(
                    rf.Execute(sitk.Cast(res.warped_mask, sitk.sitkFloat32))
                ).astype(np.int16)
            d = _dice(arr, truth)
            print(f"{label:<55} {n_iter:<5} {dt:<7.1f} {d:<7.3f}")
            return d
        except Exception as e:
            print(f"{label:<55} FAILED: {e!r}")
            return 0.0

    # Baseline
    run("baseline: default MI", target, source, src_mask)

    # NCC metric for same-modality
    run("NCC metric (same-modality)", target, source, src_mask, metric="ncc")

    # N4 bias correction
    print("[applying N4 bias correction to both volumes...]")
    target_n4 = n4_bias_correct(target)
    source_n4 = n4_bias_correct(source)
    run("N4 bias + MI", target_n4, source_n4, src_mask)
    run("N4 bias + NCC", target_n4, source_n4, src_mask, metric="ncc")

    # Histogram match (source onto target intensity range)
    print("[applying histogram match...]")
    source_hm = histogram_match(source_n4, target_n4)
    run("N4 + histogram + MI", target_n4, source_hm, src_mask)
    run("N4 + histogram + NCC", target_n4, source_hm, src_mask, metric="ncc")

    # ROI crop: crop both volumes to dilated mask bounding box
    print("[cropping to mask bbox + 15mm margin...]")
    # For source we crop to T0-mask bbox in source grid
    src_crop_mask = sitk.Cast(src_mask > 0, sitk.sitkUInt8)
    tgt_crop_mask = sitk.Cast(tgt_mask_in_t1 > 0, sitk.sitkUInt8)
    src_cropped = crop_to_mask_bbox(source_hm, src_crop_mask, margin_mm=15.0)
    tgt_cropped = crop_to_mask_bbox(target_n4, tgt_crop_mask, margin_mm=15.0)
    src_mask_cropped = crop_to_mask_bbox(src_crop_mask, src_crop_mask, margin_mm=15.0)
    print(f"  cropped source size: {src_cropped.GetSize()}, target: {tgt_cropped.GetSize()}")
    run(
        "N4 + histogram + crop + NCC (full preprocess)",
        tgt_cropped,
        src_cropped,
        src_mask_cropped,
        metric="ncc",
    )


if __name__ == "__main__":
    main()
