from io import BytesIO

import numpy as np
from PIL import Image

LABEL_COLORS = [
    (255, 0, 0),      # Red
    (0, 255, 0),      # Green
    (0, 0, 255),      # Blue
    (255, 255, 0),    # Yellow
    (255, 0, 255),    # Magenta
    (0, 255, 255),    # Cyan
    (255, 128, 0),    # Orange
    (128, 0, 255),    # Purple
    (0, 255, 128),    # Spring Green
    (255, 0, 128),    # Rose
]


def normalize_dicom(arr: np.ndarray) -> np.ndarray:
    arr = arr.astype(np.float32)
    p1, p99 = np.percentile(arr, (1, 99))
    arr = np.clip(arr, p1, p99)
    arr = (arr - p1) / (p99 - p1 + 1e-8) * 255
    return arr.astype(np.uint8)


def slice_to_png(dicom_volume: np.ndarray, slice_idx: int) -> bytes:
    slice_data = dicom_volume[slice_idx]
    normalized = normalize_dicom(slice_data)
    img = Image.fromarray(normalized, mode='L').convert('RGB')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()


def slice_with_mask_to_png(
    dicom_volume: np.ndarray,
    mask_volume: np.ndarray,
    slice_idx: int,
    alpha: float = 0.4
) -> bytes:
    slice_data = dicom_volume[slice_idx]
    normalized = normalize_dicom(slice_data)
    rgb = np.stack([normalized, normalized, normalized], axis=-1)

    if mask_volume is not None and slice_idx < mask_volume.shape[0]:
        mask_slice = mask_volume[slice_idx]
        labels = np.unique(mask_slice[mask_slice > 0])

        for label in labels:
            color = LABEL_COLORS[int(label - 1) % len(LABEL_COLORS)]
            mask = mask_slice == label
            for c in range(3):
                rgb[:, :, c] = np.where(
                    mask,
                    (1 - alpha) * rgb[:, :, c] + alpha * color[c],
                    rgb[:, :, c]
                )

    img = Image.fromarray(rgb.astype(np.uint8), mode='RGB')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()
