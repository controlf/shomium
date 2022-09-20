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
from os.path import isfile, abspath, dirname, basename, relpath
import numpy as np
import sqlite3
import re
import pathlib
import pandas as pd
from struct import unpack
import shutil
import logging

from src import ccl_leveldb, crumbs, smidge, utils


def find_meta_block(f):
    # locates the meta data block following the cache image.
    # The signature for the meta block has a 3 random bytes prior to the signature
    pattern = b"\xD8\x41\x0D\x97\x45\x6F\xFA\xF4\x01\x00\x00\x00"  # len of 12
    regex = re.compile(pattern)
    for match_obj in regex.finditer(f):
        offset = match_obj.start()
        return offset


def parse_origin(file):
    # Need to parse the origin file for the records and blobs
    origin = {'protocol': '', 'url': ''}
    with open(file, 'rb') as f:
        for k, v in origin.items():
            length = unpack('<I', f.read(4))[0]
            f.read(1)
            origin[k] = f.read(length).decode()
    return origin


class IOSThread(QThread):
    finishedSignal = pyqtSignal(list)
    progressSignal = pyqtSignal(list)

    def __init__(self, *args):
        QThread.__init__(self, parent=None)
        self.package_files, self.package_guids, self.output_dir, self.package = args
        self.package_files_count = len(self.package_files)
        self.generator_dict = {'Cookies': {'func': self.cookies,
                                           'args': None},
                               'App Cache': {'func': self.app_cache,
                                             'args': None},
                               'Safari History': {'func': self.safari_history,
                                                  'args': None},
                               'Safari Browser Tabs': {'func': self.safari_tabs,
                                                       'args': None},
                               'Network Records-Blobs': {'func': self.blobs_and_records,
                                                         'args': 'NetworkCache'},
                               'Storage Records-Blobs': {'func': self.blobs_and_records,
                                                         'args': 'CacheStorage'}
                               }

    def run(self):
        for webview_item, df_generator in self.generator_dict.items():
            self.progressSignal.emit([0, 'Processing {}...'.format(webview_item), None])
            report_name = 'Shomium - {} - {}'.format(self.package, webview_item)
            if df_generator['args']:
                df = df_generator['func'](df_generator['args'])
            else:
                df = df_generator['func']()
            self.progressSignal.emit([100,
                                      'Finished processing {}...'.format(webview_item),
                                      [df, self.package_files, report_name, self.output_dir,
                                       self.package, webview_item]])
            self.progressSignal.emit([100, '{} - {} ({} rows)'.format(self.package, webview_item, len(df.index)), None])
        self.finishedSignal.emit([])

    def cookies(self):
        count = 0
        for relative_fp in self.package_files:
            abs_fp = abspath(str(self.output_dir) + str(relative_fp))
            if isfile(abs_fp) and 'Cookies.binarycookies' in abs_fp and any(sub_path in abs_fp for
                                                                            sub_path in self.package_guids):
                _, df = crumbs.CookieParser(abs_fp, 'df').process()
                return df
            count += 1
            self.progressSignal.emit([int(count / self.package_files_count * 100), None, None])
        return pd.DataFrame()

    def safari_bookmarks(self):
        count = 0
        for relative_fp in self.package_files:
            abs_fp = abspath(str(self.output_dir) + str(relative_fp))
            if isfile(abs_fp) and 'Library' in abs_fp and abs_fp.endswith('Bookmarks.db') and \
                    any(sub_path in abs_fp for sub_path in self.package_guids):

                query = ("""SELECT
                        title,
                        url,
                        hidden
                        FROM bookmarks""")
                df = utils.build_dataframe(abs_fp, None, query=query)
                return df
            count += 1
            self.progressSignal.emit([int(count / self.package_files_count * 100), None, None])
        return pd.DataFrame()

    def safari_favicons(self):
        count = 0
        for relative_fp in self.package_files:
            abs_fp = abspath(str(self.output_dir) + str(relative_fp))
            if isfile(abs_fp) and 'Library' in abs_fp and abs_fp.endswith('Favicons.db') and \
                    any(sub_path in abs_fp for sub_path in self.package_guids):

                query = ("""SELECT 
                        datetime('2001-01-01', "timestamp" || ' seconds') as Created,
                        page_url.url AS 'URL',
                        icon_info.url AS 'Icon URL,
                        icon_info.width AS 'Width',
                        icon_info.height AS 'Height'
                        FROM icon_info
                        LEFT JOIN page_url ON icon_info.uuid = page_url.uuid""")
                df = utils.build_dataframe(abspath, None, query=query)
                df = df.fillna('')
                return df
            count += 1
            self.progressSignal.emit([int(count / self.package_files_count * 100), None, None])
        return pd.DataFrame()

    def safari_tabs(self):
        count = 0
        for relative_fp in self.package_files:
            abs_fp = abspath(str(self.output_dir) + str(relative_fp))
            if isfile(abs_fp) and 'Library' in abs_fp and abs_fp.endswith('BrowserState.db') and \
                    any(sub_path in abs_fp for sub_path in self.package_guids):

                query = ("""SELECT
                        datetime('2001-01-01', last_viewed_time || ' seconds') AS 'Last Viewed',
                        title AS 'Title', 
                        url AS 'URL', 
                        CASE private_browsing 
                            WHEN 1 THEN "Yes"
                            WHEN 0 THEN "No"
                            ELSE private_browsing
                            END AS 'Private Browsing',
                        user_visible_url AS 'URL Visible to User' 
                        FROM tabs""")
                df = utils.build_dataframe(abs_fp, None, query=query)
                df = df.fillna('')
                return df

            count += 1
            self.progressSignal.emit([int(count / self.package_files_count * 100), None, None])
        return pd.DataFrame()

    def safari_history(self):
        count = 0
        for relative_fp in self.package_files:
            abs_fp = abspath(str(self.output_dir) + str(relative_fp))
            if isfile(abs_fp) and 'Library' in abs_fp and abs_fp.endswith('History.db') and \
                    any(sub_path in abs_fp for sub_path in self.package_guids):

                query = (
                    """SELECT datetime('2001-01-01', history_visits.visit_time || ' seconds') AS 'Created Time',
                    history_items.url AS 'URL',
                    history_items.visit_count AS 'Visit Count',
                    history_visits.title 'Title',
                    CASE history_visits.origin
                        WHEN 1 THEN "iCloud Sync"
                        WHEN 0 THEN "This Device"
                        ELSE history_visits.origin
                        END AS "Source",
                    CASE history_visits.load_successful
                        WHEN 1 THEN "Yes"
                        WHEN 0 THEN "No"
                        ELSE history_visits.load_successful
                        END AS "Request Successful",
                    history_visits.id,
                    CAST(history_visits.redirect_source AS INT) AS 'Redirected From',
                    CAST(history_visits.redirect_destination AS INT) AS 'Redirected To'
                    FROM history_items
                    LEFT JOIN history_visits ON history_items.id = history_visits.history_item
                    """)
                df = utils.build_dataframe(abs_fp, None, query=query)
                df = df.fillna('')
                return df

            count += 1
            self.progressSignal.emit([int(count / self.package_files_count * 100), None, None])
        return pd.DataFrame()

    def blobs_and_records(self, cache_type):
        records = list()
        origin_files = dict()
        count = 0
        for relative_fp in self.package_files:
            abs_fp = abspath(str(self.output_dir) + str(relative_fp))
            if isfile(abs_fp) and cache_type in abs_fp and \
                    ('Records' in abs_fp or 'Blobs' in abs_fp) and \
                    any(sub_path in abs_fp for sub_path in self.package_guids):
                if basename(abs_fp) == 'origin':
                    origin_files[basename(dirname(abs_fp))] = parse_origin(abs_fp)
                    print(origin_files)
                else:
                    # Else lets try and parse it as a file
                    with open(abs_fp, 'rb') as f:
                        header = f.read(100)
                    if header:
                        if b'\x0E\x00\x00\x00' not in header[0:16]:  # a record file
                            mime_type = utils.get_file_mimetype(header, abs_fp)
                            if mime_type:
                                blob = dict()
                                new_fn = abspath(pj(dirname(abs_fp), '{}.{}'.format(basename(abs_fp), mime_type[0])))
                                os.rename(abs_fp, new_fn)
                                blob['media'] = new_fn
                                blob['Mime Type'] = mime_type[0]
                                blob['File Type'] = mime_type[1]
                                blob['File Name'] = basename(abs_fp)
                                blob['Asset'] = 'BLOB'.format(cache_type)
                                records.append(blob)
                        else:
                            # First parse the file as a record.
                            rp = smidge.RecordParser(abs_fp, 'file', 'dict', dirname(abs_fp))
                            try:
                                parsed_count, _dict, errors = rp.process()
                                if _dict:
                                    _dict[0]['Asset'] = 'Record'.format(cache_type)
                                    records.append(_dict[0])
                            except Exception as e:
                                logging.error(e)
                                continue
            count += 1
            self.progressSignal.emit([int(count / self.package_files_count * 100), None, None])

        if records:
            for r in records:
                try:
                    del r['content']  # Only in records, not blob dicts
                except KeyError:
                    pass

            df = pd.DataFrame(records)
            reordered_cols = ['media', 'File Name', 'File Type', 'Mime Type', 'Asset']
            # Extend the reordered column with the rest (removing those already ordered above)
            reordered_cols.extend([x for x in df.columns.values.tolist() if x not in reordered_cols])
            df = df[reordered_cols]
            df.replace(np.nan, '', regex=True, inplace=True)
            return df

        return pd.DataFrame()

    def app_cache(self):
        records = list()
        count = 0
        for relative_fp in self.package_files:
            abs_fp = abspath(str(self.output_dir) + str(relative_fp))
            if isfile(abs_fp) and 'cache' in abs_fp.lower() and 'image' \
                    in abs_fp.lower() and any(sub_path in abs_fp for
                                              sub_path in self.package_guids):
                with open(abs_fp, 'rb') as f:
                    header = f.read(20)
                if header:
                    mime_type = utils.get_file_mimetype(header)
                    if mime_type:
                        record = dict()
                        new_fn = abspath(pj(dirname(abs_fp), '{}.{}'.format(basename(abs_fp), mime_type[0])))
                        os.rename(abs_fp, new_fn)
                        record['media'] = new_fn
                        record['mime_type'] = mime_type[0]
                        record['File Type'] = mime_type[1]
                        record['filename'] = basename(abs_fp)
                        records.append(record)
            count += 1
            self.progressSignal.emit([int(count / self.package_files_count * 100), None, None])

        if records:
            return pd.DataFrame(records)
        return pd.DataFrame()


