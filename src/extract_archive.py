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

from PyQt5.QtCore import pyqtSignal, QThread
import os
from os.path import join as pj
from os.path import basename, abspath, split, dirname
import zipfile
import tarfile
import logging


class ExtractArchiveThread(QThread):
    finishedSignal = pyqtSignal(list)
    progressSignal = pyqtSignal(object)

    def __init__(self, parent, files_to_extract, save_dir, archive, _type, key_dir=None):
        QThread.__init__(self, parent)
        self.files_to_extract = files_to_extract
        self.save_dir = save_dir
        self.archive = archive
        self.type = _type
        self.key_dir = key_dir

    def run(self):
        archive_list = list()

        if self.type == 'zip':
            self.progressSignal.emit([None, 'Archive is zipfile, processing members...'])
            with zipfile.ZipFile(self.archive, 'r') as zip_obj:
                archive_members = zip_obj.namelist()
                archive_count = len(archive_members)
                count = 0
                self.progressSignal.emit([None, 'Archive: {} files. Extracting required files...'.format(archive_count)])
                for archive_member in archive_members:
                    if self.key_dir in archive_member and any(sub_path in archive_member for sub_path in self.files_to_extract):
                        if archive_member.endswith('/'):
                            os.makedirs(self.save_dir+'/'+"".join(i for i in archive_member if i not in ":*?<>|"), exist_ok=True)
                        else:
                            file = abspath(self.save_dir+'/'+"".join(i for i in archive_member if i not in ":*?<>|"))
                            os.makedirs(dirname(file), exist_ok=True)
                            try:
                                with open(file, 'wb') as file_out:
                                    zip_fmem = zip_obj.read(archive_member)
                                    file_out.write(zip_fmem)
                                    archive_list.append(file)
                            except Exception as e:
                                logging.error('Error: {}'.format(e))
                    count += 1
                    self.progressSignal.emit([int(count / archive_count * 100), None])

        else:
            self.progressSignal.emit([None, 'Archive is tarfile, processing members...'])
            with tarfile.open(self.archive, 'r') as tar_obj:
                archive_count = len(tar_obj)
                count = 0
                self.progressSignal.emit([None, 'Archive: {} files. Extracting required files...'.format(archive_count)])
                for member in tar_obj:
                    if self.key_dir in member.name and any(sub_path in member.name for sub_path in self.files_to_extract):
                        if member.isdir():
                            os.makedirs(self.save_dir+'/'+"".join(i for i in archive_member if i not in ":*?<>|"), exist_ok=True)
                        else:
                            file = abspath(self.save_dir+'/'+"".join(i for i in archive_member if i not in ":*?<>|"))
                            os.makedirs(dirname(file), exist_ok=True)
                            try:
                                with open(file, 'wb') as file_out:
                                    tar_fmem = tar_obj.extractfile(member)
                                    file_out.write(tar_fmem.read())
                                    archive_list.append(file)
                            except Exception as e:
                                logging.error('Error: {}'.format(e))
                    count += 1
                    self.progressSignal.emit([int(count / archive_count * 100), None])

        self.progressSignal.emit([100, 'Extracted {} files'.format(len(archive_list))])
        self.finishedSignal.emit([archive_list])
