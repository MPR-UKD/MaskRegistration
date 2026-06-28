"""Pluggable backends for deformable registration.

Every backend implements the same ``register`` API so the wrapper
``deformable_register`` can pick the best engine for the job.

Built-in backends:
  - ``sitk``    — SimpleITK 3-stage (rigid + affine + B-spline + Demons).
                  Always available, no extra dependency.
  - ``elastix`` — itk-elastix with validated parameter presets
                  ("rigid", "affine", "bspline"). Best out-of-the-box
                  accuracy for medical images. Requires `pip install
                  itk-elastix`.

Use ``available_backends()`` to discover what's installed at runtime.
"""

from MaskRegistration.backends.base import BackendResult, RegistrationBackend
from MaskRegistration.backends.elastix_backend import (
    ELASTIX_AVAILABLE,
    ElastixBackend,
)
from MaskRegistration.backends.sitk_backend import SitkBackend


def available_backends() -> list[str]:
    """Return names of backends that are installable in this environment."""
    out = ["sitk"]
    if ELASTIX_AVAILABLE:
        out.append("elastix")
    return out


def get_backend(name: str) -> RegistrationBackend:
    """Resolve a backend name to an instance.

    ``"auto"`` picks elastix if installed, otherwise SimpleITK.
    """
    if name == "auto":
        name = "elastix" if ELASTIX_AVAILABLE else "sitk"
    if name == "sitk":
        return SitkBackend()
    if name == "elastix":
        if not ELASTIX_AVAILABLE:
            raise RuntimeError(
                "elastix backend requested but itk-elastix is not installed. "
                "Run: pip install itk-elastix"
            )
        return ElastixBackend()
    raise ValueError(f"unknown backend '{name}'. Available: {available_backends()}")


__all__ = [
    "available_backends",
    "BackendResult",
    "ElastixBackend",
    "get_backend",
    "RegistrationBackend",
    "SitkBackend",
]
