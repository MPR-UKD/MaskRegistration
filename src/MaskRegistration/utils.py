import os
from pathlib import Path

import natsort
import nibabel as nib
import numpy as np
import pydicom


def split_dcm(dcm_list: list):
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
    mask = np.transpose(np.array(nib.load(nii_file).dataobj), (1, 0, 2))
    dicom_files = natsort.natsorted([_ for _ in dcm_folder.glob("*.dcm")])
    mask = mask.astype("uint16")
    for i, dcm_file in enumerate(dicom_files):
        if i == mask.shape[2]:
            return None
        ds = pydicom.dcmread(dcm_file)
        ds.PixelData = mask[:, :, i].tobytes()
        ds.save_as(out_folder / os.path.basename(dcm_file))


def check_transform_mask(org_mask: np.ndarray, transform_mask: np.ndarray):
    """
    Check that all regions are present after interpolation / registration
    """
    unique_org_mask = np.unique(org_mask)
    unique_transform_mask = np.unique(transform_mask)
    b = 2
