import shutil
import subprocess
import sys
import tempfile
import uuid
import webbrowser
from pathlib import Path
from threading import Thread
from typing import Literal

import nibabel as nib
import numpy as np
import SimpleITK as sitk
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from MaskRegistration.backend import transform
from MaskRegistration.utils import split_dcm
from MaskRegistration.web.viewer import slice_to_png, slice_with_mask_to_png

app = FastAPI()

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


class ImageMeta:
    def __init__(self, origin: tuple, spacing: tuple, direction: tuple, size: tuple):
        self.origin = origin
        self.spacing = spacing
        self.direction = direction
        self.size = size


class EchoData:
    def __init__(self):
        self.volumes: list[np.ndarray] = []
        self.metas: list[ImageMeta] = []
        self.current_echo: int = 0


class DataStore:
    def __init__(self):
        self.source_echos: EchoData = EchoData()
        self.target_echos: EchoData = EchoData()
        self.source_mask: np.ndarray | None = None
        self.target_mask: np.ndarray | None = None
        self.target_mask_meta: ImageMeta | None = None
        self.source_path: str = ""
        self.target_path: str = ""
        self.source_mask_path: str = ""
        self.output_path: str = ""
        self.temp_output_path: str = ""
        self.tasks: dict[str, dict] = {}

    def get_dicom(self, side: str) -> np.ndarray | None:
        echos = self.source_echos if side == "source" else self.target_echos
        if not echos.volumes:
            return None
        return echos.volumes[echos.current_echo]

    def get_meta(self, side: str) -> ImageMeta | None:
        echos = self.source_echos if side == "source" else self.target_echos
        if not echos.metas:
            return None
        return echos.metas[echos.current_echo]


store = DataStore()


class PathRequest(BaseModel):
    path: str


class RegisterRequest(BaseModel):
    reverse: Literal["auto", "normal", "reverse"]
    subpixel: int = 1


@app.get("/")
def root():
    return Response(
        content=(static_dir / "index.html").read_text(),
        media_type="text/html"
    )


class BrowseRequest(BaseModel):
    mode: Literal["dir", "file", "save"]
    initial_dir: str = ""


def browse_macos(mode: str, initial_dir: str = "") -> str:
    if mode == "dir":
        script = 'tell application "System Events" to activate\n'
        script += 'return POSIX path of (choose folder'
        if initial_dir:
            script += f' default location POSIX file "{initial_dir}"'
        script += ')'
    elif mode == "file":
        script = 'tell application "System Events" to activate\n'
        script += 'return POSIX path of (choose file'
        if initial_dir:
            script += f' default location POSIX file "{initial_dir}"'
        script += ' of type {"nii", "gz", "public.item"})'
    else:
        script = 'tell application "System Events" to activate\n'
        script += 'return POSIX path of (choose file name'
        if initial_dir:
            script += f' default location POSIX file "{initial_dir}"'
        script += ' default name "mask.nii.gz")'

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


@app.post("/api/browse")
def browse(req: BrowseRequest):
    if sys.platform == "darwin":
        path = browse_macos(req.mode, req.initial_dir)
    else:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        initial = req.initial_dir if req.initial_dir else None

        if req.mode == "dir":
            path = filedialog.askdirectory(initialdir=initial)
        elif req.mode == "file":
            path = filedialog.askopenfilename(
                initialdir=initial,
                filetypes=[("NIFTI files", "*.nii *.nii.gz"), ("All files", "*.*")]
            )
        else:
            path = filedialog.asksaveasfilename(
                initialdir=initial,
                defaultextension=".nii.gz",
                filetypes=[("NIFTI files", "*.nii *.nii.gz")]
            )

        root.destroy()

    return {"path": path or ""}


@app.post("/api/dicom/{side}")
def load_dicom(side: Literal["source", "target"], req: PathRequest):
    path = Path(req.path)
    if not path.exists() or not path.is_dir():
        raise HTTPException(400, f"Invalid directory: {req.path}")

    reader = sitk.ImageSeriesReader()
    all_dicom_names = reader.GetGDCMSeriesFileNames(str(path))
    if not all_dicom_names:
        raise HTTPException(400, "No DICOM files found")

    echo_lists = split_dcm(all_dicom_names)

    echos = EchoData()
    for echo_files in echo_lists:
        reader.SetFileNames(echo_files)
        image = reader.Execute()
        arr = sitk.GetArrayFromImage(image)

        meta = ImageMeta(
            origin=image.GetOrigin(),
            spacing=image.GetSpacing(),
            direction=image.GetDirection(),
            size=image.GetSize()
        )

        echos.volumes.append(arr)
        echos.metas.append(meta)

    echos.current_echo = 0

    if side == "source":
        store.source_echos = echos
        store.source_path = req.path
    else:
        store.target_echos = echos
        store.target_path = req.path

    first_meta = echos.metas[0]
    first_vol = echos.volumes[0]

    return {
        "slices": first_vol.shape[0],
        "size": [first_vol.shape[2], first_vol.shape[1]],
        "origin": first_meta.origin,
        "spacing": first_meta.spacing,
        "echos": len(echo_lists),
    }


