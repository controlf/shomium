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

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
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
from os.path import *
from subprocess import PIPE, Popen
import sqlite3
import PIL
import struct
from struct import unpack
from io import BytesIO
import base64

from src import ktx_2_png

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
                b'\xABKTX 11\xBB': ['ktx', 'image'],
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


def convert_ktx_to_png(ktx_fp, png_fp):
    try:
        ktx = ktx_2_png.KTXReader()  # init the ktx converter
        ktx_f_bytes = BytesIO(open(ktx_fp, 'rb').read())
        ktx.convert_to_png(ktx_f_bytes, ktx_png_fp)
        return True
    except:
        return False


def convert_img_to_png(img_fp, png_fp):
    # accepts an image file and an output png file
    try:
        # majority of files are supported by Pillow
        i = Image.open(img_fp)
        i.save(png_fp, format='PNG')
        return
    except:
        pass

    try:
        with open(img_fp, 'rb') as f:
            if b'\xABKTX 11\xBB' in f.read(20):  # KTX file
                if convert_ktx_to_png(img_fp, png_fp):
                    return
    except:
        pass
        
    # if all goes wrong, its not supported for conversion, 
    # return a blank PNG to show
    shutil.copy(resource_path('blank_jpeg.png'), png_fp)
    return


def copy_files(files, from_dir, to_dir):
    for file in files:
        try:
            if isfile(pj(from_dir, file)):
                shutil.copy(pj(from_dir, file), to_dir)
        except:
            print(file)


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
    if img_fp:
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


def button_config(widg, icon_fn, icon_width_height=14, widg_width=20, widg_height=20):
    # universal configuration of button widgets
    widg.setIcon(QIcon(resource_path(icon_fn)))
    widg.setIconSize(QSize(icon_width_height, icon_width_height))
    widg.setFixedWidth(widg_width)
    widg.setFixedHeight(widg_height)
    

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


class SelectOS(QDialog):
    def __init__(self):
        super(SelectOS, self).__init__()
        self.os = None
        self.setFixedSize(180, 150)
        self.get_os()

        layout = QVBoxLayout()
        layout.addWidget(self.gb)
        self.setLayout(layout)

        self.setWindowTitle("            Select OS")
        self.setWindowIcon(QIcon(resource_path("controlF.ico")))

    def set_os(self, os):
        self.os = os
        self.accept()

    def return_os(self):
        return self.os

    def get_os(self):
        self.gb = QGroupBox("")
        self.layout = QGridLayout()

        android_pic_btn = CustomQPushButton()
        button_config(android_pic_btn, 'android.png', icon_width_height=25, widg_width=35, widg_height=35)
        self.layout.addWidget(android_pic_btn,      1, 0, 1, 1, alignment=Qt.AlignLeft)
        android_pic_btn.clicked.connect(lambda: self.set_os('Android'))
        android_pic_btn.setToolTip('Android')

        ios_pic_btn = CustomQPushButton()
        button_config(ios_pic_btn, 'apple.ico', icon_width_height=25, widg_width=35, widg_height=35)
        self.layout.addWidget(ios_pic_btn,          1, 2, 1, 1, alignment=Qt.AlignRight)
        ios_pic_btn.clicked.connect(lambda: self.set_os('iOS'))
        ios_pic_btn.setToolTip('iOS')

        self.gb.setLayout(self.layout)


# custom style for our custom progress bar
progress_bar_style = ("""
        QProgressBar{
            border: 1px solid #2E0903;
            border-radius: 5px;
            text-align: center
        }
        QProgressBar::chunk {
            background-color: #D1796B;
            width: 10px;
            margin: 1px;
        }"""
        )

pushbutton_style = ("""
        QPushButton{
            color: #b7baab;
            background-color: #E3E3E3;
            border: 1px solid;
            border-color: #404040;
            font-family: "Consolas";
            font-weight: bold;
        }
        QPushButton:disabled{
            background-color: #404040;
            border-color: #454545;
            color: #454545;
        }
        QPushButton:focus {
            background-color: #E3E3E3;
            border-color: #333333;
            color: #ffe0b3;
        }
        QPushButton:pressed{
            color: #ffe0b3;
            background-color: #E3E3E3;
            border-color: #333333;
            font-family: "Consolas";
        }"""
        )

# custom style for our custom text editor
textedit_style = ("""
        QTextEdit {
            border: 1px solid grey;
        }
        QTextEdit:focus {
            border: 1px solid grey;
        }"""
        )

