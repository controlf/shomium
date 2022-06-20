# shomium | Control-F | 2021-2022
# script to concatenate executable binary pieces

import os
from os.path import join as pj
cwd = os.getcwd()

print('Building shomium.exe...')
shomium_chunks = [f for f in os.listdir(cwd) if f.startswith('shomium.')]
with open(pj(cwd, 'shomium.exe'), 'wb+') as shomium_out:
    for shomium_chunk in sorted(shomium_chunks):
        with open(pj(cwd, shomium_chunk), 'rb') as chunk:
            shomium_out.write(chunk.read())
print('Finished!')
