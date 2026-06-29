"""MaskRegistration — transfer segmentation masks between DICOM series."""

from MaskRegistration.backend import transform
from MaskRegistration.backends import available_backends
from MaskRegistration.field_transfer import (
    FieldTransferResult,
    estimate_field_lowres_apply_highres,
)
from MaskRegistration.preprocess import (
    crop_to_mask_bbox,
    histogram_match,
    n4_bias_correct,
    prepare_for_registration,
    smooth,
)
from MaskRegistration.deformable import (
    DeformableResult,
    deformable_register,
    transform_deformable,
)
from MaskRegistration.utils import (
    check_alignment,
    clean_dcm_list,
    is_resource_fork,
    read_first_dicom_ipp,
)

__all__ = [
    "crop_to_mask_bbox",
    "histogram_match",
    "n4_bias_correct",
    "prepare_for_registration",
    "smooth",
    "estimate_field_lowres_apply_highres",
    "FieldTransferResult",
    "available_backends",
    "DeformableResult",
    "check_alignment",
    "clean_dcm_list",
    "deformable_register",
    "is_resource_fork",
    "read_first_dicom_ipp",
    "transform",
    "transform_deformable",
]
