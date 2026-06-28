"""Deformable registration: synthetic deformation recovery + Lena end-to-end."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from MaskRegistration import (
    DeformableResult,
    deformable_register,
    transform_deformable,
)

FIXTURE = Path(__file__).parent / "fixtures_local" / "Knie19_T0"


def _box_image(shape=(32, 32, 16), box=(8, 24, 8, 24, 4, 12)) -> sitk.Image:
    arr = np.zeros(shape, dtype=np.float32)
    arr[box[0] : box[1], box[2] : box[3], box[4] : box[5]] = 1.0
    img = sitk.GetImageFromArray(arr)
    img.SetSpacing((1.0, 1.0, 1.0))
    return img


def _shift_image(img: sitk.Image, shift=(2, 0, 0)) -> sitk.Image:
    arr = sitk.GetArrayFromImage(img)
    shifted = np.roll(arr, shift=shift, axis=(0, 1, 2))
    out = sitk.GetImageFromArray(shifted.astype(np.float32))
    out.CopyInformation(img)
    return out


def test_deformable_recovers_rigid_shift():
    """The simplest non-trivial case: image shifted by a few voxels."""
    fixed = _box_image()
    moving = _shift_image(fixed, shift=(3, 0, 0))
    # mask = box in moving space
    mask = sitk.Cast(moving > 0.5, sitk.sitkUInt8)

    result = deformable_register(
        source_image=moving,
        target_image=fixed,
        source_mask=mask,
        n_iterations=100,
        use_demons=True,
    )
    assert isinstance(result, DeformableResult)
    warped = sitk.GetArrayFromImage(result.warped_mask)
    fixed_box = sitk.GetArrayFromImage(fixed) > 0.5

    # Dice between warped mask and fixed box should be high.
    inter = ((warped > 0) & fixed_box).sum()
    union = (warped > 0).sum() + fixed_box.sum()
    dice = 2 * inter / union if union > 0 else 0
    assert dice > 0.8, f"dice too low after deformable: {dice:.2f}"


def test_displacement_field_shape():
    fixed = _box_image()
    moving = _shift_image(fixed, shift=(2, 0, 0))
    result = deformable_register(
        source_image=moving,
        target_image=fixed,
        n_iterations=50,
        use_demons=False,
    )
    df = sitk.GetArrayFromImage(result.displacement_field)
    # Displacement field has 3 components per voxel; numpy shape is the
    # reverse of the sitk image size plus a trailing 3.
    assert df.ndim == 4
    assert df.shape[-1] == 3
    assert df.shape[:3][::-1] == tuple(fixed.GetSize())


@pytest.mark.skipif(not FIXTURE.exists(), reason="Lena fixture missing")
def test_deformable_lena_end_to_end(tmp_path):
    """Real-world: DESS -> T2 deformable, mask should land on cartilage."""
    out_mask = tmp_path / "warped.nii.gz"
    out_disp = tmp_path / "disp.nii.gz"
    result = transform_deformable(
        input_dicom_folder_1=FIXTURE / "dess",
        input_mask_file=FIXTURE / "mask.nii.gz",
        input_dicom_folder_2=FIXTURE / "t2",
        out_nii_file=out_mask,
        out_displacement_file=out_disp,
        n_iterations=50,
        use_demons=False,
    )
    assert out_mask.exists()
    assert out_disp.exists()
    # Final metric should be a real number
    assert np.isfinite(result["final_metric"])