# tableview style
table_view_style = ("""
        QTableView {
            gridline-color: black;
            border-color: black;
        }
        QHeaderView::section{
            background-color: #606060;
            font-weight:700;
            color: #F2F5F0;
            border: 1px transparent #262626;
        }
        QTableCornerButton::section 
        {
            background-color: #606060;
            border: 1px transparent #606060;
        }       
        QTableView::item:selected{
            border: 2px solid grey;
            background: grey;
        }
        QScrollBar:horizontal{
            height: 15px;
            margin: 3px 15px 3px 15px;
            border: 1px transparent #2A2929;
            border-radius: 4px;
            background-color: light grey;
        }
        QScrollBar::handle:horizontal{
            background-color: #605F5F;
            min-width: 5px;
            border-radius: 4px;
        }
        QScrollBar::add-line:horizontal{
            margin: 0px 3px 0px 3px;
            border-image: url(:/qss_icons/rc/right_arrow_disabled.png);
            width: 10px;
            height: 10px;
            subcontrol-position: right;
            subcontrol-origin: margin;
        }
        QScrollBar::sub-line:horizontal{
            margin: 0px 3px 0px 3px;
            border-image: url(:/qss_icons/rc/left_arrow_disabled.png);
            height: 7px;
            width: 7px;
            subcontrol-position: left;
            subcontrol-origin: margin;
        }
        QScrollBar::add-line:horizontal:hover,QScrollBar::add-line:horizontal:on{
            border-image: url(:/qss_icons/rc/right_arrow.png);
            height: 7px;
            width: 7px;
            subcontrol-position: right;
            subcontrol-origin: margin;
        }
        QScrollBar::sub-line:horizontal:hover, QScrollBar::sub-line:horizontal:on{
            border-image: url(:/qss_icons/rc/left_arrow.png);
            height: 7px;
            width: 7px;
            subcontrol-position: left;
            subcontrol-origin: margin;
        }
        QScrollBar::up-arrow:horizontal, QScrollBar::down-arrow:horizontal{
            background: none;
        }
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal{
            background: none;
        }
        QScrollBar:vertical{
            background-color: light grey;
            width: 15px;
            margin: 15px 3px 15px 3px;
            border: 1px transparent #2A2929;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical{
            background-color: #605F5F;
            min-height: 5px;
            border-radius: 4px;
        }
        QScrollBar::sub-line:vertical{
            margin: 3px 0px 3px 0px;
            border-image: url(:/qss_icons/rc/up_arrow_disabled.png);
            height: 10px;
            width: 10px;
            subcontrol-position: top;
            subcontrol-origin: margin;
        }
        QScrollBar::add-line:vertical{
            margin: 3px 0px 3px 0px;
            border-image: url(:/qss_icons/rc/down_arrow_disabled.png);
            height: 10px;
            width: 10px;
            subcontrol-position: bottom;
            subcontrol-origin: margin;
        }
        QScrollBar::sub-line:vertical:hover,QScrollBar::sub-line:vertical:on{
            border-image: url(:/qss_icons/rc/up_arrow.png);
            height: 10px;
            width: 10px;
            subcontrol-position: top;
            subcontrol-origin: margin;
        }
        QScrollBar::add-line:vertical:hover, QScrollBar::add-line:vertical:on{
            border-image: url(:/qss_icons/rc/down_arrow.png);
            height: 10px;
            width: 10px;
            subcontrol-position: bottom;
            subcontrol-origin: margin;
        }
        QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical{
            background: none;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical{
            background: none;
        }"""
        )


treeview_style = (
        """
        QTreeView::item:hover {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #DBBEE4, stop: 1 #E9967A);
            color: #333333;
            border: 1px solid #DBBEE4;
        }
        QTreeView::item:selected {
            border: 1px solid #E9967A;
        }
        QTreeView::item:selected:active{
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #DBBEE4, stop: 1 #E9967A);
        }
        QTreeView::item:selected:!active {
            background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #DBBEE4, stop: 1 #E9967A);
        }
        """
        )

# custom PyQt5 widgets
class CustomQTreeView(QTreeView):
    def __init__(self, parent=None):
        QTreeView.__init__(self, parent)
        self.setStyleSheet(treeview_style)

class CustomProgressBar(QProgressBar):
    def __init__(self, parent=None):
        QProgressBar.__init__(self, parent)
        self.setFixedHeight(15)
        self.setStyleSheet(progress_bar_style)

class CustomTextEdit(QTextEdit):
    def __init__(self, parent=None):
        QTextEdit.__init__(self, parent)
        self.setStyleSheet(textedit_style)

class CustomQTableView(QTableView):
    def __init__(self, parent=None):
        QTableView.__init__(self, parent)
        self.setStyleSheet(table_view_style)

