# PyInstaller for onefile CLI
poetry run pyinstaller --onefile --windowed --collect-submodules=pydicom --add-data="./src/MaskRegistration/loading.gif;."  --noconsole src/MaskRegistration/MaskRegistration.py --noconfirm

# PyInstaller for onefile GUI
poetry run pyinstaller --onefile --collect-submodules=pydicom --windowed --add-data="./src/MaskRegistration/loading.gif;." --noconsole src/MaskRegistration/MaskRegistrationGUI.py --noconfirm
