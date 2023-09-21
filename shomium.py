#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
MIT License

Shomium

Copyright (c) 2022-2023 Control-F Ltd

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

__description__ = 'Control-F - shomium - Application Web Parser'
__contact__ = 'mike.bangham@controlf.co.uk'

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
import os
from os.path import *
from os.path import join as pj
from datetime import datetime
import logging
import sys
from time import strftime
import platform
import tarfile
import zipfile
import time
from io import BytesIO
import requests
import webbrowser
import astc_decomp
import liblzfse

from src import (
    extract_archive, ios_app_mapper, shomium_funcs, save_dialog, report_builder, 
    image_delegate, pandas_model, utils, ktx_2_png)

if hasattr(Qt, 'AA_EnableHighDpiScaling'):
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)

if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

# global removal of the help button in Dialogs
QApplication.setAttribute(Qt.AA_DisableWindowContextHelpButton);

# Some initial variables
start_dir = os.getcwd()
__version__ = open(utils.resource_path('version.txt'), 'r').readlines()[0]
app_data_dir = os.getenv('APPDATA')
temp_output_dir = abspath(pj(app_data_dir, 'CF_SHOMIUM', 'temp'))
os.makedirs(temp_output_dir, exist_ok=True)
log_file_fp = pj(dirname(temp_output_dir), 'logs.txt')
font = QFont('Consolas', 8, QFont.Light)
font.setKerning(True)
font.setFixedPitch(True)
updates_available = [False, '']

# dictionary to store the relative paths for the required archive members.
archive_paths = {'Android': {'key_dir': 'data',
                             'paths': [utils.clean_path(pj('HTTP Cache', 'Cache_Data')),
                                       utils.clean_path(pj('app_webview', 'Default')),
                                       utils.clean_path(pj('Local Storage', 'leveldb')),
                                       'cache']},
                 'iOS': {'key_dir': 'private',
                         'paths': [utils.clean_path(pj('var', 'containers')),
                                   utils.clean_path(pj('mobile', 'Containers'))]}}


def init_log():
    # init log file
    logging.basicConfig(
        filename=log_file_fp, level=logging.DEBUG, 
        format='%(asctime)s | %(levelname)s | %(message)s', filemode='a')
    logging.info('{0} Control-F   Shomium   v.{1} {0}'.format('{}'.format('#'*20), __version__))
    logging.info('Program start')
    logging.debug('System: {}'.format(sys.platform))
    logging.debug('Version: {}'.format(sys.version))
    logging.debug('Host: {}'.format(platform.node()))
    logging.info('Working directory: {}'.format(temp_output_dir))


def check_for_updates():
    # checks if any updates on GitHub - will be displayed at the head of the app window
    global updates_available
    try:
        response = requests.get("https://api.github.com/repos/controlf/shomium/releases/latest")
        latest = response.json()['name']
        if latest == 'v{}'.format(__version__):
            pass
        else:
            updates_available = [
                True, '{} update available - https://github.com/controlf/shomium'.format(latest)]
    except:
        updates_available = [False, 'Offline - Check for updates (https://github.com/controlf/shomium)']