class CustomQPushButton(QPushButton):
    def __init__(self, parent=None):
        QPushButton.__init__(self, parent)
        self.setStyleSheet(pushbutton_style)



class AboutShomium(QDialog):
    def __init__(self, copyright_txt):
        super(AboutShomium, self).__init__()
        self.setStyleSheet("background-color: white;")
        self.setFixedSize(400, 400)
        self.copyright_txt = open(copyright_txt, 'r').read()
        self.about_info()

        layout = QVBoxLayout()
        layout.addWidget(self.gb)
        self.setLayout(layout)

        self.setWindowTitle("About")
        self.setWindowIcon(QIcon(resource_path("controlF.ico")))

    def about_info(self):
        self.gb = QGroupBox("")
        self.layout = QGridLayout()

        self.instructions = CustomTextEdit()
        self.instructions.setReadOnly(True)
        self.instructions.insertPlainText('Shomium\n\nControl-F \xa9 2022-2023\n\n'
                                          'Author/Contact:   mike.bangham@controlf.co.uk\n\n')
        self.instructions.insertPlainText('{}'
                                          '\n\nThis tool is still under development. If you find a bug or if you '
                                          'have a feature request, please contact:'
                                          '\n\ninfo@controlf.net'.format(self.copyright_txt))
        self.instructions.setStyleSheet('border: 0px;')
        self.layout.addWidget(self.instructions, 0, 0, 1, 1)

        self.gb.setLayout(self.layout)


class HelpShomium(QDialog):
    def __init__(self):
        super(HelpShomium, self).__init__()
        self.setFixedSize(650, 750)
        self.setStyleSheet("background-color: white;")

        self.img_h = 400
        self.img_w = 500

        self.help_box_1()
        self.help_box_2()
        self.help_box_3()

        layout = QVBoxLayout()
        layout.addWidget(self.gb1)
        layout.addWidget(self.gb2)
        layout.addWidget(self.gb3)
        self.setLayout(layout)

        self.setWindowTitle("Help")
        self.setWindowIcon(QIcon(resource_path("controlF.ico")))

    def help_box_1(self):
        self.gb1 = QGroupBox("")
        layout = QGridLayout()

        help_img_1 = QLabel()
        help_img_1_pixmap = QPixmap(
            resource_path('help_1.PNG')).scaled(self.img_h, self.img_w, Qt.KeepAspectRatio,Qt.SmoothTransformation)
        help_img_1.setPixmap(help_img_1_pixmap)
        layout.addWidget(help_img_1, 0, 0, 1, 30, alignment=Qt.AlignLeft)

        help_txt_1 = QLabel()
        help_txt_1.setText(
            'Multiple Extractions\n\n'
            'At any point, you can drag a\n'
            'forensic zip/tar archive into\n'
            'shomium, initialising a new tab.')
        layout.addWidget(help_txt_1, 0, 30, 1, 1, alignment=Qt.AlignLeft)

        self.gb1.setLayout(layout)

    def help_box_2(self):
        self.gb2 = QGroupBox("")
        layout = QGridLayout()

        help_img_2 = QLabel()
        help_img_2_pixmap = QPixmap(
            resource_path('help_2.PNG')).scaled(self.img_h, self.img_w, Qt.KeepAspectRatio,Qt.SmoothTransformation)
        help_img_2.setPixmap(help_img_2_pixmap)
        layout.addWidget(help_img_2, 1, 0, 1, 30, alignment=Qt.AlignLeft)

        help_txt_2 = QLabel()
        help_txt_2.setText(
            'Reports\n\n'
            'Use the report buttons found\n'
            'at the foot of each packages\n'
            'web artefact tab display to\n'
            'export data')
        layout.addWidget(help_txt_2, 1, 30, 1, 1, alignment=Qt.AlignLeft)

        self.gb2.setLayout(layout)

    def help_box_3(self):
        self.gb3 = QGroupBox("")
        layout = QGridLayout()

        help_img_3 = QLabel()
        help_img_3_pixmap = QPixmap(
            resource_path('help_3.PNG')).scaled(self.img_h, self.img_w, Qt.KeepAspectRatio,Qt.SmoothTransformation)
        help_img_3.setPixmap(help_img_3_pixmap)
        layout.addWidget(help_img_3, 2, 0, 1, 30, alignment=Qt.AlignLeft)

        help_txt_3 = QLabel()
        help_txt_3.setText(
            'Search/Filter\n\n'
            'Provide a keyword and see the\n'
            'data filter in realtime with each\n'
            'letter added.')
        layout.addWidget(help_txt_3, 2, 30, 1, 1, alignment=Qt.AlignLeft)

        self.gb3.setLayout(layout)