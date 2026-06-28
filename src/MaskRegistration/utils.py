import logging
import os
from pathlib import Path

import natsort
import nibabel as nib
import numpy as np
import pydicom

log = logging.getLogger("MaskRegistration")


def is_resource_fork(file: Path) -> bool:
    """macOS APFS/HFS+ writes a paired `._<name>` metadata file when a folder
    is copied to a non-Mac filesystem. They have a `.dcm` extension but no
    DICOM payload; pydicom raises InvalidDicomError on them."""
    return Path(file).name.startswith("._")


def clean_dcm_list(dcm_files: list) -> list:
    """Drop macOS resource-fork shadow files (`._<name>.dcm`) before
    reading. Returns the filtered list."""
    out = [f for f in dcm_files if not is_resource_fork(f)]
    dropped = len(dcm_files) - len(out)
    if dropped > 0:
        log.warning(
            "skipping %d macOS resource-fork file(s) (._*) — these are not "
            "real DICOMs and confuse pydicom",
            dropped,
        )
    return out


def split_dcm(dcm_list: list):
    dcm_list = clean_dcm_list(dcm_list)
    locations = {}
    for f in dcm_list:
        try:
            d = pydicom.dcmread(f)
        except BaseException:
            continue
        if d["SliceLocation"].value in locations.keys():
            locations[d["SliceLocation"].value].append(f)
        else:
            locations[d["SliceLocation"].value] = [f]
    locations = check_locations(locations)
    split_dcmList = [locations[key] for key in locations.keys()]
    echo_list = [[] for _ in range(len(split_dcmList[0]))]
    keys = list(locations.keys())
    keys.sort()
    for key in keys:
        echos = locations[key]
        for idx in range(len(echo_list)):
            echo_list[idx].append(echos[idx])
    return echo_list


def check_locations(locations):
    keys = [key for key in locations.keys()]
    ls = [len(locations[key]) for key in locations.keys()]
    echos = np.median(ls)
    idx = []
    for i, l in enumerate(ls):
        if (l - echos) != 0.0:
            idx.append(i)
    if len(idx) == 2:
        locations[keys[idx[0]]] += locations[keys[idx[1]]]
        locations.pop(keys[idx[1]])
    return locations


def mask_to_dicom(dcm_folder: Path, nii_file: Path, out_folder: Path):
    """Write the mask slice-by-slice into copies of the source DICOMs.

    Warns when the slice counts disagree — that case is otherwise silent
    and produces a partially-filled output series.
    """
    mask = np.transpose(np.array(nib.load(nii_file).dataobj), (1, 0, 2))
    dicom_files = natsort.natsorted(clean_dcm_list([_ for _ in dcm_folder.glob("*.dcm")]))
    if mask.shape[2] != len(dicom_files):
        log.warning(
            "slice count mismatch: mask has %d slices, source DICOM has %d. "
            "Using min(%d) — extra slices on either side will be dropped.",
            mask.shape[2],
            len(dicom_files),
            min(mask.shape[2], len(dicom_files)),
        )
    mask = mask.astype("uint16")
    for i, dcm_file in enumerate(dicom_files):
        if i == mask.shape[2]:
            return None
        ds = pydicom.dcmread(dcm_file)
        ds.PixelData = mask[:, :, i].tobytes()
        ds.save_as(out_folder / os.path.basename(dcm_file))


def read_first_dicom_ipp(dcm_folder: Path) -> np.ndarray | None:
    """Return the ImagePositionPatient of the first readable DICOM in folder."""
    files = clean_dcm_list(natsort.natsorted([_ for _ in dcm_folder.glob("*.dcm")]))
    for f in files:
        try:
            ds = pydicom.dcmread(f, stop_before_pixels=True)
            ipp = getattr(ds, "ImagePositionPatient", None)
            if ipp is not None:
                return np.array(list(ipp), dtype=float)
        except BaseException:
            continue
    return None


def check_alignment(
    mask_file: Path,
    dcm_folder: Path,
    drift_warn_mm: float = 5.0,
    drift_fail_mm: float = 20.0,
) -> dict:
    """Compare the mask's NIfTI affine origin with the DICOM's first-slice
    ImagePositionPatient. Logs a warning if they differ noticeably — that
    usually means the mask was drawn on a different scan.

    Returns a dict with keys: drift_mm, mask_origin, dicom_ipp, ok.
    """
    out = {
        "drift_mm": float("nan"),
        "mask_origin": None,
        "dicom_ipp": None,
        "ok": False,
    }
    try:
        img = nib.load(str(mask_file))
        mask_origin = img.affine[:3, 3]
    except BaseException as e:
        log.warning("could not read mask affine from %s: %s", mask_file, e)
        return out
    ipp = read_first_dicom_ipp(Path(dcm_folder))
    if ipp is None:
        log.warning("could not read DICOM IPP from %s", dcm_folder)
        out["mask_origin"] = tuple(np.round(mask_origin, 2))
        return out

    drift = float(np.linalg.norm(np.abs(mask_origin) - np.abs(ipp)))
    out["drift_mm"] = drift
    out["mask_origin"] = tuple(np.round(mask_origin, 2))
    out["dicom_ipp"] = tuple(np.round(ipp, 2))
    out["ok"] = drift < drift_warn_mm

    if drift > drift_fail_mm:
        log.warning(
            "[alignment FAIL] mask %s and DICOM %s differ by %.1f mm "
            "(mask origin %s vs DICOM IPP %s). The mask was almost certainly "
            "drawn on a different scan. Re-segment or supply the matching DICOM.",
            mask_file.name,
            dcm_folder.name,
            drift,
            out["mask_origin"],
            out["dicom_ipp"],
        )
    elif drift > drift_warn_mm:
        log.warning(
            "[alignment warn] mask %s and DICOM %s differ by %.1f mm — registration may struggle.",
            mask_file.name,
            dcm_folder.name,
            drift,
        )
    else:
        log.info("alignment OK for %s (drift %.2f mm)", mask_file.name, drift)
    return out


def check_transform_mask(org_mask: np.ndarray, transform_mask: np.ndarray):
    """
    Check that all regions are present after interpolation / registration
    """
    unique_org_mask = np.unique(org_mask)
    unique_transform_mask = np.unique(transform_mask)
    b = 2
