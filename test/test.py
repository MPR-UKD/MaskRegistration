import pytest
import tempfile
from pathlib import Path
from src.MaskRegistration import transform

# Define fixtures or test data at module level
@pytest.fixture
def test_data():
    return Path(__file__).parent / "test_data"


@pytest.fixture
def temp_path():
    return Path(tempfile.mkdtemp())


# Test cases
def test_transform_dess_to_t2(test_data, temp_path):
    dess_folder = test_data / "6_PRE_dess_cor_16654"
    t2_folder = test_data / "10_T2_map_cor_25681"
    output_file = temp_path / "output_mask.nii.gz"

    transform(
        input_dicom_folder_1=dess_folder,
        input_mask_file=dess_folder / "mask.nii.gz",
        input_dicom_folder_2=t2_folder,
        out_nii_file=output_file
    )

    # Write assertions here to check if the function worked as expected.
    # For example, check if the output file was created and if it has the expected properties.
    assert output_file.exists(), "Output file was not created"


def test_transform_dess_to_dGEMRIC(test_data, temp_path):
    dess_folder = test_data / "6_PRE_dess_cor_16654"
    dGEMRIC_folder = test_data / "16_PRE_dGEMRIC_cor_FLIP1_28830"
    output_file = temp_path / "output_mask_2.nii.gz"

    transform(
        input_dicom_folder_1=dess_folder,
        input_mask_file=dess_folder / "mask.nii.gz",
        input_dicom_folder_2=dGEMRIC_folder,
        out_nii_file=output_file
    )

    # Write assertions here.
    assert output_file.exists(), "Output file was not created"


def test_transform_dess_to_t1rho(test_data, temp_path):
    dess_folder = test_data / "6_PRE_dess_cor_16654"
    t1rho_folder = test_data / "T1rho" / "12_T1rho_cor_27534"
    output_file = temp_path / "output_mask_3.nii.gz"

    transform(
        input_dicom_folder_1=dess_folder,
        input_mask_file=dess_folder / "mask.nii.gz",
        input_dicom_folder_2=t1rho_folder,
        out_nii_file=output_file
    )

    # Write assertions here.
    assert output_file.exists(), "Output file was not created"

if __name__ == '__main__':
    pytest.main()