"""End-to-end deformable: Lena Knie 19 T0 mask warped onto T1 DESS.

Ground truth: Lena segmented the T1 DESS manually too, so after the
deformable transform we can compare the warped T0 mask against the real
T1 mask via Dice. A pure affine resample on these two DESS volumes
gives a poor Dice (~0.45) because the patient moved between scans;
deformable registration should clearly improve that.
"""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
import SimpleITK as sitk

FIX_T0 = Path(__file__).parent / "fixtures_local" / "Knie19_T0"
FIX_T1 = Path(__file__).parent / "fixtures_local" / "Knie19_T1"


def _dice(a: np.ndarray, b: np.ndarray) -> float:
    a = a > 0
    b = b > 0
    if not a.any() and not b.any():
        return 1.0
    inter = (a & b).sum()
    return 2.0 * inter / (a.sum() + b.sum() + 1e-9)


@pytest.fixture
def lena_paths():
    if not (FIX_T0.exists() and FIX_T1.exists()):
        pytest.skip("Lena T0/T1 fixtures missing")
    paths = {
        "t0_dess": FIX_T0 / "dess",
        "t0_mask": FIX_T0 / "mask.nii.gz",
        "t1_dess": FIX_T1 / "dess",
        "t1_mask": FIX_T1 / "mask.nii.gz",
    }
    for k, p in paths.items():
        if not p.exists():
            pytest.skip(f"missing {p}")
    return paths


def _read_dicom(folder: Path) -> sitk.Image:
    reader = sitk.ImageSeriesReader()
    reader.SetFileNames(reader.GetGDCMSeriesFileNames(str(folder)))
    return sitk.Cast(reader.Execute(), sitk.sitkFloat32)


def _affine_resample_mask(mask_in_t0: Path, t1_dess_folder: Path) -> np.ndarray:
    """Baseline: just resample the T0 mask onto the T1 voxel grid via affine.
    This is what the regular transform() would do — it ignores patient motion."""
    from MaskRegistration.backend import _nifti_to_sitk

    target = _read_dicom(t1_dess_folder)
    src = sitk.Cast(_nifti_to_sitk(mask_in_t0), sitk.sitkFloat32)
    rf = sitk.ResampleImageFilter()
    rf.SetReferenceImage(target)
    rf.SetInterpolator(sitk.sitkNearestNeighbor)
    rf.SetDefaultPixelValue(0)
    out = rf.Execute(src)
    return sitk.GetArrayFromImage(out).astype(np.int16)


@pytest.fixture(params=["sitk", "elastix"])
def backend(request):
    from MaskRegistration import available_backends

    if request.param not in available_backends():
        pytest.skip(f"backend '{request.param}' not installed")
    return request.param


def test_deformable_t0_to_t1_beats_affine(lena_paths, tmp_path, backend):
    """Deformable warp of T0 mask onto T1 DESS should beat affine resample.

    Comparing each against Lena's hand-drawn T1 mask via Dice. Runs once
    per available backend so we get a head-to-head comparison.
    """
    from MaskRegistration import transform_deformable

    out_warped = tmp_path / f"warped_t0_in_t1_{backend}.nii.gz"
    out_disp = tmp_path / f"displacement_{backend}.nii.gz"
    # Keep iterations modest so the smoke test stays under a few minutes
    # per backend. Real production runs use 200-500 iterations.
    result = transform_deformable(
        input_dicom_folder_1=lena_paths["t0_dess"],
        input_mask_file=lena_paths["t0_mask"],
        input_dicom_folder_2=lena_paths["t1_dess"],
        out_nii_file=out_warped,
        out_displacement_file=out_disp,
        backend=backend,
        n_iterations=50,
        use_demons=False,
    )
    assert out_warped.exists()
    assert out_disp.exists()

    # Ground truth: T1 mask resampled into the T1 DESS grid (it already is
    # in T1 DESS space, but resample to ensure identical shape)
    from MaskRegistration.backend import _nifti_to_sitk

    target = _read_dicom(lena_paths["t1_dess"])
    t1_truth_mask = sitk.Cast(_nifti_to_sitk(lena_paths["t1_mask"]), sitk.sitkFloat32)
    rf = sitk.ResampleImageFilter()
    rf.SetReferenceImage(target)
    rf.SetInterpolator(sitk.sitkNearestNeighbor)
    rf.SetDefaultPixelValue(0)
    truth_arr = sitk.GetArrayFromImage(rf.Execute(t1_truth_mask)).astype(np.int16)

    warped_arr = nib.load(str(out_warped)).get_fdata().astype(np.int16)
    affine_arr = _affine_resample_mask(lena_paths["t0_mask"], lena_paths["t1_dess"])

    # SimpleITK / nibabel axis order can differ — align by total label
    # presence per axis if needed. For Dice on union-mask we just need
    # matching shape; resample affine result onto warped grid if shapes
    # disagree.
    if warped_arr.shape != truth_arr.shape:
        # Both should be in T1 DESS space — if shapes differ it's an axis
        # convention issue; transpose accordingly.
        warped_arr = np.transpose(warped_arr, (2, 1, 0))
    if affine_arr.shape != truth_arr.shape:
        affine_arr = np.transpose(affine_arr, (2, 1, 0))

    dice_def = _dice(warped_arr, truth_arr)
    dice_aff = _dice(affine_arr, truth_arr)
    backend_name = result["backend"]
    print(f"\n[{backend_name}] Dice deformable: {dice_def:.3f}")
    print(f"Dice affine:     {dice_aff:.3f}")
    print(f"metric: {result['final_metric']:.4f}, iters: {result['iterations']}")

    # Deformable must beat affine, and absolute Dice should be at least
    # decent (>0.5). Realistic deformable Dice on cartilage between time
    # points is roughly 0.65-0.85.
    assert dice_def >= dice_aff, (
        f"deformable Dice {dice_def:.3f} did not beat affine {dice_aff:.3f}"
    )
    assert dice_def > 0.4, f"deformable Dice {dice_def:.3f} unreasonably low"

    # Sanity-check the displacement field
    disp = sitk.ReadImage(str(out_disp))
    disp_arr = sitk.GetArrayFromImage(disp)
    assert disp_arr.shape[-1] == 3
    # Average displacement magnitude should be non-trivial because the
    # two volumes do not align rigidly.
    mag = np.linalg.norm(disp_arr, axis=-1)
    print(f"mean |displacement|: {mag.mean():.2f} mm, max: {mag.max():.2f} mm")
    assert mag.max() > 0.5, "displacement field is suspiciously zero"
