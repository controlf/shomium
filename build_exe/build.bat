@echo off
echo -------------------------------------------
echo Control-F 2022 - Binary Concat
echo -------------------------------------------
echo Due to Github file size restrictions, the executable for this program has been broken into chunks. This script will rebuild the executable from the chunks found in the build_exe directory (in order).
echo -------------------------------------------
COPY /B shomium.0 + shomium.1 + shomium.2 + shomium.3 + shomium.4 shomium.exe
echo -------------------------------------------
echo Finished!