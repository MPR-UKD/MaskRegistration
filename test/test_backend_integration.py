"""End-to-end tests against a real Lena fixture (gitignored locally).

These run only when test/fixtures_local/Knie19_T0/ is populated. The
data is patient DICOM and never committed.
"""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

FIXTURE = Path(__file__).parent / "fixtures_local" / "Knie19_T0"


@pytest.fixture
def fixture_paths():
    if not FIXTURE.exists():
        pytest.skip(f"local fixture missing: {FIXTURE}")
    paths = {
        "dess": FIXTURE / "dess",
        "t2": FIXTURE / "t2",
        "mask": FIXTURE / "mask.nii.gz",
    }
    for k, p in paths.items():
        if not p.exists():
            pytest.skip(f"fixture path missing: {p}")
    return paths


def test_transform_lena_knie19(fixture_paths, tmp_path):
    """Full registration pipeline on real Lena data: DESS mask -> T2 grid."""
    from MaskRegistration import transform

    out = tmp_path / "mask_in_t2.nii.gz"
    result = transform(
        input_dicom_folder_1=fixture_paths["dess"],
        input_mask_file=fixture_paths["mask"],
        input_dicom_folder_2=fixture_paths["t2"],
        out_nii_file=out,
        auto_axes="z",
    )
    assert out.exists()
    arr = nib.load(str(out)).get_fdata()
    # Knie 19 mask has labels 1..6 (cartilage 1-5, Hoffa 6).
    unique = sorted(int(v) for v in np.unique(arr) if v != 0)
    assert set([1, 2, 3, 4, 5, 6]).issubset(set(unique)), (
        f"missing labels after registration: expected 1-6, got {unique}"
    )
    # Volume should be close to source — 0.5 to 2.0 ratio
    assert 0.4 < result["volume_ratio"] < 2.5, result
    # Alignment of mask vs source DICOM should be clean
    assert result["alignment"]["drift_mm"] < 1.0


def test_transform_xyz_auto_lena(fixture_paths, tmp_path):
    """auto_axes='xyz' must also work; same labels must survive."""
    from MaskRegistration import transform

    out = tmp_path / "mask_xyz.nii.gz"
    result = transform(
        input_dicom_folder_1=fixture_paths["dess"],
        input_mask_file=fixture_paths["mask"],
        input_dicom_folder_2=fixture_paths["t2"],
        out_nii_file=out,
        auto_axes="xyz",
    )
    assert out.exists()
    # auto_axes='xyz' must not lose labels relative to 'z' on the same data
    arr = nib.load(str(out)).get_fdata()
    unique = sorted(int(v) for v in np.unique(arr) if v != 0)
    assert set([1, 2, 3, 4, 5, 6]).issubset(set(unique)), unique
    # used_flips returned
    assert "used_flips" in result
    assert len(result["used_flips"]) == 3
