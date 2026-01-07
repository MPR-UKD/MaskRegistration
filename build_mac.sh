#!/bin/bash

# PyInstaller for onefile CLI
poetry run pyinstaller --onefile --windowed --collect-submodules=pydicom --add-data="./src/MaskRegistration/loading.gif:."  --noconsole src/MaskRegistration/MaskRegistration.py --noconfirm

#zip -r dist/MaskRegistration_mac.zip dist/MaskRegistration.app