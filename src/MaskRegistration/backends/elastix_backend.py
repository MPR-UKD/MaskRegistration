"""elastix backend via itk-elastix (no external binary required).

Uses the validated default parameter presets from the elastix model zoo:
"rigid" + "affine" + "bspline". Generally more accurate out-of-the-box
than hand-tuned SimpleITK because the presets bake in decades of
empirical tuning for medical image registration.

Pip install:
    pip install itk-elastix
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import SimpleITK as sitk

from MaskRegistration.backends.base import BackendResult, RegistrationBackend

log = logging.getLogger("MaskRegistration.elastix")

try:
    import itk

    ELASTIX_AVAILABLE = hasattr(itk, "ElastixRegistrationMethod")
except ImportError:  # pragma: no cover
    itk = None
    ELASTIX_AVAILABLE = False


def _sitk_to_itk(img: sitk.Image):
    """SimpleITK <-> itk roundtrip via numpy. Geometry preserved."""
    arr = sitk.GetArrayFromImage(img)
    itk_img = itk.GetImageFromArray(arr.astype(np.float32))
    itk_img.SetOrigin(img.GetOrigin())
    itk_img.SetSpacing(img.GetSpacing())
    # itk expects direction as a flat tuple, sitk gives it the same way
    direction = np.array(img.GetDirection(), dtype=float).reshape(3, 3)
    itk_img.SetDirection(itk.matrix_from_array(direction))
    return itk_img


def _itk_to_sitk(img) -> sitk.Image:
    arr = itk.GetArrayFromImage(img).astype(np.float32)
    out = sitk.GetImageFromArray(arr)
    out.SetOrigin(tuple(img.GetOrigin()))
    out.SetSpacing(tuple(img.GetSpacing()))
    direction = np.array(itk.array_from_matrix(img.GetDirection())).flatten()
    out.SetDirection([float(v) for v in direction])
    return out


def _itk_vector_to_sitk(img) -> sitk.Image:
    """Convert an itk vector image (deformation field) to a sitk
    multi-component image. Preserves geometry."""
    arr = itk.GetArrayFromImage(img)  # shape (Z, Y, X, 3) for 3D
    sitk_img = sitk.GetImageFromArray(arr, isVector=True)
    sitk_img.SetOrigin(tuple(img.GetOrigin()))
    sitk_img.SetSpacing(tuple(img.GetSpacing()))
    direction = np.array(itk.array_from_matrix(img.GetDirection())).flatten()
    sitk_img.SetDirection([float(v) for v in direction])
    return sitk_img


def _build_param_object(
    initial_alignment: str,
    n_iterations: int,
    preset: str = "default",
    metric: str = "mi",
):
    """Assemble elastix parameter object.

    preset:
      - "default": elastix default rigid/affine/bspline presets.
      - "knee":    knee-MRI optimised, multi-stage B-spline 16/8/4 mm grid.

    metric:
      - "mi"  AdvancedMattesMutualInformation (good for multi-modal, default).
      - "ncc" AdvancedNormalizedCorrelation (better for same-modality
              like DESS-DESS where the intensity relationship is linear).
    """
    po = itk.ParameterObject.New()
    maps_added = 0

    metric_name = (
        "AdvancedNormalizedCorrelation" if metric == "ncc" else "AdvancedMattesMutualInformation"
    )

    def _patch_metric(m):
        m["Metric"] = [metric_name]

    if initial_alignment in ("rigid", "rigid+affine"):
        rigid = po.GetDefaultParameterMap("rigid")
        rigid["MaximumNumberOfIterations"] = [str(n_iterations)]
        if preset == "knee":
            rigid["NumberOfHistogramBins"] = ["64"]
        _patch_metric(rigid)
        po.AddParameterMap(rigid)
        maps_added += 1

    if initial_alignment == "rigid+affine":
        affine = po.GetDefaultParameterMap("affine")
        affine["MaximumNumberOfIterations"] = [str(n_iterations)]
        if preset == "knee":
            affine["NumberOfHistogramBins"] = ["64"]
        _patch_metric(affine)
        po.AddParameterMap(affine)
        maps_added += 1

    if preset == "knee":
        for grid_mm in (16.0, 8.0, 4.0):
            b = po.GetDefaultParameterMap("bspline")
            b["MaximumNumberOfIterations"] = [str(n_iterations)]
            b["NumberOfHistogramBins"] = ["64"]
            b["FinalGridSpacingInPhysicalUnits"] = [str(grid_mm)]
            b["NumberOfSpatialSamples"] = ["4096"]
            b["NewSamplesEveryIteration"] = ["true"]
            _patch_metric(b)
            po.AddParameterMap(b)
            maps_added += 1
    else:
        bspline = po.GetDefaultParameterMap("bspline")
        bspline["MaximumNumberOfIterations"] = [str(n_iterations)]
        _patch_metric(bspline)
        po.AddParameterMap(bspline)
        maps_added += 1

    return po, maps_added


class ElastixBackend(RegistrationBackend):
    name = "elastix"

    def __init__(self, preset: str = "default", metric: str = "mi"):
        """preset: 'default' (generic) or 'knee' (knee-MRI tuned).
        metric: 'mi' (Mattes MI) or 'ncc' (NormalizedCorrelation, recommended
        for same-modality like DESS-DESS)."""
        self.preset = preset
        self.metric = metric

    def register(
        self,
        fixed: sitk.Image,
        moving: sitk.Image,
        source_mask: Optional[sitk.Image] = None,
        *,
        n_iterations: int = 200,
        use_demons: bool = True,  # ignored — elastix has its own refinement
        initial_alignment: str = "rigid+affine",
        fixed_mask: Optional[sitk.Image] = None,
        moving_mask: Optional[sitk.Image] = None,
    ) -> BackendResult:
        """elastix-based deformable registration.

        fixed_mask / moving_mask: optional binary masks (sitk.Image) that
        restrict where the registration metric is evaluated. Very
        effective when you know roughly where the anatomy of interest
        sits — the algorithm stops chasing irrelevant background pixels.
        Both masks (or just one) can be passed.
        """
        if not ELASTIX_AVAILABLE:
            raise RuntimeError("itk-elastix not installed")

        # elastix wants itk images
        fixed_itk = _sitk_to_itk(sitk.Cast(fixed, sitk.sitkFloat32))
        moving_itk = _sitk_to_itk(sitk.Cast(moving, sitk.sitkFloat32))

        param_object, n_maps = _build_param_object(
            initial_alignment, n_iterations, preset=self.preset, metric=self.metric
        )

        elastix = itk.ElastixRegistrationMethod.New(fixed_itk, moving_itk)
        elastix.SetParameterObject(param_object)
        if fixed_mask is not None:
            # elastix expects uint8 mask
            fm = _sitk_to_itk(sitk.Cast(fixed_mask, sitk.sitkFloat32))
            fm_uint8 = itk.cast_image_filter(fm, ttype=(type(fm), itk.Image[itk.UC, 3]))
            elastix.SetFixedMask(fm_uint8)
        if moving_mask is not None:
            mm = _sitk_to_itk(sitk.Cast(moving_mask, sitk.sitkFloat32))
            mm_uint8 = itk.cast_image_filter(mm, ttype=(type(mm), itk.Image[itk.UC, 3]))
            elastix.SetMovingMask(mm_uint8)
        elastix.SetLogToConsole(False)
        elastix.Update()

        result_image = elastix.GetOutput()
        result_params = elastix.GetTransformParameterObject()

        # Compute the dense deformation field by passing an identity image
        # through transformix.
        transformix = itk.TransformixFilter.New(moving_itk)
        transformix.SetTransformParameterObject(result_params)
        transformix.SetComputeDeformationField(True)
        transformix.Update()
        deformation_field_itk = transformix.GetOutputDeformationField()

        # Warp the mask through the same transform (nearest neighbour)
        warped_mask = None
        if source_mask is not None:
            mask_itk = _sitk_to_itk(sitk.Cast(source_mask, sitk.sitkFloat32))
            # Clone the parameter object so we can tune for mask warping
            mask_params = itk.ParameterObject.New()
            for i in range(n_maps):
                m = dict(result_params.GetParameterMap(i))
                # Override interpolator to nearest neighbour for labels
                m["ResampleInterpolator"] = ["FinalNearestNeighborInterpolator"]
                m["FinalBSplineInterpolationOrder"] = ["0"]
                m["ResultImagePixelType"] = ["unsigned char"]
                mask_params.AddParameterMap(m)
            mask_tx = itk.TransformixFilter.New(mask_itk)
            mask_tx.SetTransformParameterObject(mask_params)
            mask_tx.Update()
            warped_mask_itk = mask_tx.GetOutput()
            warped_mask = sitk.Cast(_itk_to_sitk(warped_mask_itk), sitk.sitkUInt8)

        # Build sitk displacement field for the caller
        disp = _itk_vector_to_sitk(deformation_field_itk)

        # elastix doesn't return a single metric value the same way SITK does
        # (one per parameter map). Take the last map's final metric.
        try:
            final_metric = float(
                result_params.GetParameterMap(n_maps - 1).get("FinalMetricValue", ["nan"])[0]
            )
        except Exception:
            final_metric = float("nan")

        # Iteration count: sum across maps if available
        iters_total = 0
        for i in range(n_maps):
            try:
                iters_total += int(
                    result_params.GetParameterMap(i).get("MaximumNumberOfIterations", ["0"])[0]
                )
            except Exception:
                pass

        log.info("elastix: %d param maps, final_metric=%s", n_maps, final_metric)

        return BackendResult(
            warped_mask=warped_mask,
            displacement_field=disp,
            final_metric=final_metric,
            iterations=iters_total,
            backend="elastix",
            extra={
                "param_maps": n_maps,
                "initial_alignment": initial_alignment,
            },
        )
