#!/bin/bash

# PyInstaller for onefile CLI
uv run pyinstaller --onefile --windowed --collect-submodules=pydicom --add-data="./src/MaskRegistration/loading.gif:." --noconsole src/MaskRegistration/MaskRegistration.py --noconfirm

# PyInstaller for onefile GUI
uv run pyinstaller --onefile --windowed --collect-submodules=pydicom --add-data="./src/MaskRegistration/loading.gif:." --noconsole src/MaskRegistration/MaskRegistrationGUI.py --noconfirm
