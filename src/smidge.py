'''
MIT License

smidge

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

__version__ = 0.01
__description__ = 'Control-F - smidge - Apple Binary Record Parser'
__contact__ = 'mike.bangham@controlf.co.uk'

import sys
import os
from os.path import abspath, isfile, isdir, basename
from os.path import join as pj
from struct import unpack
from collections import namedtuple
import argparse
import time
import csv

# Apple cocoa timestamp epoch
cocoa_delta = 978307200


def generate_dataframe(records_dict):
    import pandas as pd
    df = pd.DataFrame(records_dict)
    return df


def generate_csv(records_dict):
    fn = 'binary_records_{}.csv'.format(int(time.time()))

    with open(fn, 'w', newline='') as csv_out:
        dict_writer = csv.DictWriter(csv_out, records_dict[0].keys())
        dict_writer.writeheader()
        dict_writer.writerows(records_dict)

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


class RecordParser:
    def __init__(self, *args):
        self._input, self.input_type, self.output_format, self.output_dir = args
        os.makedirs(self.output_dir, exist_ok=True)
        self.records = list()
        self.errors = dict(non_records=list(), errors=list())
        self.count = 1

    def log_errors(self, err, f):
        if err == 'not_a_record':
            self.errors['non_records'].append('{} is not a record file'.format(basename(f)))
        else:
            self.errors['errors'].append('Could not parse: {} {}'.format(basename(f), err))

    def process(self):
        if self.input_type == 'file':
            bf = open(self._input, 'rb')
            record = self.generate_record(bf, self._input)
            if record[0]:
                self.records.append(record[1])
            else:
                self.log_errors(record[1], self._input)
        else:
            for file in os.listdir(self._input):
                bf = open(pj(self._input, file), 'rb')
                record = self.generate_record(bf, pj(self._input, file))
                if record[0]:
                    self.records.append(record[1])
                else:
                    self.log_errors(record[1], pj(self._input, file))

        if self.records:
            if self.output_format == 'dict':
                return len(self.records), self.records, self.errors
            elif self.output_format == 'csv':
                return len(self.records), generate_csv(self.records), self.errors
            else:  # df
                return len(self.records), generate_dataframe(self.records), self.errors

        return 0, None, self.errors

    def read_payload(self, length, bf):
        bf.read(1)  # signed char \x01
        return bf.read(length).decode()

    def generate_record(self, bf, f):
        error_list = list()
        record = dict()
        # Extract 1 x 4 byte char[] 'magic'
        magic = unpacker('>4s', bf.read(4))
        if magic == b'\x0E\x00\x00\x00':
            record['path'] = f
            # Each component in the record is structured with a 4 byte little endian unsigned integer,
            # a signed signed integer that is always \x01 and then the record payload. Knowing this, we
            # can loop through this structure.
            # We have to allow for some arbitrary data along the way however

            for r in ['File Name', 'File Type', 'URL']:
                record[r] = self.read_payload(unpacker('<I', bf.read(4)), bf)

            bf.read(130)  # 130 bytes of arbitrary data
            record['URL_2'] = self.read_payload(unpacker('<I', bf.read(4)), bf)
            record['Mime Type'] = self.read_payload(unpacker('<I', bf.read(4)), bf)
            bf.read(12)  # 12 bytes of arbitrary data

            for r in ['Status', 'Protocol']:
                record[r] = self.read_payload(unpacker('<I', bf.read(4)), bf)

            bf.read(8)  # 8 bytes of arbitrary data

            # Until we reach the record content we have key value pairs. Each key and value is recorded in the
            # same way as before so we need to pair them up.
            while True:
                length = bf.read(4)
                if length != b'\xc8\x00\x00\x00':  # xc8 is consistent in most cases with the end of the metadata
                    try:
                        key = self.read_payload(unpacker('<I', length), bf)
                        value = self.read_payload(unpacker('<I', bf.read(4)), bf)
                        record[key] = value
                    except Exception as e:
                        error_list.append(e)
                        break
                else:
                    break

            bf.read(49)  # A 4 byte signed int, a signed char byte + 56 bytes of arbitrary data up to the content
            # One of the key value pairs parsed earlier contained the content length
            record['content'] = bf.read(int(record['Content-Length']))

            fn = pj(self.output_dir, '{}.{}'.format(basename(f), record['Mime Type'].split('/')[1]))
            with open(fn, 'wb') as f:
                f.write(record['content'])
            record['media'] = fn

            self.count += 1

            if error_list:
                return False, error_list

            return True, record

        else:
            return False, 'not_a_record'


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
    parser.add_argument('-i', required=True, help='A directory of binary records or a single binary record')
    parser.add_argument('-f', required=True, help="Output format: accepts 'df', 'dict' or 'csv'")
    parser.add_argument('-o', required=True, help="Output directory")
    args = parser.parse_args()

    if len(args.i) and (isfile(abspath(args.i)) or isdir(abspath(args.i))):
        _input = args.i
        if isfile(_input):
            input_format = 'file'
        else:
            input_format = 'dir'
    else:
        print('[!!] Error: Please provide a file/directory for argument -i')
        sys.exit()

    if len(args.f) and args.f in ['df', 'csv', 'dict']:
        output_format = args.f
    else:
        print("[!!] Error: argument -o only accepts 'df', 'dict' or 'csv'")
        sys.exit()

    if len(args.o) and isdir(abspath(args.o)):
        output_dir = args.o
    else:
        print("[!!] Error: argument -o is not a directory")
        sys.exit()

    rp = RecordParser(_input, input_format, output_format, output_dir)
    parsed_count, content, errors = rp.process()
    print('\nFinished! Parsed {} records'.format(parsed_count))
    print('Out:\n{}'.format(content))
    print('\nErrors\n')
    if errors['errors']:
        for error in errors['errors']:
            print(error)
    print('\n\n')