class GUI(QMainWindow):
    '''
    Interactive (drag-and-drop) window. Spawns tabs following a successful 
    ingest of a forensic archive
    '''
    def __init__(self, parent=None):
        super().__init__(parent)
        
        init_log()
        check_for_updates()
        self.setStyleSheet("background-color: white;")

        self.setWindowTitle('Shomium   v{}     {}'.format(__version__, updates_available[1]))
        self.setWindowIcon(QIcon(utils.resource_path('controlF.ico')))
        self.setMinimumSize(800, 800)
        window_widget = QWidget(self)
        self.setCentralWidget(window_widget)

        self.center()  # center the window
        self.create_menu()
        self._createTabs()

        self.statusbar = self.statusBar()
        self.statusbar.showMessage('Drag an Android/iOS file system archive into Shomium!')
        self.setAcceptDrops(True)

        self.hbox = QHBoxLayout()
        self.hbox.setSpacing(5)
        self.hbox.setContentsMargins(2, 2, 2, 2)
        window_widget.setLayout(self.hbox)
        self.hbox.addWidget(self.tabs)

        # clean up old data
        self.init_clean_temp()

    def init_clean_temp(self):
        # A quick thread to clean up the temp directory
        self.clean_thread = utils.CleanTemp()
        self.clean_thread.start()

    def center(self):
        self.setGeometry(
            QStyle.alignedRect(Qt.LeftToRight, Qt.AlignCenter, 
                self.size(), qApp.desktop().availableGeometry(),))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls:
            e.accept()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls:
            e.accept()
        else:
            e.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls:
            event.setDropAction(Qt.CopyAction)
            event.accept()
            self.fnames = []
            for url in event.mimeData().urls():
                self.fnames.append(str(url.toLocalFile()))
            for f in self.fnames:
                self._load(f)
        else:
            event.ignore()

    def _load(self, archive):
        # the loader. Checks the input file dragged is a zip/tar archive
        archive_type = None
        if isfile(archive):
            if zipfile.is_zipfile(archive):
                archive_type = 'zip'
            elif tarfile.is_tarfile(archive):
                archive_type = 'tar'
            else:
                utils.display_message('\n[!] File is not a zip/tar archive')

        if archive_type:
            self.statusbar.showMessage('Dragged {}...'.format(archive))
            diag = utils.SelectOS()  # spawn a dialog to fetch the OS
            diag.exec_()
            if diag.return_os():
                os = diag.return_os()
                if os == 'Android':
                    tab_icon = QIcon(utils.resource_path('android_2.ico'))
                    tab_idx = self.tabs.addTab(
                        ArchiveTab(
                            self, archive, archive_type, os), tab_icon, ' {} '.format(basename(archive)))
                else:
                    tab_icon = QIcon(utils.resource_path('apple.ico'))
                    tab_idx = self.tabs.addTab(
                        ArchiveTab(
                            self, archive, archive_type, os), tab_icon, ' {} '.format(basename(archive)))

                self.tabs.setCurrentIndex(tab_idx)

    def _createTabs(self):
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.tabCloseRequested.connect(self._close_archive_tab)

    def _close_archive_tab(self, index):
        tab = self.tabs.widget(index)
        tab.deleteLater()
        self.tabs.removeTab(index)

    def create_menu(self):
        self.file_menu = self.menuBar().addMenu("&File")
        self.file_menu.addAction(
            '&Open Temp', lambda: webbrowser.open(temp_output_dir))
        self.file_menu.addAction(
            '&Open Logs', lambda: webbrowser.open(pj(dirname(temp_output_dir), 'logs.txt')))

        self.help_menu = self.menuBar().addMenu("&Help")
        self.help_menu.addAction(
            '&Help', lambda: utils.HelpShomium().exec_())
        self.help_menu.addAction(
            '&About', lambda: utils.AboutShomium(utils.resource_path('copyright.txt')).exec_())

class TreeItem(object):
    def __init__(self, pkg):
        self.package = pkg


