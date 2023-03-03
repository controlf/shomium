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

__version__ = 0.4
__description__ = "iOS Application Mapper"
__contact__ = "mike.bangham@controlf.co.uk"

import tarfile
import zipfile
import time
import pandas as pd
import plistlib
from io import BytesIO
from os.path import dirname, basename, isfile, abspath
import sys
import argparse


def merge_metadata_dicts(app_dict, app_meta_dict):
    # Function to merge an applications App, Data and Shared Metadata plist files.
    # This is will assist in mapping all the app GUID's associated to an app.
    # The package name from our app dict is used to seek all child metadata plists

    for key1 in list(app_dict.keys()):
        for key2 in list(app_meta_dict.keys()):
            # also check if the item name is present as app nomenclature cannot be relied upon
            if (app_dict[key1]['App Name'] in app_meta_dict[key2]['App Name']
                    or app_dict[key1]['itemName'].lower().split(' ')[0] in app_meta_dict[key2]['App Name']):
                app_dict[key1]['MetaData'][key2] = app_meta_dict[key2]
                # remove the metadata key value as we have attributed it to a 3rd party app
                del app_meta_dict[key2]

    return app_dict, app_meta_dict


class NameParser:
    def __init__(self, *args):
        self.ios_archive, self.archive_type, self.output_format = args
        self.date_time = int(time.time())

        self.plists_to_extract = ['iTunesMetadata.plist', '.com.apple.mobile_container_manager.metadata.plist']

    def generate_dataframe(self, app_3rd_party_dict, app_native_dict, xl):
        if app_3rd_party_dict:
            df_3rd_party = pd.DataFrame.from_dict(app_3rd_party_dict, orient='index')
        else:
            df_3rd_party = pd.DataFrame(columns=['App Name'])
        if app_native_dict:
            df_native = pd.DataFrame.from_dict(app_native_dict, orient='index')
        else:
            df_native = pd.DataFrame(columns=['App Name'])

        for df in [df_native, df_3rd_party]:
            df['GUID'] = df.index
            first_column = df.pop('App Name')
            df.insert(0, 'App Name', first_column)
            df.reset_index(drop=True, inplace=True)

        if xl == 'xlsx':
            writer = pd.ExcelWriter('mapped_apps.xlsx', engine='xlsxwriter')
            df_3rd_party.to_excel(writer, sheet_name='3rd Party')
            df_native.to_excel(writer, sheet_name='Native')
            writer.save()

        return df_native, df_3rd_party

    def parse(self):
        app_dict = dict()
        app_meta_dict = dict()

        if self.archive_type == 'zip':
            with zipfile.ZipFile(self.ios_archive, 'r') as zip_obj:
                fps = zip_obj.namelist()
                for fp in fps:
                    if any(_plist in fp for _plist in self.plists_to_extract):
                        guid = basename(dirname(fp))  # each GUI has a plist containing info we need
                        f = zip_obj.read(fp)
                        try:
                            plist_ = plistlib.load(BytesIO(f))  # convert to stream then convert plist > dict
                            if plist_ and 'iTunesMetadata.plist' in fp:
                                # Third Party Application
                                app_dict[guid] = plist_
                                app_dict[guid]['App Name'] = plist_['softwareVersionBundleId']
                                app_dict[guid]['FilePath'] = fp
                                # For storing our app metadata in
                                app_dict[guid]['MetaData'] = dict()
                            else:
                                # Default Native Package
                                app_meta_dict[guid] = plist_
                                app_meta_dict[guid]['App Name'] = plist_['MCMMetadataIdentifier']
                                app_meta_dict[guid]['FilePath'] = fp
                        except Exception as err:
                            print('[!] Error - Could not parse plist for {}\n{}'.format(guid, err))
                            pass

        else:
            with tarfile.open(self.ios_archive, 'r') as file_obj:
                fps = file_obj.getnames()
                for fp in fps:
                    if any(_plist in fp for _plist in self.plists_to_extract):
                        guid = basename(dirname(fp))  # each GUI has a plist containing info we need
                        f = file_obj.extractfile(fp)  # extract file as bytes
                        try:
                            plist_ = plistlib.load(BytesIO(f.read()))  # convert to stream then convert to dict
                            if plist_ and 'iTunesMetadata.plist' in fp:
                                # Third Party Application
                                app_dict[guid] = plist_
                                app_dict[guid]['App Name'] = plist_['softwareVersionBundleId']
                                app_dict[guid]['FilePath'] = fp
                                # For storing our app metadata in
                                app_dict[guid]['MetaData'] = dict()
                            else:
                                # Default Native Package
                                app_name = plist_['MCMMetadataIdentifier']
                                app_meta_dict[guid] = plist_
                                app_meta_dict[guid]['App Name'] = plist_['MCMMetadataIdentifier']
                                app_meta_dict[guid]['FilePath'] = fp
                        except Exception as err:
                            print('[!] Error - Could not parse plist for {}\n{}'.format(guid, err))
                            pass

        app_dict, app_meta_dict = merge_metadata_dicts(app_dict, app_meta_dict)

        df_native, df_3rd_party = self.generate_dataframe(app_dict, app_meta_dict, self.output_format)

        return df_native, df_3rd_party


