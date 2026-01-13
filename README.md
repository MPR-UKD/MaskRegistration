# MaskRegistration
MaskRegistration is a wrapper-tool for [SimpleITK](https://github.com/SimpleITK/SimpleITK) that takes in two DICOM image folders and a mask file, and performs a registration process to align the mask file with the images in the second DICOM folder. The resulting image is then saved in NIFTI format.

**Registration Steps:**

1. Convert the mask file to DICOM format in a temporary directory
2. If auto-detect mode: try both slice directions (normal and reverse), compare results by number of preserved labels and pixels, pick the better one
3. Optionally upsample target Z-axis by subpixel factor for finer registration
4. Use ResampleImageFilter with nearest neighbor interpolation to align mask with target geometry
5. If subpixel was used: downsample back using OR-logic (if any sub-voxel is positive, result is positive)
6. Save result as NIFTI file

## Easy use

MaskRegistration can be easily used by downloading its included exe files:

- [CLI](/dist/MaskRegistration.exe)
- [GUI](/dist/MaskRegistrationGUI.exe)

or as whl file to include the transformation step in your own project:

- [WHL](/dist/maskregistration-0.1.0-py3-none-any.whl)

## Environment Setup

Alternatively, you can use the source code, which has the advantage that you can make changes.

1. Install [python3.10](https://www.python.org/downloads/release/python-3100/) and [uv](https://docs.astral.sh/uv/)
2. Clone MaskRegistration Repository
 ```bash
git clone https://github.com/ludgerradke/MaskRegistration
 ```
3. Open MaskRegistration
 ```bash
cd MaskRegistration
 ```
4. Install dependencies
 ```bash
uv sync
 ```
5. Run Command Line Interface (CLI) or Graphical User Interface (GUI)

## Command Line Interface (MaskRegistration.py)

The command-line tool that performs a registration process to align a mask image with a series of DICOM images. The resulting image is saved in NIFTI format.

### Usage
 ```bash
uv run maskregistration -d1 <input_dcm1> -m <input_mask> -d2 <input_dcm2> -o <output_mask> [options]
 ```

**Required arguments:**

- **-d1, --input_dcm1** - Path to the first DICOM folder (source/reference)
- **-m, --input_mask** - Path to the mask file (NIFTI format)
- **-d2, --input_dcm2** - Path to the second DICOM folder (target)
- **-o, --output_mask** - Path to the output NIFTI file

**Optional arguments:**

- **--reverse** - Slice direction mode: `auto` (default), `true`, or `false`
  - `auto`: Tries both directions and picks the one with more preserved ROIs
  - `true`: Force reverse slice order
  - `false`: Force normal slice order

- **--subpixel N** - Upsample target Z-axis by factor N before registration, then downsample with OR-logic (default: 1 = disabled). Useful for preserving small structures when downsampling to lower resolution.

### Examples

Basic registration with auto-detection:
 ```bash
uv run maskregistration -d1 dicom_folder_1 -m mask.nii.gz -d2 dicom_folder_2 -o output_mask.nii.gz
 ```

With subpixel upsampling (preserves small ROIs during heavy downsampling):
 ```bash
uv run maskregistration -d1 dicom_folder_1 -m mask.nii.gz -d2 dicom_folder_2 -o output_mask.nii.gz --subpixel 9
 ```

## Graphical User Interface (GUI)

![](/assets/show.gif)

The MaskRegistration GUI is a PyQt6-based graphical user interface (GUI) that allows the user to input two DICOM image folders, a mask file, and an output file path, and performs a registration process to align the mask file with the images in the second DICOM folder. The resulting image is then saved in the specified output file.

The GUI consists of several widgets, including buttons, text fields, and a layout. The buttons allow the user to browse for and select the input DICOM folders, mask file, and output file. The text fields display the selected paths. The layout arranges the widgets in a grid.

The GUI also has a "RUN" button that, when clicked, executes the transform function from the backend module with the specified input and output paths.

### Usage
 ```bash
uv run maskregistration-gui
```

## Build

To build standalone executables:

```bash
# macOS
./build_mac.sh

# Windows
./build.sh
```

## Development

Install with dev dependencies:
```bash
uv sync --extra dev
```

Run tests:
```bash
uv run pytest
```

Format code:
```bash
uv run black .
```

## License
[GNU General Public License 3](https://www.gnu.org/licenses/gpl-3.0.html)

The GNU General Public License is a free, copyleft license for software and other kinds of works.

### Git hooks
Install "pre-commit"
```bash
uv run pip install pre-commit
```

then run:
```bash
uv run pre-commit install
```

# Support

If you really like this repository and find it useful, please consider starring it, so that it can reach a broader audience of like-minded people.
