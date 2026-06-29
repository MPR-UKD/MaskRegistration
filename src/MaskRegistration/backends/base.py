"""Backend interface for deformable registration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import SimpleITK as sitk


@dataclass
class BackendResult:
    """Backend-agnostic result of a deformable registration."""

    warped_mask: Optional[sitk.Image]
    displacement_field: sitk.Image
    final_metric: float
    iterations: int
    backend: str
    extra: dict = field(default_factory=dict)


class RegistrationBackend(ABC):
    """Abstract base. Backends register a moving image onto a fixed image
    and (optionally) warp a mask through the resulting transform."""

    name: str = "base"

    @abstractmethod
    def register(
        self,
        fixed: sitk.Image,
        moving: sitk.Image,
        source_mask: Optional[sitk.Image] = None,
        *,
        n_iterations: int = 200,
        use_demons: bool = True,
        initial_alignment: str = "rigid+affine",
        fixed_mask: Optional[sitk.Image] = None,
        moving_mask: Optional[sitk.Image] = None,
    ) -> BackendResult:
        """Run the registration and return a BackendResult.

        fixed_mask / moving_mask are optional binary masks (anywhere
        non-zero counts as 'inside') that restrict where the registration
        metric is evaluated. Backends that don't support masks must
        ignore them silently.
        """
        raise NotImplementedError
