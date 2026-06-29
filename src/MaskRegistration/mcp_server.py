"""MCP server for MaskRegistration.

Exposes the library as MCP tools so an LLM agent (e.g. Claude Code) can
register knee MRI masks via plain natural-language commands instead of
clicking through the web UI.

Install + run:
    pip install maskregistration[mcp]
    maskregistration-mcp                # stdio mode (default)
    maskregistration-mcp --transport sse --port 8765    # network mode

Add to Claude Code config (~/.claude/config.json):
    "mcpServers": {
      "maskreg": {
        "command": "maskregistration-mcp"
      }
    }

Tools exposed:
  - list_backends                     which engines are installed
  - check_alignment                   verify mask/DICOM affines line up
  - register_affine                   transfer a mask via affine resample
  - register_deformable               same but with deformable + field
  - field_transfer_lowres_to_highres  estimate field on low-res, apply to high-res
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from MaskRegistration import (
    available_backends,
    check_alignment as _check_alignment,
    transform as _transform,
    transform_deformable as _transform_deformable,
)
from MaskRegistration.field_transfer import estimate_field_lowres_apply_highres

log = logging.getLogger("maskregistration.mcp")

mcp = FastMCP("MaskRegistration")


@mcp.tool()
def list_backends() -> dict:
    """List registration backends available in this environment.

    Always present: 'sitk'. Optionally: 'elastix' (when itk-elastix is
    installed). 'auto' picks elastix if available, otherwise sitk.
    """
    return {"available": available_backends()}


@mcp.tool()
def check_mask_alignment(
    mask_file: str,
    dicom_folder: str,
    drift_warn_mm: float = 5.0,
    drift_fail_mm: float = 20.0,
) -> dict:
    """Verify that a NIfTI mask was drawn on a given DICOM series.

    Compares the mask's affine origin with the DICOM's first-slice
    ImagePositionPatient. Returns drift in mm and an OK flag. Drift over
    drift_fail_mm almost certainly means the mask comes from a different
    scan.
    """
    rep = _check_alignment(
        Path(mask_file),
        Path(dicom_folder),
        drift_warn_mm=drift_warn_mm,
        drift_fail_mm=drift_fail_mm,
    )
    # Make the dict JSON-serialisable
    return {
        "drift_mm": float(rep["drift_mm"]) if rep["drift_mm"] is not None else None,
        "mask_origin": list(rep["mask_origin"]) if rep["mask_origin"] is not None else None,
        "dicom_ipp": list(rep["dicom_ipp"]) if rep["dicom_ipp"] is not None else None,
        "ok": bool(rep["ok"]),
    }


@mcp.tool()
def register_affine(
    source_dicom: str,
    mask: str,
    target_dicom: str,
    output_mask: str,
    reverse: str = "auto",
    subpixel: int = 1,
    auto_axes: str = "z",
) -> dict:
    """Transfer a mask between two DICOM series via affine resample.

    Fast (sub-second per volume), no deformation. Right pick when the
    two series describe the same anatomy on the same physical grid
    (e.g. DESS -> T2 in the same session).

    Args:
        source_dicom: DICOM folder the mask was drawn on
        mask: path to NIfTI mask
        target_dicom: DICOM folder to transfer the mask onto
        output_mask: where to write the warped mask (NIfTI)
        reverse: 'auto', 'true', 'false' — Z-direction handling
        subpixel: upsample target Z by this factor for fine structures
        auto_axes: 'z' or 'xyz' — which flips to try in auto-detect
    """
    reverse_map = {"auto": None, "true": True, "false": False}
    rev = reverse_map.get(reverse, None)
    result = _transform(
        input_dicom_folder_1=Path(source_dicom),
        input_mask_file=Path(mask),
        input_dicom_folder_2=Path(target_dicom),
        out_nii_file=Path(output_mask),
        reverse=rev,
        subpixel_factor=subpixel,
        auto_axes=auto_axes,
    )
    return {
        "output_mask": output_mask,
        "used_reverse": result["used_reverse"],
        "used_flips": list(result["used_flips"]),
        "label_loss": result["label_loss"],
        "volume_ratio": float(result["volume_ratio"])
        if result["volume_ratio"] is not None
        else None,
        "alignment_drift_mm": result["alignment"]["drift_mm"] if result.get("alignment") else None,
    }


@mcp.tool()
def register_deformable(
    source_dicom: str,
    mask: str,
    target_dicom: str,
    output_mask: str,
    output_displacement: Optional[str] = None,
    backend: str = "auto",
    n_iterations: int = 500,
    initial_alignment: str = "rigid+affine",
) -> dict:
    """Transfer a mask via deformable registration.

    Slower (~10-30 s with elastix, minutes with SimpleITK) but recovers
    patient motion / non-rigid deformation. Right pick when the two
    scans were taken at different times and the patient moved between
    them (e.g. same patient, two visits).

    Args:
        source_dicom: DICOM folder the mask was drawn on
        mask: path to NIfTI mask
        target_dicom: DICOM folder to transfer the mask onto
        output_mask: where to write the warped mask
        output_displacement: optional NIfTI for the dense displacement field
        backend: 'auto', 'sitk', or 'elastix'
        n_iterations: optimiser iterations per registration stage
        initial_alignment: 'rigid+affine' (default, robust), 'rigid', or 'none'
    """
    result = _transform_deformable(
        input_dicom_folder_1=Path(source_dicom),
        input_mask_file=Path(mask),
        input_dicom_folder_2=Path(target_dicom),
        out_nii_file=Path(output_mask),
        out_displacement_file=Path(output_displacement) if output_displacement else None,
        backend=backend,
        n_iterations=n_iterations,
        initial_alignment=initial_alignment,
    )
    return {
        "output_mask": output_mask,
        "displacement_file": result.get("displacement_file"),
        "backend": result["backend"],
        "final_metric": float(result["final_metric"])
        if result["final_metric"] is not None
        else None,
        "iterations": result["iterations"],
        "used_demons": result.get("used_demons", False),
    }


@mcp.tool()
def field_transfer_lowres_to_highres(
    lowres_source_dicom: str,
    lowres_target_dicom: str,
    highres_source_dicom: str,
    highres_target_dicom: str,
    source_mask: str,
    output_mask: str,
    output_displacement: Optional[str] = None,
    backend: str = "auto",
    n_iterations: int = 200,
) -> dict:
    """Estimate the deformation field on a low-resolution sequence,
    then apply it to a higher-resolution sequence.

    Example: estimate the field on T2 maps (cheap), warp the high-res
    DESS mask through it. The deformation is anatomical, so it's
    sequence-independent and the low-res estimate transfers cleanly.
    """
    res = estimate_field_lowres_apply_highres(
        lowres_source_dicom=Path(lowres_source_dicom),
        lowres_target_dicom=Path(lowres_target_dicom),
        highres_source_dicom=Path(highres_source_dicom),
        highres_target_dicom=Path(highres_target_dicom),
        source_mask_file=Path(source_mask),
        out_warped_mask=Path(output_mask),
        out_displacement_highres=Path(output_displacement) if output_displacement else None,
        backend=backend,
        n_iterations=n_iterations,
    )
    return {
        "output_mask": output_mask,
        "displacement_file": output_displacement,
        "backend": res.backend,
        "iterations": res.iterations,
        "speed_factor_estimate": res.speed_factor,
    }


def main():
    parser = argparse.ArgumentParser(description="MaskRegistration MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="stdio for Claude Code local install, sse for network",
    )
    parser.add_argument("--port", type=int, default=8765, help="port for SSE mode")
    parser.add_argument("--host", default="127.0.0.1", help="host for SSE mode")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    log.info("starting MaskRegistration MCP server on %s", args.transport)

    if args.transport == "sse":
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport="sse")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
