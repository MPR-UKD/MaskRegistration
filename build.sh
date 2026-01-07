#!/bin/bash

# PyInstaller for onefile CLI (Windows)
uv run pyinstaller --onefile --windowed --collect-submodules=pydicom --add-data="./src/MaskRegistration/loading.gif;." --noconsole src/MaskRegistration/MaskRegistration.py --noconfirm

# PyInstaller for onefile GUI (Windows)
uv run pyinstaller --onefile --windowed --collect-submodules=pydicom --add-data="./src/MaskRegistration/loading.gif;." --noconsole src/MaskRegistration/MaskRegistrationGUI.py --noconfirm