if __name__ == '__main__':
    print("\n\n"
          "                                                        ,%&&,\n"
          "                                                    *&&&&&&&&,\n"
          "                                                  /&&&&&&&&&&&&&\n"
          "                                               #&&&&&&&&&&&&&&&&&&\n"
          "                                           ,%&&&&&&&&&&&&&&&&&&&&&&&\n"
          "                                        ,%&&&&&&&&&&&&&&#  %&&&&&&&&&&,\n"
          "                                     *%&&&&&&&&&&&&&&%       %&&&&&&&&&%,\n"
          "                                   (%&&&&&&&&&&&&&&&&&&&#       %&%&&&&&&&%\n"
          "                               (&&&&&&&&&&&&&&&%&&&&&&&&&(       &&&&&&&&&&%\n"
          "              ,/#%&&&&&&&#(*#&&&&&&&&&&&&&&%,    #&&&&&&&&&(       &&&&&&&\n"
          "          (&&&&&&&&&&&&&&&&&&&&&&&&&&&&&#          %&&&&&&&&&(       %/\n"
          "       (&&&&&&&&&&&&&&&&&&&&&&&&&&&&&(               %&&&&&&&&&/\n"
          "     /&&&&&&&&&&&&&&&&&&%&&&&&&&%&/                    %&&&&&,\n"
          "    #&&&&&&&&&&#          (&&&%*                         #,\n"
          "   #&&&&&&&&&%\n"
          "   &&&&&&&&&&\n"
          "  ,&&&&&&&&&&\n"
          "   %&&&&&&&&&                           {}\n"
          "   (&&&&&&&&&&,             /*          Version: {}\n"
          "    (&&&&&&&&&&&/        *%&&&&&#\n"
          "      &&&&&&&&&&&&&&&&&&&&&&&&&&&&&%\n"
          "        &&&&&&&&&&&&&&&&&&&&&&&&&%\n"
          "          *%&&&&&&&&&&&&&&&&&&#,\n"
          "                *(######/,".format(__description__, __version__))
    print('\n\n')

    print("Append the '--help' command to see usage in detail")

    parser = argparse.ArgumentParser(description=__description__)
    parser.add_argument('-i', required=True, help='The iOS input archive (Full File System)')
    parser.add_argument('-o', required=True, help="Output format: accepts 'df' or 'xlsx'")
    args = parser.parse_args()

    if len(args.i) and isfile(abspath(args.i)):
        archive = args.i
        if zipfile.is_zipfile(archive):
            archive_type = 'zip'
        elif tarfile.is_tarfile(archive):
            archive_type = 'tar'
        else:
            print('\n[!] Unrecognised file format - must be a zip or tar archive')
            sys.exit()
    else:
        print('[!!] Error: Please provide an archive for argument -i')
        sys.exit()

    if len(args.o) and args.o in ['df', 'xlsx']:
        output_format = args.o
    else:
        print("[!!] Error: argument -o only accepts 'df' or 'xlsx'")
        sys.exit()

    np = NameParser(archive, archive_type, output_format)
    app_native_df, app_3rd_party_df = np.parse()

    print('\nFinished!'
          '\n\t[*] Mapped {} 3rd Party Apps'
          '\n\t[*] Mapped {} Native Apps\n\n'.format(len(app_3rd_party_df.index), len(app_native_df.index)))
    print('Native Apps DataFrame:\n{}'.format(app_native_df))
    print('\n\n3rd Party Apps DataFrame:\n{}'.format(app_3rd_party_df))
    print('\n\n')