class ArchiveTab(QWidget):
    '''
    Root tab for an ingested archive extraction
    '''
    def __init__(self, maingui, archive, archive_type, os):
        super().__init__(maingui)
        self.maingui = maingui
        self.archive = archive
        self.archive_type = archive_type
        self.oem = os
        self.archive_paths = archive_paths  # make a copy for working on

        self._init_tabs()

        control_f_emblem = QLabel()
        emblem_pixmap = QPixmap(
            utils.resource_path('ControlF_R_RGB.png')).scaled(
            300, 300, Qt.KeepAspectRatio,Qt.SmoothTransformation)
        control_f_emblem.setPixmap(emblem_pixmap)

        self.progress_bar = utils.CustomProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()

        # incase the filename is massive
        if len(basename(self.archive)) > 60:
            fn = '{}...'.format(basename(self.archive)[60:])
        else:
            fn = basename(self.archive)
        self.archive_details = utils.CustomTextEdit()
        self.archive_details.setFont(font)
        self.archive_details.setReadOnly(True)
        self.archive_details.setFixedWidth(460)
        self.archive_details.setFixedHeight(40)
        self.archive_details.insertPlainText('Archive:\t{}\nOS:\t{}'.format(fn, self.oem))

        self._maingrid = QGridLayout()
        self._maingrid.setContentsMargins(5, 5, 5, 5)
        self._maingrid.addWidget(self.archive_details,          0, 0, 1, 1, alignment=Qt.AlignLeft)
        self._maingrid.addWidget(self.application_tree_view(),  1, 0, 1, 1, alignment=Qt.AlignLeft)
        self._maingrid.addWidget(self.log_widget(),             2, 0, 1, 1, alignment=Qt.AlignLeft)
        self._maingrid.addWidget(self.tabs,                     0, 1, 4, 4)
        self._maingrid.addWidget(control_f_emblem,              3, 0, 2, 1)
        self._maingrid.addWidget(self.progress_bar,             5, 1, 1, 4, alignment=Qt.AlignBottom)
        self.setLayout(self._maingrid)

        # start parsing our archive
        self.maingui.statusbar.showMessage('Parsing and extracting {}. . .'.format(self.archive))
        self._init_archive_parser()

        if self.oem == 'iOS':
            self.maingui.statusbar.showMessage('Mapping iOS GUIDs to their package names. . .')
            # iOS requires the GUID's to be mapped to their package
            self.guid_dict = self.ios_guid_mapper()
            for app, guid_list in self.guid_dict.items():
                archive_paths[self.oem]['paths'].extend(guid_list)

        self.maingui.statusbar.showMessage('Idle')

    def application_tree_view(self):
        groupbox = QGroupBox()
        groupbox.setFont(QFont("Arial", weight=QFont.Bold))
        self.tree_layout = QGridLayout()
        self.tree_layout.setContentsMargins(0, 0, 0, 0)

        self.app_view = utils.CustomQTreeView()
        self.app_view.setHeaderHidden(True)
        self.app_view.setUniformRowHeights(True)
        self.app_view.setRootIsDecorated(False)
        self.treemodel = QStandardItemModel()
        self.app_view.setModel(self.treemodel)
        self.app_view.setAlternatingRowColors(True)
        self.app_view.setFont(font)
        self.tree_layout.addWidget(self.app_view, 0, 0, 1, 1)
        self.app_view.setFixedWidth(460)

        # enable selection of rows
        self.app_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # prevent editing of objects in tree
        self.app_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # create trigger when an object is selected
        self.app_view.clicked.connect(self.app_view_clicked)

        groupbox.setLayout(self.tree_layout)
        return groupbox

    def app_view_clicked(self, idx):
        obj = idx.data(Qt.UserRole)
        package_name = obj.package
        if self.package_dict[package_name]['oem'] == 'android':
            self._add_tab(
                PackageTab, [self.package_dict, package_name, self.report_output_dir], package_name)
        else:
            self.package_dict['guid_dict'] = self.guid_dict
            self._add_tab(
                PackageTab, [self.package_dict, package_name, self.report_output_dir], package_name)

    def _finished_archive_extraction(self, out):
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        self.package_dict = self.build_package_dict(out[0])
        # add items to treeview
        self.add_log('Found {} Packages (single click a package)'.format(len(self.package_dict.keys())))
        for count, (package, files) in enumerate(self.package_dict.items()):
            obj = TreeItem(package)  # create an object for the item
            item = QStandardItem()
            item.setData(obj, role=Qt.UserRole)   #so we can add an icon and text
            item.setText(package)
            #item.setIcon(QIcon(package_icon))  # TO DO - package_icon - recover app icons for displaying
            self.treemodel.appendRow(item)

    def _init_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Ignored)
        self.tabs.tabCloseRequested.connect(self._close_tab)

    def _add_tab(self, func, args, tab_name):
        if not self.findChild(QWidget, tab_name):
            self.tabs.addTab(func(self, *args), tab_name)
        else:
            self.add_log('{} already open'.format(tab_name))
        self.tabs.setCurrentWidget(self.findChild(QWidget, tab_name))

    def _close_tab(self, index):
        tab = self.tabs.widget(index)
        tab.deleteLater()
        self.tabs.removeTab(index)

    def _progress_archive_extraction(self, objects):
        val, txt = objects
        if val:
            self.progress_bar.setValue(val)
        if txt:
            self.add_log(txt)

    def _init_archive_parser(self):
        self.progress_bar.show()
        self.report_output_dir = pj(temp_output_dir, 'dump_{}'.format(int(time.time())))

        self._extract_archive_thread = extract_archive.ExtractArchiveThread(
                                                            self,
                                                            archive_paths[self.oem]['paths'],
                                                            self.report_output_dir,
                                                            self.archive,
                                                            self.archive_type,
                                                            key_dir=archive_paths[self.oem]['key_dir'])

        self._extract_archive_thread.progressSignal.connect(self._progress_archive_extraction)
        self._extract_archive_thread.finishedSignal.connect(self._finished_archive_extraction)
        self._extract_archive_thread.start()

    def build_package_dict(self, archive_files):
        self.add_log('Building package list...')
        package_dict = dict()
        if self.oem == 'Android':
            for file in archive_files:
                rel_path = file.split('data\\data\\', 1)
                if len(rel_path) > 1:
                    rel_path = rel_path[-1]
                    package_name = rel_path.split('\\')[0]
                    if package_name not in package_dict:
                        package_dict[package_name] = dict()
                        package_dict[package_name]['rel_path'] = list()
                        package_dict[package_name]['oem'] = 'android'
                    package_dict[package_name]['rel_path'].append(rel_path)

        else:
            for filepath in archive_files:
                for package_name, guid_list in self.guid_dict.items():
                    if any(guid in filepath for guid in guid_list):
                        if package_name not in package_dict:
                            package_dict[package_name] = dict()
                            package_dict[package_name]['rel_path'] = list()
                            package_dict[package_name]['oem'] = 'ios'
                        # all container data will be held under private\var\..., 
                        # so let's slice this off

                        rel_path = filepath.split(self.report_output_dir, 1)[1]
                        package_dict[package_name]['rel_path'].append(rel_path)

        return package_dict

    def ios_guid_mapper(self):
        # attempts to map all GUIDs to their package
        self.add_log("Resolving package GUID's and mapping the FS...")
        np = ios_app_mapper.NameParser(self.archive, self.archive_type, 'df')
        df_native_apps, df_3rd_party = np.parse()

        guid_dict = dict()
        if not df_3rd_party.empty:
            app_dict = df_3rd_party.set_index('App Name').to_dict('index')
            # Get all GUIDs relating to a 3rd app
            for app, details in app_dict.items():
                guid_dict[app] = list()
                guid_dict[app].append(app_dict[app]['GUID'])
                for app_meta, metadata in app_dict[app]['MetaData'].items():
                    guid_dict[app].append(app_meta)

        # Lets get Safari out of the native apps dataframe
        if not df_native_apps.empty:
            app_dict = {k: g.to_dict(orient='records') for k, g in df_native_apps.groupby(level=0)}
            if app_dict:
                guid_dict['com.apple.mobilesafari'] = list()
                for index, app_records in app_dict.items():
                    if 'safari' in app_records[0]['App Name']:
                        guid_dict['com.apple.mobilesafari'].append(app_records[0]['GUID'])

        self.add_log("Finished mapping!")
        return guid_dict

    def add_log(self, txt):
        dt = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.log_tb.insertPlainText('[{}] {}\n'.format(dt, txt))
        self.log_tb.moveCursor(QTextCursor.End)

    def update_progress_bar(self, v):
        self.progress_bar.setValue(v)

    def log_widget(self):
        groupbox = QGroupBox()
        groupbox.setFont(QFont("Arial", weight=QFont.Bold))
        self.log_display_layout = QGridLayout()
        self.log_display_layout.setContentsMargins(0, 0, 0, 0)

        self.log_tb = utils.CustomTextEdit()
        self.log_tb.setFixedWidth(460)
        self.log_display_layout.addWidget(self.log_tb, 0, 0, 1, 1)
        self.log_tb.setFont(font)

        groupbox.setLayout(self.log_display_layout)
        return groupbox