class AndroidThread(QThread):
    finishedSignal = pyqtSignal(list)
    progressSignal = pyqtSignal(list)

    def __init__(self, *args):
        QThread.__init__(self, parent=None)
        self.package_files, self.output_dir, self.package = args
        self.package_files_count = len(self.package_files)
        self.generator_dict = {'HTTP Cache': self.http_cache,
                               'Cookies': self.cookies,
                               'LocalStorage': self.leveldb,
                               'App Cache': self.app_cache}

    def run(self):
        for webview_item, df_generator in self.generator_dict.items():
            self.progressSignal.emit([0, 'Processing {}...'.format(webview_item), None])
            report_name = 'Shomium - {} - {}'.format(self.package, webview_item)
            df = df_generator()
            self.progressSignal.emit([100,
                                      'Finished processing {}...'.format(webview_item),
                                      [df, self.package_files, report_name, self.output_dir,
                                       self.package, webview_item]])
            self.progressSignal.emit([100, '{} - {} ({} rows)'.format(self.package, webview_item, len(df.index)), None])
        self.finishedSignal.emit([])

    def cookies(self):
        count = 0
        for relative_fp in self.package_files:
            abs_fp = abspath(pj(self.output_dir, 'data', 'data', relative_fp))
            if isfile(abs_fp) and 'cookies' in basename(abs_fp).lower():
                with open(abs_fp, 'rb') as sql:
                    if b'SQLite format 3' not in sql.read(16):
                        pass
                    else:
                        cnx = sqlite3.connect(abs_fp)
                        df = pd.read_sql_query("SELECT * FROM cookies", cnx)
                        return df
            count += 1
            self.progressSignal.emit([int(count/self.package_files_count*100), None, None])
        return pd.DataFrame()

    def http_cache(self):
        http_cache = list()

        count = 0
        for relative_fp in self.package_files:
            abs_fp = abspath(pj(self.output_dir, 'data', 'data', relative_fp))
            if isfile(abs_fp):
                f = open(abs_fp, 'rb').read()
                try:
                    magic = utils.unpacker('<12s', f[0:12])
                except:
                    magic = None

                if magic == b'0\\r\xa7\x1bm\xfb\xfc\x05\x00\x00\x00':
                    file_dict = dict()
                    file_dict['filename'] = basename(relative_fp)
                    # bytes 12-16 is the length of the URL from offset 24
                    url_len = utils.unpacker('<i', f[12:16])
                    # We can read the URL from offset 24 - length of the URL
                    file_dict['url'] = utils.unpacker('<{}s'.format(url_len), f[24:24 + url_len]).decode()
                    # read the magic of the embedded data to see if it matches a known file format e.g JPEG
                    try:
                        mime_type = utils.get_file_mimetype(utils.unpacker('<16s',
                                                                           f[24 + url_len:24 + url_len + 16]))[0]
                    except TypeError:  # May not contain a media file/unrecognised
                        mime_type = None

                    file_dict['output_fn'] = '{}.{}'.format(basename(abs_fp), mime_type)
                    # keep a relative path in our dict so we can refer back to it with a hyperlink
                    file_dict['media'] = pj(self.output_dir, 'data', 'data',
                                            dirname(relative_fp), file_dict['output_fn'])

                    file_dict['relpath'] = relpath(pj(dirname(relative_fp), file_dict['output_fn']))

                    # Begin extracting Metadata
                    meta_data_header = find_meta_block(f)

                    file_dict['relpath'] = relpath(pj(dirname(relative_fp), file_dict['output_fn']))

                    if mime_type:
                        # The bytes following might be a cache file, but sometimes not.
                        # We can read up to the meta block > file
                        with open(pj(dirname(abs_fp), file_dict['output_fn']), 'wb') as f_out:
                            f_out.write(f[24 + url_len:meta_data_header])
                    else:
                        shutil.copy(utils.resource_path('blank_jpeg.png'),
                                    pj(dirname(abs_fp), file_dict['output_fn']))

                    # the beginning of the metadata block is 52 bytes from the end of the blob. It may not follow
                    # the rules so we will wrap this in a try except block and skip metadata if it doesn't play ball
                    try:
                        metadata_offs = meta_data_header + 40 + 12
                        # Length of Metadata. Move 12 bytes for the header length and then
                        # 36 bytes to the length integer (4 byte int) preceding the metadata block.
                        metadata_length = utils.unpacker('<i', f[meta_data_header + 36 + 12:
                                                                 meta_data_header + 36 + 12 + 4])

                        metadata = f[metadata_offs:metadata_offs + metadata_length]
                        # Each metadata field is separated by x\00. We can chunk into key values
                        mdat_parts = metadata.split(b'\00')[:-2]
                        mdat_parts = '\n'.join([x.decode('latin1') for x in mdat_parts])
                        file_dict['metadata'] = mdat_parts
                    except:
                        pass

                    http_cache.append(file_dict)
            count += 1
            self.progressSignal.emit([int(count / self.package_files_count * 100), None, None])

        if http_cache:
            return pd.DataFrame(http_cache, columns=http_cache[0].keys())

        return pd.DataFrame()

    def leveldb(self):
        count = 0
        for relative_fp in self.package_files:
            abs_fp = abspath(pj(self.output_dir, 'data', 'data', relative_fp))
            if isfile(abs_fp) and pj('Local Storage', 'leveldb') in abs_fp and abs_fp.endswith('.log'):
                # ----------------------------------------------------------------------------
                # modified code from ccl script 'dump_leveldb.py'
                leveldb_records = ccl_leveldb.RawLevelDb(pathlib.Path(dirname(abs_fp)))
                cols = ["key-hex", "key-text", "value-hex", "value-text", "origin_file",
                        "file_type", "offset", "seq", "state", "was_compressed"]
                rows = list()
                for record in leveldb_records.iterate_records_raw():
                    rows.append([
                        record.user_key.hex(" ", 1),
                        record.user_key.decode("iso-8859-1", "replace"),
                        record.value.hex(" ", 1),
                        record.value.decode("iso-8859-1", "replace"),
                        str(record.origin_file),
                        record.file_type.name,
                        record.offset,
                        record.seq,
                        record.state.name,
                        record.was_compressed
                    ])
                if rows:
                    df = pd.DataFrame(rows, columns=cols)
                    df.drop(['key-hex', 'value-hex'], axis=1, inplace=True)
                    return df

            count += 1
            self.progressSignal.emit([int(count/self.package_files_count*100), None, None])
        return pd.DataFrame()

    def app_cache(self):
        # All other cache files
        app_cache = list()
        count = 0
        for relative_fp in self.package_files:
            abs_fp = abspath(pj(self.output_dir, 'data', 'data', relative_fp))
            if isfile(abs_fp):
                with open(abs_fp, 'rb') as f:
                    header = f.read(100)
                if header:
                    mime_type = utils.get_file_mimetype(header)
                    if mime_type:
                        cache_record = dict()
                        new_fn = abspath(pj(dirname(abs_fp), '{}.{}'.format(basename(abs_fp), mime_type[0])))
                        if isfile(new_fn):
                            pass
                        else:
                            os.rename(abs_fp, new_fn)
                        cache_record['media'] = new_fn
                        cache_record['mime_type'] = mime_type[0]
                        cache_record['File Type'] = mime_type[1]
                        cache_record['filename'] = basename(abs_fp)
                        app_cache.append(cache_record)
            count += 1
            self.progressSignal.emit([int(count/self.package_files_count*100), None, None])
        if app_cache:
            return pd.DataFrame(app_cache)

        return pd.DataFrame()
