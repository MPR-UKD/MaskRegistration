#!/usr/bin/python

import argparse

from src.MaskRegistration.backend import transform

if __name__ == "__main__":
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

    args = parser.parse_args()
    transform(
        input_dicom_folder_1=args.input_dcm1,
        input_mask_file=args.input_mask,
        input_dicom_folder_2=args.input_dcm2,
        out_nii_file=args.output_mask,
    )