class PackageTab(QWidget):
    '''
    Displays the tabs for each artefact that was found for a package
    '''
    def __init__(self, maingui, package_dict, package, output_dir, parent=None):
        super().__init__(parent)
        self.setObjectName(package)
        self.maingui = maingui
        self.package = package
        self._init_tabs()

        self.pkg_progress_bar = utils.CustomProgressBar()
        self.pkg_progress_bar.setMaximum(100)
        self.pkg_progress_bar.setValue(0)
        self.pkg_progress_bar.hide()

        self.package_grid = QGridLayout()
        self.package_grid.setContentsMargins(1, 1, 1, 1)
        self.package_grid.addWidget(self._tabs, 0, 0, 99, 1)
        self.package_grid.addWidget(self.pkg_progress_bar, 101, 0, 1, 1, alignment=Qt.AlignBottom)
        if package_dict[package]['oem'] == 'android':
            self.android_package_tab(package_dict, package, output_dir)
        else:
            self.ios_package_tab(package_dict, package, output_dir)
        self.setLayout(self.package_grid)

    def _init_tabs(self):
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(False)
        self._tabs.setMovable(True)
        self._tabs.setDocumentMode(True)
        self._tabs.setElideMode(Qt.ElideRight)
        self._tabs.setUsesScrollButtons(True)
        self._tabs.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Ignored)
        self._tabs.tabCloseRequested.connect(self.close_tab)

    def close_tab(self, index):
        tab = self._tabs.widget(index)
        tab.deleteLater()
        self._tabs.removeTab(index)

    def update_pkg_progress_bar(self, v):
        self.pkg_progress_bar.setValue(v)

    def android_package_tab(self, package_dict, package, output_dir):
        self.pkg_progress_bar.show()
        thread_ = shomium_funcs.AndroidThread(package_dict[package]['rel_path'], output_dir, package)
        thread_.progressSignal.connect(self._progress_df_generation)
        thread_.finishedSignal.connect(self._finished_df_generation)
        thread_.start()

    def ios_package_tab(self, package_dict, package, output_dir):
        self.pkg_progress_bar.show()
        thread_ = shomium_funcs.IOSThread(
            package_dict[package]['rel_path'], package_dict['guid_dict'][package], output_dir, package)
        thread_.progressSignal.connect(self._progress_df_generation)
        thread_.finishedSignal.connect(self._finished_df_generation)
        thread_.start()

    def _progress_df_generation(self, objects):
        val, text, result = objects
        if val:
            self.update_pkg_progress_bar(val)
        if text:
            self.maingui.add_log(text)
        if result:
            df = result[0]
            if not df.empty:
                package_files, report_name, output_dir, package, webview_item = result[1:]
                tab_widget = QWidget()
                _grid = QGridLayout()
                _grid.setContentsMargins(1, 1, 1, 1)
                _grid.addWidget(
                    DisplayTab(self, df, package_files, report_name, output_dir, webview_item), 
                    1, 0, 1, 1)
                tab_widget.setLayout(_grid)
                self._tabs.addTab(tab_widget, webview_item)

    def _finished_df_generation(self, s):
        self.update_pkg_progress_bar(0)
        self.pkg_progress_bar.hide()