@app.post("/api/echo/{side}/{echo_idx}")
def set_echo(side: Literal["source", "target"], echo_idx: int):
    echos = store.source_echos if side == "source" else store.target_echos

    if echo_idx < 0 or echo_idx >= len(echos.volumes):
        raise HTTPException(400, f"Invalid echo index: {echo_idx}")

    echos.current_echo = echo_idx
    meta = echos.metas[echo_idx]
    vol = echos.volumes[echo_idx]

    return {
        "slices": vol.shape[0],
        "size": [vol.shape[2], vol.shape[1]],
        "origin": meta.origin,
        "spacing": meta.spacing,
    }


@app.post("/api/mask/{side}")
def load_mask(side: Literal["source", "target"], req: PathRequest):
    path = Path(req.path)
    if not path.exists():
        raise HTTPException(400, f"File not found: {req.path}")

    nii = nib.load(path)
    arr = np.asarray(nii.dataobj)
    arr = np.transpose(arr, (2, 1, 0))

    if side == "source":
        store.source_mask = arr
        store.source_mask_path = req.path
    else:
        store.target_mask = arr

    labels = np.unique(arr[arr > 0]).tolist()
    return {"slices": arr.shape[0], "labels": labels}


@app.get("/api/slice/aligned/{index}")
def get_aligned_slice(index: int, mask: bool = False, reverse: bool = False, t: str = None):
    source_dicom = store.get_dicom("source")
    target_dicom = store.get_dicom("target")
    source_meta = store.get_meta("source")
    target_meta = store.get_meta("target")

    if source_dicom is None or target_dicom is None:
        raise HTTPException(400, "Both DICOMs must be loaded")

    if index < 0 or index >= source_dicom.shape[0]:
        raise HTTPException(400, f"Invalid slice index: {index}")

    target_data = target_dicom
    if reverse:
        target_data = target_data[::-1, :, :]

    target_img = sitk.GetImageFromArray(target_data.astype(np.float32))
    target_img.SetOrigin(target_meta.origin)
    target_img.SetSpacing(target_meta.spacing)
    target_img.SetDirection(target_meta.direction)

    resampler = sitk.ResampleImageFilter()
    resampler.SetSize([source_meta.size[0], source_meta.size[1], source_meta.size[2]])
    resampler.SetOutputOrigin(source_meta.origin)
    resampler.SetOutputSpacing(source_meta.spacing)
    resampler.SetOutputDirection(source_meta.direction)
    resampler.SetInterpolator(sitk.sitkLinear)
    resampler.SetDefaultPixelValue(0)

    aligned = resampler.Execute(target_img)
    aligned_arr = sitk.GetArrayFromImage(aligned)

    mask_vol = None
    if mask and store.target_mask is not None:
        mask_img = sitk.GetImageFromArray(store.target_mask.astype(np.float32))
        mask_meta = store.target_mask_meta if store.target_mask_meta else target_meta
        mask_img.SetOrigin(mask_meta.origin)
        mask_img.SetSpacing(mask_meta.spacing)
        mask_img.SetDirection(mask_meta.direction)

        mask_resampler = sitk.ResampleImageFilter()
        mask_resampler.SetSize([source_meta.size[0], source_meta.size[1], source_meta.size[2]])
        mask_resampler.SetOutputOrigin(source_meta.origin)
        mask_resampler.SetOutputSpacing(source_meta.spacing)
        mask_resampler.SetOutputDirection(source_meta.direction)
        mask_resampler.SetInterpolator(sitk.sitkNearestNeighbor)
        mask_resampler.SetDefaultPixelValue(0)

        aligned_mask = mask_resampler.Execute(mask_img)
        mask_vol = sitk.GetArrayFromImage(aligned_mask).astype(np.uint8)

    if mask_vol is not None:
        png = slice_with_mask_to_png(aligned_arr, mask_vol, index)
    else:
        png = slice_to_png(aligned_arr, index)

    return Response(content=png, media_type="image/png")


@app.get("/api/slice/{side}/{index}")
def get_slice(side: Literal["source", "target"], index: int, mask: bool = False, t: str = None):
    dicom = store.get_dicom(side)
    if dicom is None:
        raise HTTPException(400, f"No {side} DICOM loaded")

    if index < 0 or index >= dicom.shape[0]:
        raise HTTPException(400, f"Invalid slice index: {index}")

    mask_vol = None
    if mask:
        mask_vol = store.source_mask if side == "source" else store.target_mask

    if mask_vol is not None:
        png = slice_with_mask_to_png(dicom, mask_vol, index)
    else:
        png = slice_to_png(dicom, index)

    return Response(content=png, media_type="image/png")


