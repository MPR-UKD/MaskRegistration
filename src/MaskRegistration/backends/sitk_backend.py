"""SimpleITK backend: rigid + affine + B-spline + Demons.

Default backend, always available. Slower than elastix but with no
extra dependency.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import SimpleITK as sitk

from MaskRegistration.backends.base import BackendResult, RegistrationBackend

log = logging.getLogger("MaskRegistration.sitk")


def _resample(moving, fixed, transform=None, interp=sitk.sitkLinear, default=0.0):
    rf = sitk.ResampleImageFilter()
    rf.SetReferenceImage(fixed)
    rf.SetInterpolator(interp)
    rf.SetDefaultPixelValue(default)
    if transform is not None:
        rf.SetTransform(transform)
    return rf.Execute(moving)


def _rigid(fixed, moving, n_iter=200):
    initial = sitk.CenteredTransformInitializer(
        fixed,
        moving,
        sitk.Euler3DTransform(),
        sitk.CenteredTransformInitializerFilter.GEOMETRY,
    )
    R = sitk.ImageRegistrationMethod()
    R.SetMetricAsMattesMutualInformation(numberOfHistogramBins=32)
    R.SetMetricSamplingStrategy(R.RANDOM)
    R.SetMetricSamplingPercentage(0.1)
    R.SetInterpolator(sitk.sitkLinear)
    R.SetOptimizerAsRegularStepGradientDescent(
        learningRate=2.0,
        minStep=1e-4,
        numberOfIterations=n_iter,
        gradientMagnitudeTolerance=1e-8,
    )
    R.SetOptimizerScalesFromPhysicalShift()
    R.SetInitialTransform(initial, inPlace=False)
    R.SetShrinkFactorsPerLevel([8, 4, 2, 1])
    R.SetSmoothingSigmasPerLevel([4, 2, 1, 0])
    R.SmoothingSigmasAreSpecifiedInPhysicalUnitsOn()
    tx = R.Execute(fixed, moving)
    log.info("rigid:  metric=%.4f iters=%d", R.GetMetricValue(), R.GetOptimizerIteration())
    return tx


def _affine(fixed, moving, init_tx, n_iter=200):
    R = sitk.ImageRegistrationMethod()
    R.SetMetricAsMattesMutualInformation(numberOfHistogramBins=32)
    R.SetMetricSamplingStrategy(R.RANDOM)
    R.SetMetricSamplingPercentage(0.15)
    R.SetInterpolator(sitk.sitkLinear)
    R.SetOptimizerAsRegularStepGradientDescent(
        learningRate=1.0,
        minStep=1e-4,
        numberOfIterations=n_iter,
        gradientMagnitudeTolerance=1e-8,
    )
    R.SetOptimizerScalesFromPhysicalShift()
    R.SetMovingInitialTransform(init_tx)
    R.SetInitialTransform(sitk.AffineTransform(3), inPlace=False)
    R.SetShrinkFactorsPerLevel([4, 2, 1])
    R.SetSmoothingSigmasPerLevel([2, 1, 0])
    R.SmoothingSigmasAreSpecifiedInPhysicalUnitsOn()
    tx = R.Execute(fixed, moving)
    log.info("affine: metric=%.4f iters=%d", R.GetMetricValue(), R.GetOptimizerIteration())
    return tx


def _bspline(
    fixed,
    moving_aligned,
    n_iter: int = 200,
    grid: Tuple[int, int, int] = (8, 8, 4),
):
    initial = sitk.BSplineTransformInitializer(image1=fixed, transformDomainMeshSize=list(grid))
    R = sitk.ImageRegistrationMethod()
    R.SetMetricAsMattesMutualInformation(numberOfHistogramBins=32)
    R.SetMetricSamplingStrategy(R.RANDOM)
    R.SetMetricSamplingPercentage(0.2)
    R.SetInterpolator(sitk.sitkLinear)
    R.SetOptimizerAsLBFGSB(
        gradientConvergenceTolerance=1e-5,
        numberOfIterations=n_iter,
        maximumNumberOfCorrections=5,
        maximumNumberOfFunctionEvaluations=1000,
        costFunctionConvergenceFactor=1e7,
    )
    R.SetInitialTransformAsBSpline(initial, inPlace=False)
    R.SetShrinkFactorsPerLevel([4, 2, 1])
    R.SetSmoothingSigmasPerLevel([2, 1, 0])
    R.SmoothingSigmasAreSpecifiedInPhysicalUnitsOn()
    tx = R.Execute(fixed, moving_aligned)
    log.info("bspline: metric=%.4f iters=%d", R.GetMetricValue(), R.GetOptimizerIteration())
    return tx, R.GetMetricValue(), R.GetOptimizerIteration()


class SitkBackend(RegistrationBackend):
    name = "sitk"

    def register(
        self,
        fixed: sitk.Image,
        moving: sitk.Image,
        source_mask: Optional[sitk.Image] = None,
        *,
        n_iterations: int = 200,
        use_demons: bool = True,
        initial_alignment: str = "rigid+affine",
    ) -> BackendResult:
        fixed = sitk.Cast(fixed, sitk.sitkFloat32)
        moving = sitk.Cast(moving, sitk.sitkFloat32)

        pre_tx = None
        if initial_alignment in ("rigid", "rigid+affine"):
            pre_tx = _rigid(fixed, moving)
        if initial_alignment == "rigid+affine":
            pre_tx = _affine(fixed, moving, pre_tx)

        moving_aligned = (
            _resample(moving, fixed, pre_tx) if pre_tx is not None else _resample(moving, fixed)
        )

        bspline_tx, final_metric, iters = _bspline(fixed, moving_aligned, n_iter=n_iterations)

        composite = sitk.CompositeTransform(3)
        if pre_tx is not None:
            composite.AddTransform(pre_tx)
        composite.AddTransform(bspline_tx)

        used_demons = False
        if use_demons:
            try:
                pre_aligned = _resample(moving_aligned, fixed, bspline_tx)
                demons = sitk.FastSymmetricForcesDemonsRegistrationFilter()
                demons.SetNumberOfIterations(50)
                demons.SetStandardDeviations(1.5)
                field = demons.Execute(fixed, pre_aligned)
                composite.AddTransform(sitk.DisplacementFieldTransform(field))
                used_demons = True
            except Exception as e:
                log.warning("Demons refinement failed: %s", e)

        disp_filter = sitk.TransformToDisplacementFieldFilter()
        disp_filter.SetReferenceImage(fixed)
        disp = disp_filter.Execute(composite)

        warped_mask = None
        if source_mask is not None:
            warped_mask = sitk.Cast(
                _resample(
                    sitk.Cast(source_mask, sitk.sitkFloat32),
                    fixed,
                    composite,
                    interp=sitk.sitkNearestNeighbor,
                    default=0,
                ),
                sitk.sitkUInt8,
            )

        return BackendResult(
            warped_mask=warped_mask,
            displacement_field=disp,
            final_metric=float(final_metric),
            iterations=int(iters),
            backend="sitk",
            extra={"used_demons": used_demons, "initial_alignment": initial_alignment},
        )
