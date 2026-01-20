# MaskRegistration

MaskRegistration is a tool for aligning segmentation masks between different DICOM series using [SimpleITK](https://github.com/SimpleITK/SimpleITK).

**Registration Steps:**

1. Convert the mask file to DICOM format in a temporary directory
2. If auto-detect mode: try both slice directions (normal and reverse), compare results by number of preserved labels and pixels, pick the better one
3. Optionally upsample target Z-axis by subpixel factor for finer registration
4. Use ResampleImageFilter with nearest neighbor interpolation to align mask with target geometry
5. If subpixel was used: downsample back using OR-logic (if any sub-voxel is positive, result is positive)
6. Save result as NIFTI file

## Installation

```bash
# Clone repository
git clone https://github.com/ludgerradke/MaskRegistration
cd MaskRegistration

# Install dependencies
uv sync
```

## Web Interface

The web interface provides an interactive viewer for comparing source and target DICOM images with mask overlay.

```bash
uv run maskregistration-web
```

Opens browser at `http://localhost:8000` with:
- Dual viewer with Curtain/Blend/Split modes
- Aligned vs Original comparison toggle
- Synchronized slice navigation
- Auto-detection of slice direction
- Export registered mask

## Command Line Interface

```bash
uv run maskregistration -d1 <source_dicom> -m <mask> -d2 <target_dicom> -o <output>
```

**Required arguments:**

- **-d1, --input_dcm1** - Path to source DICOM folder
- **-m, --input_mask** - Path to mask file (NIFTI format)
- **-d2, --input_dcm2** - Path to target DICOM folder
- **-o, --output_mask** - Path to output NIFTI file

**Optional arguments:**

- **--reverse** - Slice direction: `auto` (default), `true`, or `false`
- **--subpixel N** - Upsample factor for preserving small structures (default: 1)

**Example:**

```bash
uv run maskregistration -d1 dicom1 -m mask.nii.gz -d2 dicom2 -o output.nii.gz --subpixel 9
```

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Format code
uv run black .
```

## License

[GNU General Public License 3](https://www.gnu.org/licenses/gpl-3.0.html)