@app.post("/api/output")
def set_output(req: PathRequest):
    store.output_path = req.path
    return {"path": req.path}


@app.get("/api/spatial-relation")
def get_spatial_relation():
    sm = store.get_meta("source")
    tm = store.get_meta("target")
    if sm is None or tm is None:
        raise HTTPException(400, "Both DICOMs must be loaded")

    def get_bounds(meta):
        size_phys = [meta.size[i] * meta.spacing[i] for i in range(3)]
        return {
            "min": list(meta.origin),
            "max": [meta.origin[i] + size_phys[i] for i in range(3)],
            "size": list(meta.size),
            "spacing": list(meta.spacing),
            "size_mm": size_phys
        }

    source_bounds = get_bounds(sm)
    target_bounds = get_bounds(tm)

    overlap = [0, 0, 0]
    for i in range(3):
        overlap_min = max(source_bounds["min"][i], target_bounds["min"][i])
        overlap_max = min(source_bounds["max"][i], target_bounds["max"][i])
        overlap[i] = max(0, overlap_max - overlap_min)

    source_vol = source_bounds["size_mm"][0] * source_bounds["size_mm"][1] * source_bounds["size_mm"][2]
    target_vol = target_bounds["size_mm"][0] * target_bounds["size_mm"][1] * target_bounds["size_mm"][2]
    overlap_vol = overlap[0] * overlap[1] * overlap[2]

    overlap_pct_source = (overlap_vol / source_vol * 100) if source_vol > 0 else 0
    overlap_pct_target = (overlap_vol / target_vol * 100) if target_vol > 0 else 0

    offset = [target_bounds["min"][i] - source_bounds["min"][i] for i in range(3)]

    return {
        "source": source_bounds,
        "target": target_bounds,
        "overlap_mm": overlap,
        "overlap_vol_mm3": overlap_vol,
        "overlap_pct_source": round(overlap_pct_source, 1),
        "overlap_pct_target": round(overlap_pct_target, 1),
        "offset_mm": offset,
        "warning": overlap_pct_source < 50 or overlap_pct_target < 50,
        "error": overlap_vol == 0
    }


@app.post("/api/register")
def register(req: RegisterRequest):
    if not store.source_path:
        raise HTTPException(400, "No source DICOM loaded")
    if not store.source_mask_path:
        raise HTTPException(400, "No source mask loaded")
    if not store.target_path:
        raise HTTPException(400, "No target DICOM loaded")

    # Use temp file if no output path specified
    if not store.output_path:
        store.temp_output_path = tempfile.mktemp(suffix=".nii.gz")
    output_file = store.output_path or store.temp_output_path

    reverse_map = {"auto": None, "normal": False, "reverse": True}
    reverse = reverse_map[req.reverse]

    task_id = str(uuid.uuid4())
    store.tasks[task_id] = {"status": "running", "message": ""}

    def run_task():
        try:
            result = transform(
                input_dicom_folder_1=Path(store.source_path),
                input_mask_file=Path(store.source_mask_path),
                input_dicom_folder_2=Path(store.target_path),
                out_nii_file=Path(output_file),
                reverse=reverse,
                subpixel_factor=req.subpixel,
            )
            nii_img = sitk.ReadImage(output_file)
            arr = sitk.GetArrayFromImage(nii_img)
            store.target_mask = arr
            store.target_mask_meta = ImageMeta(
                origin=nii_img.GetOrigin(),
                spacing=nii_img.GetSpacing(),
                direction=nii_img.GetDirection(),
                size=nii_img.GetSize()
            )
            used_direction = "reverse" if result["used_reverse"] else "normal"
            store.tasks[task_id] = {
                "status": "done",
                "message": f"Registration complete (direction: {used_direction})",
                "used_direction": used_direction
            }
        except Exception as e:
            store.tasks[task_id] = {"status": "error", "message": str(e)}

    thread = Thread(target=run_task)
    thread.start()

    return {"task_id": task_id}


@app.get("/api/status/{task_id}")
def get_status(task_id: str):
    if task_id not in store.tasks:
        raise HTTPException(404, "Task not found")
    return store.tasks[task_id]


@app.post("/api/export")
def export_mask(req: PathRequest):
    source_file = store.output_path or store.temp_output_path
    if not source_file or not Path(source_file).exists():
        raise HTTPException(400, "No registered mask available")

    dest_path = Path(req.path)
    if not dest_path.suffix:
        dest_path = dest_path.with_suffix(".nii.gz")

    shutil.copy2(source_file, dest_path)
    return {"path": str(dest_path)}


def main():
    webbrowser.open("http://localhost:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
