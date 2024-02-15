@echo off
echo -------------------------------------------
echo Control-F 2022 - Binary Concat
echo -------------------------------------------
echo Due to Github file size restrictions, the executable for this program has been broken into chunks. This script will rebuild the executable from the chunks found in the build_exe directory (in order).
echo -------------------------------------------
COPY /B shomium_0 + shomium_1 + shomium_2 + shomium_3 + shomium_4 + shomium_5 + shomium_6 + shomium_7 + shomium_8 + shomium_9 shomium.exe
echo -------------------------------------------
echo Finished!
