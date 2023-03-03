#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
MIT License

Shomium

Copyright (c) 2022 Control-F Ltd

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

import json
import filetype
import shutil
import numpy as np
import pandas as pd
import cv2
from collections import namedtuple
import sys
import os
from os.path import join as pj
from os.path import isdir, isfile, basename, dirname, abspath, exists
from subprocess import PIPE, Popen
from PyQt5.QtCore import QThread
import sqlite3
import PIL
import struct
from struct import unpack
from io import BytesIO
import base64

start_dir = os.getcwd()
app_data_dir = os.getenv('APPDATA')
temp_output_dir = abspath(pj(app_data_dir, 'CF_SHOMIUM', 'temp'))


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = pj(abspath("."), 'res')
    return pj(base_path, relative_path)


file_headers = {b'\xFF\xD8\xFF': ['jpeg', 'image'],
                b'\x89PNG\x0D\x0A\x1A\x0A': ['png', 'image'],
                b'GIF': ['gif', 'image'],
                b'BM': ['bmp', 'image'],
                b'\x00\x00\x01\x00': ['ico', 'image'],
                b'\x49\x49\x2A\x00': ['tif', 'image'],
                b'\x4D\x4D\x00\x2A': ['tif', 'image'],
                b'RIFF': ['avi', 'video'],
                b'OggS\x00\x02': ['ogg', 'video'],
                b'ftypf4v\x20': ['f4v', 'video'],
                b'ftypF4V\x20': ['f4v', 'video'],
                b'ftypmmp4': ['3gp', 'video'],
                b'ftyp3g2a': ['3g2', 'video'],
                b'matroska': ['mkv', 'video'],
                b'\x01\x42\xF7\x81\x01\x42\xF2\x81)': ['mkv', 'video'],
                b'moov': ['mov', 'video'],
                b'skip': ['mov', 'video'],
                b'mdat': ['mov', 'video'],
                b'\x00\x00\x00\x14pnot': ['mov', 'video'],
                b'\x00\x00\x00\x08wide)': ['mov', 'video'],
                b'ftypmp41': ['mp4', 'video'],
                b'ftypavc1': ['mp4', 'video'],
                b'ftypMSNV': ['mp4', 'video'],
                b'ftypFACE': ['mp4', 'video'],
                b'ftypmobi': ['mp4', 'video'],
                b'ftypmp42': ['mp4', 'video'],
                b'ftypMP42': ['mp4', 'video'],
                b'ftypdash': ['mp4', 'video'],
                b'\x30\x26\xB2\x75\x8E\x66\xCF\x11\xA6\xD9\x00\xAA\x00\x62\xCE\x6C': ['wmv', 'video'],
                b'4XMVLIST': ['4xm', 'video'],
                b'FLV\x01': ['flv', 'video'],
                b'\x1A\x45\xDF\xA3\x01\x00\x00\x00': ['webm', 'video'],
                b'<!doctype html>': ['html', 'file'],
                b'<!DOCTYPE HTML>': ['html', 'file'],
                b'<?xml version=': ['xml', 'file']}


def get_file_mimetype(header, abs_fp=None):
    for f_head, f_type in file_headers.items():
        if f_head in header:
            return f_type
        else:
            if abs_fp:
                kind = filetype.get_type(abs_fp)
                if kind:
                    return [kind.extension, kind.mime]
    return None


def copy_files(files, from_dir, to_dir):
    for file in files:
        if isfile(pj(from_dir, file)):
            shutil.copy(pj(from_dir, file), to_dir)


class NpEncoder(json.JSONEncoder):
    # converts numpy objects so they can be serialised
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)


def get_image_type(img_fp):
    file_typ, file_ext = None, None
    kind = filetype.guess(img_fp)
    if kind is None:
        with open(img_fp, 'rb') as bf:
            line = bf.read(50)
            for head, ext in file_headers.items():
                if head in line:
                    file_typ, file_ext = ext
    else:
        file_typ, file_ext = kind.mime, kind.extension
    return file_typ, file_ext