class DisplayTab(QWidget):
    '''
    Each tab shows a dataframe of the recovered artefact data
    '''
    def __init__(self, *args, parent=None):
        super().__init__(parent)
        (self.package_main, self.df, self.package_files, 
            self.report_name, self.output_dir, self.webview_item) = args

        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        if 'media' in self.df.columns:
            self.organise_columns()

        self.tableview = utils.CustomQTableView()
        # Set our model to incorporate a dataframe
        model = pandas_model.ModelDataFrame(self.df)

        # set our proxy so that we can use a search function on our tableview
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(model)
        self.tableview.setModel(self.proxy)

        # customise our tableview so that it looks pretty and behaves as we expect it to
        self.tableview.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.tableview.setAlternatingRowColors(True)
        self.tableview.horizontalHeader().setMaximumSectionSize(300)
        self.tableview.resizeColumnsToContents()
        self.tableview.horizontalHeader().setStretchLastSection(True)

        self.tableview.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tableview.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tableview.resizeRowsToContents()

        if not self.df.empty:
            # DisplayTab will accept a dataframe without a media column, but if 'has_media' 
            # is True, the df must contain a media column.
            if 'media' in self.df.columns:
                self.has_media = True
                col_idx = self.df.columns.values.tolist().index('media')
                self.tableview.setItemDelegateForColumn(
                    col_idx, image_delegate.ImageDelegate(self.tableview))
            else:
                self.has_media = False

        self.tableview.resizeRowsToContents()
        layout.addWidget(self.tableview, 0, 0, 1, 100)

        if not self.df.empty:
            # The report widgets
            self.dump_to_html_btn = utils.CustomQPushButton()
            utils.button_config(self.dump_to_html_btn, 'html.png', icon_width_height=30, widg_width=35, widg_height=35)
            self.dump_to_html_btn.clicked.connect(lambda: self._init_report_thread('html', self.df))
            layout.addWidget(self.dump_to_html_btn,         1, 0, 1, 1)
            self.dump_to_html_btn.setToolTip('Export {} data to a HTML report'.format(self.webview_item))

            self.dump_to_xlsx_btn = utils.CustomQPushButton()
            utils.button_config(self.dump_to_xlsx_btn, 'xlsx.png', icon_width_height=30, widg_width=35, widg_height=35)
            self.dump_to_xlsx_btn.clicked.connect(lambda: self._init_report_thread('xlsx', self.df))
            layout.addWidget(self.dump_to_xlsx_btn,         1, 1, 1, 1)
            self.dump_to_xlsx_btn.setToolTip('Export {} data to a XLSX report'.format(self.webview_item))

            self.search_lbl = QLabel('Search')
            self.search_lbl.setToolTip('Search/Filter {} data for a keyword'.format(self.webview_item))
            self.search_lbl.setFont(QFont("Arial", weight=QFont.Bold))
            layout.addWidget(self.search_lbl, 1, 4, 1, 1)
            self.search_input = QLineEdit()
            self.search_input.setFixedWidth(250)
            layout.addWidget(self.search_input, 1, 5, 1, 10)
            self.search_input.textChanged.connect(self.search_input_changed)
            self.search_input.setToolTip('Search/Filter {} data for a keyword'.format(self.webview_item))

            self.report_progress_bar = utils.CustomProgressBar()
            self.report_progress_bar.setMaximum(100)
            self.report_progress_bar.setValue(0)
            self.report_progress_bar.hide()
            layout.addWidget(self.report_progress_bar,      1, 19, 1, 80)

        self.setLayout(layout)

    def organise_columns(self):
        # organises so that 'media' is always the first column
        col_headers = self.df.columns.values.tolist()
        col_headers.remove('media')
        col_headers.insert(0, "media")
        self.df = self.df[col_headers]

    @pyqtSlot(str)
    def search_input_changed(self, text):
        search = QRegExp(text, Qt.CaseInsensitive, QRegExp.RegExp)
        self.proxy.setFilterRegExp(search)
        self.proxy.setFilterKeyColumn(-1)  # search all columns

    def _thread_progress(self, v):
        self.report_progress_bar.setValue(v)

    def _thread_status(self, s):
        self.package_main.maingui.add_log(s)

    def _thread_complete(self, report_dir):
        webbrowser.open(report_dir)
        self.report_progress_bar.setValue(0)
        self.report_progress_bar.hide()

    def _init_report_thread(self, report_type, df):
        sd = save_dialog.SaveDialog(self.webview_item, report_type)
        rc = sd.exec_()
        if rc == 1:
            save_details = sd.get_value_dict()

            dt = '{}_{}'.format(strftime('%d%m%y'), strftime('%H%M%S'))
            report_name = '{} Report'.format(self.webview_item)
            report_sub_dir = '{}_{}_{}'.format(report_type, self.webview_item, dt)
            os.makedirs(pj(save_details['save_dir'], report_sub_dir), exist_ok=True)

            self.report_progress_bar.show()
            out_fp = pj(save_details['save_dir'], report_sub_dir,
                        '{} Report {}.{}'.format(self.webview_item, dt, report_type))
            if report_type == 'xlsx':
                self._thread = report_builder.XLSXReportThread(
                        report_name, out_fp, df, save_details, self.has_media, self.output_dir)

            else:
                self._thread = report_builder.HTMLReportThread(
                        report_name, out_fp, df, save_details, self.has_media, self.output_dir)
            self._thread.statusSignal.connect(self._thread_status)
            self._thread.progressSignal.connect(self._thread_progress)
            self._thread.finishedSignal.connect(self._thread_complete)
            self._thread.start()


def main():
    app = QApplication(sys.argv)
    ex = GUI()
    ex.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
