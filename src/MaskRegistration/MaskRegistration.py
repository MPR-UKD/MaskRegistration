#!/usr/bin/python

import argparse
from pathlib import Path

from MaskRegistration.backend import transform


def main():
    parser = argparse.ArgumentParser(description="Mask Registration")
    parser.add_argument(
        "-d1", "--input_dcm1", type=str, help="path to the first DICOM folder"
    )
    parser.add_argument("-m", "--input_mask", type=str, help="path to the mask file")
    parser.add_argument(
        "-d2", "--input_dcm2", type=str, help="path to the second DICOM folder"
    )
    parser.add_argument(
        "-o", "--output_mask", type=str, help="path to the output NIFTI file"
    )
    parser.add_argument(
        "--subpixel",
        type=int,
        default=1,
        help="upsample Z-axis by this factor, then downsample with OR logic (default: 1 = disabled)",
    )
    parser.add_argument(
        "--reverse",
        type=str,
        choices=["auto", "true", "false"],
        default="auto",
        help="read target DICOM in reverse Z order (auto = try both, pick better)",
    )

    args = parser.parse_args()
    reverse_map = {"auto": None, "true": True, "false": False}
    transform(
        input_dicom_folder_1=Path(args.input_dcm1),
        input_mask_file=Path(args.input_mask),
        input_dicom_folder_2=Path(args.input_dcm2),
        out_nii_file=Path(args.output_mask),
        subpixel_factor=args.subpixel,
        reverse=reverse_map[args.reverse],
    )


if __name__ == "__main__":
    main()