def generate_thumbnail(fp, thmbsize=128):
    file_type, file_ext = get_image_type(fp)

    if file_type and file_ext:
        if file_type.startswith('image'):
            img = PIL.Image.open(fp, 'r')

        elif file_type.startswith('video'):
            try:
                cap = cv2.VideoCapture(fp)
                _, cv2_img = cap.read()
                cv2_img = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB)
                img = PIL.Image.fromarray(cv2_img)
                file_ext = 'JPEG'
            except:
                img = PIL.Image.open(resource_path('blank_jpeg.png'), 'r')
                file_ext = 'PNG'
        else:
            img = PIL.Image.open(resource_path('blank_jpeg.png'), 'r')
            file_ext = 'PNG'

    else:
        img = PIL.Image.open(resource_path('blank_jpeg.png'), 'r')
        file_ext = 'PNG'

    if file_ext == 'jpg':
        file_ext = 'jpeg'

    try:
        hpercent = (int(thmbsize) / float(img.size[1]))
        wsize = int((float(img.size[0]) * float(hpercent)))
        img = img.resize((wsize, int(thmbsize)), PIL.Image.ANTIALIAS)
    except OSError:  # truncated file
        img = PIL.Image.open(resource_path('blank_jpeg.png'), 'r')
        file_ext = 'PNG'
        hpercent = (int(thmbsize) / float(img.size[1]))
        wsize = int((float(img.size[0]) * float(hpercent)))
        img = img.resize((wsize, int(thmbsize)), PIL.Image.ANTIALIAS)

    buf = BytesIO()
    img.save(buf, format=file_ext.upper())
    b64_thumb = base64.b64encode(buf.getvalue()).decode('utf8')

    return b64_thumb


def clean_path(path):
    return path.replace('\\\\', '/').replace('\\', '/')


def replacer(_string):
    incompatible_chars = ":*?<>|"
    for c in incompatible_chars:
        _string = _string.replace(c, '')
    return _string


def unpacker(struct_arg, data, fields=None):
    # Accepts a struct argument, the packed binary data and optional fields.
    if fields:
        # returns a dictionary where the field is the key and the unpacked data is value.
        attr1 = namedtuple('struct', fields)
        return attr1._asdict(attr1._make(unpack(struct_arg, data)))
    else:
        # or just return value of single argument
        try:
            return unpack(struct_arg, data)[0]
        except struct.error:
            return False


def build_dataframe(db, table, index=None, query=None):
    fc_conn = sqlite3.connect(db)
    if query:
        df = pd.read_sql_query(query, fc_conn, index_col=index)
    else:
        df = pd.read_sql_query("SELECT * FROM " + table, fc_conn, index_col=index)
    fc_conn.close()
    return df


class CleanTemp(QThread):
    # Cleans the temporary directory in the background at startup
    def __init__(self):
        QThread.__init__(self, parent=None)
        if exists(temp_output_dir):
            self.temp_dirs = [pj(temp_output_dir, d) for d in os.listdir(temp_output_dir)]

    def power_delete(self, dir_):
        try:
            cmd = ["powershell", "-Command", "Remove-Item", "-LiteralPath", dir_, "-Force", "-Recurse", "-Verbose"]
            Popen(cmd, stdout=PIPE, stderr=PIPE, shell=True)
            return True
        except:
            return False

    def run(self):
        if self.temp_dirs:
            for td in self.temp_dirs:
                for root, dirs, files in os.walk(td, topdown=False):
                    for name in files:
                        try:
                            os.remove(pj(root, name))
                        except:
                            self.power_delete(pj(root, name))
                    for name in dirs:
                        try:
                            os.rmdir(pj(root, name))
                        except:
                            self.power_delete(pj(root, name))

        os.makedirs(temp_output_dir, exist_ok=True)