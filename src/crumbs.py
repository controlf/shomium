'''
MIT License

crumbs

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

__version__ = 0.02
__description__ = 'Control-F - crumbs - Apple Binary Cookie Parser'
__contact__ = 'mike.bangham@controlf.co.uk'

import sys
from os.path import dirname, abspath, isfile
from struct import unpack
from collections import namedtuple
from datetime import datetime
import argparse
import time
import csv

# Apple cocoa timestamp epoch
cocoa_delta = 978307200


def generate_dataframe(cookie_dict):
    import pandas as pd
    df = pd.DataFrame()
    columns = ['Last Access (ts)', 'Last Access (dt)', 'Name', 'Value', 'Path', 'URL', 'Expires', 'Flag']
    rows = []
    pages = cookie_dict['header']['page_count']
    for page in range(pages):
        for cookie in cookie_dict['header']['pages'][page]['cookies']:
            cd = cookie_dict['header']['pages'][page]['cookies'][cookie]['data']
            rows.append([int(cd['Last Access (ts)']), cd['Last Access (dt)'], cd['Name'], cd['Value'],
                         cd['Path'], cd['URL'], cd['Expires'], cd['Flag']])
    if rows:
        df = pd.DataFrame(rows, columns=columns)
    return df


def generate_csv(cookie_dict):
    fn = 'binary_cookies_{}.csv'.format(int(time.time()))
    with open(fn, 'w', encoding='UTF8', newline='') as outfile:
        cols = ['Last Access (ts)', 'Last Access (dt)', 'Name', 'Value', 'Path', 'URL', 'Expires', 'Flag']
        w = csv.DictWriter(outfile, cols)
        w.writeheader()
        pages = cookie_dict['header']['page_count']
        for page in range(pages):
            for cookie in cookie_dict['header']['pages'][page]['cookies']:
                cd = cookie_dict['header']['pages'][page]['cookies'][cookie]['data']
                cd = {k: cd[k] for k in cols}  # omits any keys not required for final output
                w.writerow(cd)
    return fn


def unpacker(struct_arg, data, fields=None):
    # Accepts a struct argument, the packed binary data and optional fields.
    if fields:
        # returns a dictionary where the field is the key and the unpacked data is value.
        attr1 = namedtuple('struct', fields)
        return attr1._asdict(attr1._make(unpack(struct_arg, data)))
    else:
        # or just return value of single argument
        return unpack(struct_arg, data)[0]


class CookieParser:
    def __init__(self, input_file, output):
        self.binary_file = open(input_file, "rb")
        self.output_format = output
        self.cookie_dict = dict()

    def process(self):
        # Extract 1 x 4 byte char[] 'magic' and 1 x 4 byte int
        self.cookie_dict['header'] = unpacker('>4s i', self.binary_file.read(8), ['magic', 'page_count'])
        if self.cookie_dict['header']['magic'] == b'cook':
            if self.cookie_dict['header']['page_count'] > 0:
                # Each page will have its own dictionary
                self.cookie_dict['header']['pages'] = dict()
                for page in range(self.cookie_dict['header']['page_count']):
                    self.cookie_dict['header']['pages'][page] = page_dict = {}
                    page_dict['page_size'] = unpacker('>i', self.binary_file.read(4))

            # move to first page offset
            for page in range(self.cookie_dict['header']['page_count']):
                # read each page into bytes object
                page_data = self.binary_file.read(self.cookie_dict['header']['pages'][page]['page_size'])
                # now we can process the page
                self.process_page(self.cookie_dict['header']['pages'][page], page_data)

        if self.output_format == 'csv':
            output = generate_csv(self.cookie_dict)
        else:
            output = generate_dataframe(self.cookie_dict)

        cookie_count = 0
        for page in self.cookie_dict['header']['pages']:
            cookie_count += self.cookie_dict['header']['pages'][page]['cookie_count']

        return cookie_count, output

    def process_page(self, page_dict, page_data):
        page_dict['page_header'] = unpacker('>i', page_data[0:4])
        if page_dict['page_header'] == 256:  # b'00000100'
            page_dict['cookie_count'] = unpacker('<i', page_data[4:8])
            if page_dict['cookie_count'] > 0:
                page_dict['cookies'] = dict()
                s = 8
                for cookie in range(page_dict['cookie_count']):
                    # create a dictionary for each cookie
                    page_dict['cookies'][cookie] = cookie_dict = dict()
                    # get the start offset for each cookie in the page (4 bytes Little Endian)
                    cookie_dict['offset'] = unpacker('<i', page_data[s:s+4])
                    # read the cookie data from the offset
                    cookie_data = page_data[cookie_dict['offset']:]
                    cookie_dict['data'] = self.process_cookie(cookie_data)
                    s += 4

    @staticmethod
    def process_cookie(cookie_data):
        data_dict = dict()
        data_dict['size'] = unpacker('<i', cookie_data[0:4])
        # bytes[4:8] are obscure
        data_dict['Flag'] = ''
        # Known flags
        flags = {0: '', 1: 'Secure', 2: 'HTTP', 3: 'Secure/HTTP'}
        if unpacker('<i', cookie_data[8:12]) in flags.keys():
            data_dict['Flag'] = flags[unpacker('<i', cookie_data[8:12])]
        # bytes[12:16] are obscure
        # merge output from unpacker with out dictionary
        data_dict = dict(**data_dict, **(unpacker('<4i',
                                                  cookie_data[16:32],
                                                  ['url_ofs', 'name_ofs', 'path_ofs', 'val_ofs'])))
        # miss the following 8 bytes [32:40] - this is the cookie header footer
        data_dict['expires_epoch'] = int(unpacker('<d', cookie_data[40:48]))
        data_dict['Last Access (ts)'] = int(unpacker('<d', cookie_data[48:56]))

        # Make the timestamps readable
        try:
            data_dict['Expires'] = datetime.fromtimestamp(data_dict['expires_epoch'] +
                                                          cocoa_delta).strftime('%Y-%m-%d %H:%M:%S')
        except OSError:
            data_dict['Expires'] = '-'
        try:
            data_dict['Last Access (dt)'] = datetime.fromtimestamp(data_dict['Last Access (ts)'] +
                                                              cocoa_delta).strftime('%Y-%m-%d %H:%M:%S')
        except OSError:
            data_dict['Last Access (dt)'] = '-'

        # all components end with \x00 so we can use this to delimit the component pieces
        for ofs, component in {'url_ofs': 'URL', 'name_ofs': 'Name', 'path_ofs': 'Path', 'val_ofs': 'Value'}.items():
            s = data_dict[ofs]
            data_dict[component] = ''
            while True:
                # check if \x00
                unpacked_byte = unpacker('<b', cookie_data[s:s+1])
                if unpacked_byte != 0:
                    # append decoded byte to dict
                    data_dict[component] += cookie_data[s:s+1].decode()
                    s += 1
                else:
                    break
        return data_dict


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
    parser.add_argument('-i', required=True, help='The binary cookie file e.g. Cookies.binarycookies')
    parser.add_argument('-o', required=True, help="Output format: accepts 'df' or 'csv'")
    args = parser.parse_args()

    if len(args.i) and isfile(abspath(args.i)):
        cookie_file = args.i
    else:
        print('[!!] Error: Please provide a file for argument -i')
        sys.exit()

    if len(args.o) and args.o in ['df', 'csv']:
        output_format = args.o
    else:
        print("[!!] Error: argument -o only accepts 'df' or 'csv'")
        sys.exit()

    cp = CookieParser(cookie_file, output_format)
    parsed_count, content = cp.process()
    print('\nFinished! Parsed {} cookies'.format(parsed_count))
    print('Out:\n{}'.format(content))
    print('\n\n')

