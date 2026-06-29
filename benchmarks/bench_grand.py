"""Grand bench: try every reasonable combination, pick the best.

Combines:
  - backends (elastix default, elastix knee)
  - metrics (MI, NCC)
  - preprocessing (none, N4, N4+hist, full preprocess)
  - mask awareness (none, fixed_mask)
  - iteration count (500, 1500)
  - mask-to-mask refinement on top
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
    a, b = a > 0, b > 0
    return 2 * (a & b).sum() / (a.sum() + b.sum() + 1e-9)


def _resample(mask, ref, nn=True):
    rf = sitk.ResampleImageFilter()
    rf.SetReferenceImage(ref)
    rf.SetInterpolator(sitk.sitkNearestNeighbor if nn else sitk.sitkLinear)
    rf.SetDefaultPixelValue(0)
    return rf.Execute(mask)


def _dilated_mask(mask, ref, dilate_mm=15.0):
    if mask.GetSize() != ref.GetSize():
        mask = _resample(mask, ref)
    binary = sitk.BinaryThreshold(
        sitk.Cast(mask, sitk.sitkFloat32),
        lowerThreshold=0.5,
        insideValue=1,
        outsideValue=0,
    )
    sp = ref.GetSpacing()
    radius = [max(1, int(round(dilate_mm / s))) for s in sp]
    return sitk.Cast(sitk.BinaryDilate(binary, radius), sitk.sitkUInt8)


def main():
    print("loading data...")
    source = _read_dicom_series(T0 / "dess")
    target = _read_dicom_series(T1 / "dess")
    src_mask = _resample(sitk.Cast(_nifti_to_sitk(T0 / "mask.nii.gz"), sitk.sitkFloat32), source)
    tgt_mask_in_t1 = _resample(
        sitk.Cast(_nifti_to_sitk(T1 / "mask.nii.gz"), sitk.sitkFloat32), target
    )
    truth = sitk.GetArrayFromImage(tgt_mask_in_t1).astype(np.int16)
    print(f"truth voxels: {(truth > 0).sum()}\n")

    # Precompute preprocessing variants
    print("[N4 bias correction...]")
    src_n4 = n4_bias_correct(source)
    tgt_n4 = n4_bias_correct(target)
    print("[histogram match...]")
    src_hm = histogram_match(src_n4, tgt_n4)

    # Dilated mask of T1 (in T1 grid) for fixed_mask option
    fixed_mask_15 = _dilated_mask(tgt_mask_in_t1, target, dilate_mm=15.0)

    rows = []

    def run(label, fixed, moving, src_mask_arg, n_iter, metric, preset, fixed_mask=None):
        t = time.perf_counter()
        try:
            eng = ElastixBackend(preset=preset, metric=metric)
            res = eng.register(
                fixed=fixed,
                moving=moving,
                source_mask=src_mask_arg,
                n_iterations=n_iter,
                fixed_mask=fixed_mask,
            )
            dt = time.perf_counter() - t
            arr = sitk.GetArrayFromImage(res.warped_mask).astype(np.int16)
            if arr.shape != truth.shape:
                arr = sitk.GetArrayFromImage(
                    _resample(
                        sitk.Cast(res.warped_mask, sitk.sitkFloat32),
                        tgt_mask_in_t1,
                    )
                ).astype(np.int16)
            d = _dice(arr, truth)
            rows.append((label, n_iter, dt, d))
            print(f"  {label:<55} {n_iter:<5} {dt:<7.1f} Dice={d:.3f}")
            return res, d
        except Exception as e:
            print(f"  {label:<55} FAILED: {e!r}")
            rows.append((label, n_iter, 0, 0))
            return None, 0

    print("\n=== Image-based configs ===")
    configs = [
        ("baseline elastix MI", target, source, None, 500, "mi", "default", None),
        ("NCC", target, source, None, 500, "ncc", "default", None),
        ("N4 + MI", tgt_n4, src_n4, None, 500, "mi", "default", None),
        ("N4 + NCC", tgt_n4, src_n4, None, 500, "ncc", "default", None),
        ("N4 + hist + NCC", tgt_n4, src_hm, None, 500, "ncc", "default", None),
        ("N4 + hist + NCC 1500iter", tgt_n4, src_hm, None, 1500, "ncc", "default", None),
        ("N4 + NCC + fixed_mask", tgt_n4, src_n4, None, 500, "ncc", "default", fixed_mask_15),
        (
            "N4 + hist + NCC + fixed_mask",
            tgt_n4,
            src_hm,
            None,
            500,
            "ncc",
            "default",
            fixed_mask_15,
        ),
        (
            "N4 + hist + NCC + fixed_mask 1500",
            tgt_n4,
            src_hm,
            None,
            1500,
            "ncc",
            "default",
            fixed_mask_15,
        ),
    ]
    for cfg in configs:
        # cfg is a tuple (label, fixed, moving, src_mask_arg, n_iter, metric, preset, fixed_mask?)
        if len(cfg) == 7:
            run(*cfg[:3], src_mask, *cfg[3:])
        elif len(cfg) == 8:
            label, fixed_, moving_, _, n_iter, metric, preset, fmask = cfg
            run(label, fixed_, moving_, src_mask, n_iter, metric, preset, fixed_mask=fmask)

    print("\n=== Mask-to-mask refinement on best image-based ===")
    # Pick the best image-based result and add mask-to-mask refinement
    best = max(rows, key=lambda r: r[3])
    print(f"best so far: {best[0]} (Dice {best[3]:.3f})")

    # Mask-to-mask binary stage on top: take the warped mask and refine against
    # the T1 binary mask.
    # We re-run the best config but get the warped, then run mask-to-mask
    # on (warped_mask_binary) -> (t1_mask_binary) and chain.
    # Simpler: directly do mask-to-mask binary as standalone (we know this gives 0.708)
    print("[adding mask-to-mask binary on top of best image-based result...]")

    # Run best image-based once more to get warped mask
    best_label = best[0]
    print(f"  re-running best ({best_label}) to capture warped mask...")
    best_cfg = [c for c in configs if c[0] == best_label][0]
    if len(best_cfg) == 7:
        res_best, _ = run(*best_cfg[:3], src_mask, *best_cfg[3:])
    else:
        label, fixed_, moving_, _, n_iter, metric, preset, fmask = best_cfg
        res_best, _ = run(
            label + " (rerun)", fixed_, moving_, src_mask, n_iter, metric, preset, fixed_mask=fmask
        )

    if res_best is not None:
        warped = sitk.Cast(res_best.warped_mask, sitk.sitkFloat32)
        warped_bin = sitk.Cast(warped > 0, sitk.sitkFloat32)
        tgt_bin = sitk.Cast(tgt_mask_in_t1 > 0, sitk.sitkFloat32)
        # Resample warped to truth grid first
        if warped_bin.GetSize() != target.GetSize():
            warped_bin = _resample(warped_bin, target, nn=False)
        t = time.perf_counter()
        eng = ElastixBackend(preset="default", metric="ncc")
        res2 = eng.register(
            fixed=tgt_bin,
            moving=warped_bin,
            source_mask=sitk.Cast(warped, sitk.sitkUInt8),
            n_iterations=500,
            initial_alignment="rigid+affine",
        )
        dt = time.perf_counter() - t
        arr2 = sitk.GetArrayFromImage(res2.warped_mask).astype(np.int16)
        if arr2.shape != truth.shape:
            arr2 = sitk.GetArrayFromImage(
                _resample(sitk.Cast(res2.warped_mask, sitk.sitkFloat32), tgt_mask_in_t1)
            ).astype(np.int16)
        d2 = _dice(arr2, truth)
        rows.append((f"{best_label} + mask-to-mask refine", 500, dt, d2))
        print(f"  cascade Dice: {d2:.3f}")

    print("\n=== Mask-to-mask only (theoretical ceiling reminder) ===")
    src_bin = sitk.Cast(_resample(src_mask, tgt_mask_in_t1) > 0, sitk.sitkFloat32)
    tgt_bin = sitk.Cast(tgt_mask_in_t1 > 0, sitk.sitkFloat32)
    src_label = sitk.Cast(_resample(src_mask, tgt_mask_in_t1), sitk.sitkFloat32)
    t = time.perf_counter()
    eng = ElastixBackend(preset="default", metric="ncc")
    res = eng.register(
        fixed=tgt_bin,
        moving=src_bin,
        source_mask=sitk.Cast(src_label, sitk.sitkUInt8),
        n_iterations=500,
    )
    dt = time.perf_counter() - t
    arr = sitk.GetArrayFromImage(res.warped_mask).astype(np.int16)
    if arr.shape != truth.shape:
        arr = sitk.GetArrayFromImage(
            _resample(sitk.Cast(res.warped_mask, sitk.sitkFloat32), tgt_mask_in_t1)
        ).astype(np.int16)
    d = _dice(arr, truth)
    rows.append(("PURE mask-to-mask binary (cheat, needs target mask)", 500, dt, d))
    print(f"  pure mask-to-mask: Dice {d:.3f}")

    print("\n\n=== RANKED RESULTS ===")
    rows.sort(key=lambda r: -r[3])
    print(f"{'config':<60} {'iter':<5} {'time':<7} {'Dice':<7}")
    print("-" * 85)
    for r in rows:
        print(f"{r[0]:<60} {r[1]:<5} {r[2]:<7.1f} {r[3]:<7.3f}")


if __name__ == "__main__":
    main()
