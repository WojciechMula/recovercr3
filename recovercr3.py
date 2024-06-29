#!/usr/bin/env python3

import os
import sys
import argparse
import logging
from pathlib import Path


MB = 1024*1024


def main():
    args = parse_args()
    app = Application(args)
    app.run()


class Application:
    def __init__(self, args):
        self.args = args
        self.input_size = args.input.stat().st_size
        self.file_id = 1

        if self.args.maxchunks:
            maxchunks = self.args.maxchunks
            def last(chunk_id, chunk_name):
                return chunk_id + 1 == maxchunks

            self.CR3_last_chunk = last
        else:
            lastchunk = self.args.lastchunk
            def last(chunk_id, chunk_name):
                return chunk_name == lastchunk

            self.CR3_last_chunk = last

    def run(self):
        path = self.args.input
        log.info(f"Processing {path}")
        count = 0
        with path.open('rb') as dump, path.open('rb') as cr3:
            for offset in CR3_headers(dump, self.input_size):
                log.debug(f"found CR3 header at offset {offset}")
                cr3.seek(offset)
                size = self.CR3_size(cr3)
                if size > 0:
                    self.restore(cr3, offset, size)
                    count += 1
                else:
                    log.debug("not a CR3 file")

        if count:
            log.info(f"Restored {count} file(s)")
        else:
            log.info("No CR3 files found")

    def restore(self, cr3, offset, size):
        path = self.args.outdir / f'img{self.file_id}.cr3'
        self.file_id += 1

        if path.exists():
            log.info(f"{path} already exists: skipping")
            return

        cr3.seek(offset)

        bufsize = 8*MB
        log.info(f"Saving {path}, size {size:,d} B")
        with path.open('wb') as out:
            while size > 0:
                k = min(bufsize, size)
                buf = cr3.read(k)
                out.write(buf)
                size -= k

    def CR3_size(self, cr3, endianess="big"):
        total_size = 0
        for index, (offset, name, size) in enumerate(CR3_atoms(cr3, endianess)):
            if index == 0 and name != b'ftyp':
                break

            total_size += size

            log.debug(f"atom name = {name}, size = {size}")
            if self.CR3_last_chunk(index, name):
                break

        return total_size


def parse_args():
    p = argparse.ArgumentParser(description="Recover Canon CR3 files from memory dumps")

    p.add_argument('--input',
                   type=Path,
                   required=True,
                   help="memory dump",
                   metavar="PATH")
    p.add_argument('--outdir',
                   type=Path,
                   required=True,
                   help="output directory",
                   metavar="DIR")
    p.add_argument('-v', '--verbose',
                   action="store_true",
                   default=False,
                   help="be verbose")
    p.add_argument('--lastchunk',
                   type=str,
                   default='mdat',
                   metavar="NAME",
                   help="name of last CR3 chunk (default 'mdat')")
    p.add_argument('--maxchunks',
                   type=int,
                   metavar="N",
                   help="max number of CR3 chunks to output")

    args = p.parse_args()
    if args.maxchunks is not None:
        if args.maxchunks <= 0:
            p.error("--maxchunks must be greater than zero")

        args.lastchunk = b''
    else:
        args.lastchunk = bytes(args.lastchunk, encoding='utf-8')
        if not args.lastchunk:
            p.error("--lastchunk must not be empty")

    if not args.input.exists():
        p.error(f"{args.input} does not exist")

    if not args.outdir.is_dir():
        p.error(f"{args.outdir} is not a directory or not exists")

    if args.verbose:
        log.setLevel(logging.DEBUG)

    return args


def logger():
    log = logging.getLogger(__name__)
    log.setLevel(logging.INFO)

    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))

    log.addHandler(ch)

    return log


"""
CR3 file structure
==================================================

This description was written based on the DCRaw project sources.

A CR3 file is a series of chunks. A chunk consist a header and data.
The header may be in two forms:

    size uint32
    name char[4]

or

    mark uint32 = 1
    name char[4]
    size uint64

The size is the total number of bytes of header + data.
"""
def CR3_atoms(file, endianess="big"):
    """
    Scans a binary file and yields CR3 atoms.
    """

    assert file.seekable()

    while True:
        pos  = file.tell()

        tmp = file.read(4)
        if not tmp: # eof
            break

        name = file.read(4)

        tmp = int.from_bytes(tmp, endianess)
        if tmp == 1:
            tmp  = file.read(8)
            size = int.from_bytes(tmp, endianess)
        else:
            size = tmp

        yield (pos, name, size)

        file.seek(pos + size)


# bytes at the beginning of file
CR3_magic  = b'\x00\x00\x00\x18ftypcrx'

# name inside header, at offset 64 (this is how Geeqie identifies CR3s)
CR3_marker = b'CanonCR3'


def CR3_headers(file, totalsize, bufsize=8*MB):
    """
    Scans a binary file and yield offset where CR3 file may start.
    """
    n = len(CR3_magic)
    k = len(CR3_marker)
    while True:
        pos = file.tell()
        progress = 100 * pos / totalsize
        log.debug(f"read at {pos:,d} B of {totalsize:,d} B ({progress:0.2f}%)")
        buf = file.read(bufsize)
        if not buf:
            break

        idx = buf.find(CR3_magic)
        if idx < 0:
            file.seek(pos + bufsize - 2*n)
            continue

        file.seek(pos + idx + 64)
        marker = file.read(len(CR3_marker))
        if marker != CR3_marker:
            file.seek(pos + idx + n)
            continue

        yield (pos + idx)

        file.seek(pos + idx + n)


if __name__ == '__main__':
    log = logger()
    main()
