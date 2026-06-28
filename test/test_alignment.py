"""Pre-flight alignment + resource-fork tests."""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np
import pydicom
import pytest
from pydicom.dataset import FileDataset, FileMetaDataset

from MaskRegistration.utils import (
    check_alignment,
    clean_dcm_list,
    is_resource_fork,
    read_first_dicom_ipp,
)


def _write_nifti(path: Path, origin):
    affine = np.eye(4)
    affine[:3, 3] = origin
    nib.save(nib.Nifti1Image(np.ones((4, 4, 2), dtype=np.int16), affine), str(path))


def _write_fake_dcm(path: Path, ipp):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.4"
    meta.MediaStorageSOPInstanceUID = "1.2.3"
    meta.TransferSyntaxUID = "1.2.840.10008.1.2"
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.PatientName = "T"
    ds.PatientID = "T"
    ds.Modality = "MR"
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.4"
    ds.SOPInstanceUID = "1.2.3.4"
    ds.ImagePositionPatient = list(ipp)
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.PixelSpacing = [1.0, 1.0]
    ds.Rows = 4
    ds.Columns = 4
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = (np.zeros((4, 4), dtype=np.uint16)).tobytes()
    ds.save_as(str(path), write_like_original=False)


def test_is_resource_fork():
    assert is_resource_fork(Path("._foo.dcm"))
    assert not is_resource_fork(Path("foo.dcm"))


def test_clean_dcm_list_drops_resource_forks(caplog):
    files = [Path("a.dcm"), Path("._a.dcm"), Path("b.dcm"), Path("._b.dcm")]
    with caplog.at_level("WARNING"):
        out = clean_dcm_list(files)
    assert [f.name for f in out] == ["a.dcm", "b.dcm"]
    assert any("resource-fork" in rec.message for rec in caplog.records)


def test_read_first_dicom_ipp(tmp_path: Path):
    folder = tmp_path / "scan"
    folder.mkdir()
    _write_fake_dcm(folder / "slice1.dcm", (10, 20, 30))
    ipp = read_first_dicom_ipp(folder)
    assert ipp is not None
    assert np.allclose(ipp, [10, 20, 30])


def test_check_alignment_warns_on_drift(tmp_path: Path, caplog):
    mask = tmp_path / "mask.nii.gz"
    _write_nifti(mask, (0, 0, 0))
    folder = tmp_path / "scan"
    folder.mkdir()
    _write_fake_dcm(folder / "slice1.dcm", (50, 0, 0))

    with caplog.at_level("WARNING"):
        rep = check_alignment(mask, folder, drift_warn_mm=5, drift_fail_mm=20)
    assert rep["drift_mm"] > 30
    assert not rep["ok"]
    assert any("drawn on a different scan" in rec.message for rec in caplog.records)


def test_check_alignment_clean(tmp_path: Path, caplog):
    mask = tmp_path / "mask.nii.gz"
    _write_nifti(mask, (10, 20, 30))
    folder = tmp_path / "scan"
    folder.mkdir()
    _write_fake_dcm(folder / "slice1.dcm", (10, 20, 30))

    with caplog.at_level("INFO"):
        rep = check_alignment(mask, folder)
    assert rep["drift_mm"] < 0.1
    assert rep["ok"]
