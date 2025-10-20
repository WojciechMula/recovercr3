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

        # Handling logic for maxchunks and lastchunk
        if self.args.maxchunks:
            maxchunks = self.args.maxchunks
            def last(chunk_id, chunk_name):
                return chunk_id + 1 == maxchunks

            self.CR3_last_chunk = last
        else:
            lastchunk = self.args.lastchunk
            def last(chunk_id, chunk_name):
                # Encode the string lastchunk to bytes for comparison with chunk_name
                return chunk_name == lastchunk.encode()

            self.CR3_last_chunk = last

    def run(self):
        path = self.args.input
        log.info(f"Processing {path}")
        count = 0
        with path.open('rb') as dump, path.open('rb') as cr3:
            for offset in CR3_headers(dump, self.input_size):
                log.debug(f"found CR3 header at offset {offset}")
                cr3.seek(offset)
                # Pass offset for logging context inside CR3_size
                size = self.CR3_size(cr3, offset) 
                if size > 0:
                    log.debug("Found valid CR3 chunk, restoring...")
                    self.restore(cr3, offset, size)
                    count += 1
                else:
                    log.debug("not a CR3 file or file is too large/corrupt")

        if count:
            log.info(f"Restored {count} file(s)")
        else:
            log.info("No CR3 files found")

    def restore(self, cr3, offset, size):
        # Use the exact format: 0001.CR3, 0002.CR3, etc.
        name = f'{self.file_id:04d}.CR3'  # Force the extension to be uppercase (CR3)
        path = self.args.outdir / name
        self.file_id += 1

        if path.exists():
            log.info(f"{path} already exists: skipping")
            return

        cr3.seek(offset)

        bufsize = 16 * MB  # Increased buffer size
        log.info(f"Saving {path}, size {size:,d} B")

        # Write directly to the output file
        with path.open('wb') as out:
            while size > 0:
                k = min(bufsize, size)
                buf = cr3.read(k)
                if not buf:
                    # Logs when the file stream ends before the calculated size is reached
                    log.warning(f"Unexpected EOF while reading {path}. File may be incomplete.")
                    break
                out.write(buf)
                size -= k

    # THIS METHOD HAS BEEN CORRECTED TO USE A MORE ROBUST CARVING HEURISTIC
    def CR3_size(self, file_stream, start_offset):
        total_size = 0
        MAX_CR3_SIZE = 1 * 1024 * 1024 * 1024  # 1GB max
        endianess = 'big' 
        
        # New: Store all found atoms to apply the stopping rule later
        atoms = []

        # 1. First Pass: Read all valid, contiguous atoms until corruption or EOF
        # CR3_atoms is called only once and finds all sequential, valid atoms.
        for index, (offset, name, size) in enumerate(CR3_atoms(file_stream, endianess)):
            
            # Check for excessive size during atom traversal
            if (total_size + size) > MAX_CR3_SIZE:
                log.warning(f"File size exceeded {MAX_CR3_SIZE:,d} B! Likely corrupt data starting at offset {start_offset}.")
                return 0 # Stop and discard file
                
            if index == 0 and name != b'ftyp':
                log.debug("First atom is not 'ftyp'")
                return 0 # Stop and discard file

            atoms.append((name, size, index))
            total_size += size

        # If no flags are set, total_size is the full contiguous atom sequence size found.

        # 2. Second Pass: Apply Last Chunk Rule (if specified by user flags)
        
        # If the user specified a max chunk count (e.g., --maxchunks 10)
        if self.args.maxchunks and len(atoms) > self.args.maxchunks:
            # Recalculate size based on the slice of atoms
            total_size = sum(size for _, size, _ in atoms[:self.args.maxchunks])
            log.debug(f"Applied --maxchunks {self.args.maxchunks}, new size: {total_size:,d} B")
            return total_size
        
        # If the user specified a last chunk name (e.g., --lastchunk mdat)
        elif self.args.lastchunk:
            final_size = 0
            found_last_chunk = False
            for name, size, index in atoms:
                final_size += size
                # Check for the specified last chunk
                if self.CR3_last_chunk(index, name):
                    found_last_chunk = True
                    break
            
            # If the last chunk wasn't found in the contiguous sequence, discard (or revert to total_size).
            # Discarding is safer for file carving.
            if not found_last_chunk:
                log.debug(f"Did not find expected last chunk '{self.args.lastchunk}' in contiguous sequence starting at offset {start_offset}.")
                return 0
            
            total_size = final_size
            log.debug(f"Applied --lastchunk {self.args.lastchunk}, new size: {total_size:,d} B")

        # The function returns the total_size calculated based on the atoms list,
        # truncated by user flags or limited by the end of the valid sequence.
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
    p.add_argument("--ext",
                   type=str,
                   help="file extension without the dot [default %(default)s]",
                   default="cr3",
                   metavar="EXT")
    p.add_argument("--numwidth",
                   type=int,
                   help="how many digits use to number files; shorter numbers will be zero-prefixed",
                   default=0)
    p.add_argument('-v', '--verbose',
                   action="store_true",
                   default=False,
                   help="be verbose")
    p.add_argument('--lastchunk',
                   type=str,
                   default='mdat',
                   metavar="NAME",
                   help="name of last CR3 chunk [default '%(default)s']")
    p.add_argument('--maxchunks',
                   type=int,
                   metavar="N",
                   help="max number of CR3 chunks to output")

    args = p.parse_args()
    if args.maxchunks is not None:
        if args.maxchunks <= 0:
            p.error("--maxchunks must be greater than zero")

        args.lastchunk = '' # Set lastchunk to empty string if maxchunks is used
    else:
        # Fixed NameError by using 'args.lastchunk'
        if not args.lastchunk:
            p.error("--lastchunk must not be empty")

    if args.input.exists() == False:
        p.error(f"Input file {args.input} does not exist")

    if args.outdir.is_dir() == False:
        # Check if the directory exists, if not, attempt to create it
        try:
            args.outdir.mkdir(parents=True, exist_ok=True)
            log.info(f"Created output directory: {args.outdir}")
        except OSError as e:
            p.error(f"Output directory {args.outdir} does not exist and could not be created: {e}")


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
... (documentation preserved)
"""
def CR3_atoms(file, endianess):
    """
    Scans a binary file and yields CR3 atoms.
    """

    assert file.seekable()

    while True:
        pos  = file.tell()

        tmp = file.read(4)
        if not tmp or len(tmp) < 4: # eof or truncated read
            break

        name = file.read(4)
        if not name or len(name) < 4: # truncated read
            break

        # FIXED: The ValueError required endianess to be 'big' or 'little'
        tmp = int.from_bytes(tmp, endianess) 
        if tmp == 1:
            tmp  = file.read(8)
            if not tmp or len(tmp) < 8: # truncated read
                break
            size = int.from_bytes(tmp, endianess)
        else:
            size = tmp

        # Sanity check for size
        if size < 8: # min size for size(4) + name(4)
            log.debug(f"Skipping atom with invalid size {size} at position {pos}")
            break # Exit the loop if an atom size is too small/corrupt

        yield (pos, name, size)

        # Move to the start of the next atom
        file.seek(pos + size)


# bytes at the beginning of file
CR3_magic  = b'\x00\x00\x00\x18ftypcrx'

# name inside header, at offset 64 (this is how Geeqie identifies CR3s)
CR3_marker = b'CanonCR3'


def CR3_headers(file, totalsize, bufsize=16 * MB):
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
            # Move back enough to check for a split magic number
            file.seek(pos + bufsize - 2*n)
            continue

        # Found CR3_magic, check for CR3_marker at offset 64
        original_position = file.tell()
        file.seek(pos + idx + 64)
        marker = file.read(len(CR3_marker))
        
        if marker != CR3_marker:
            file.seek(pos + idx + n) # Continue search from after the magic
            continue

        # CR3 header found and validated
        yield (pos + idx)

        # Resume search from immediately after the valid header
        file.seek(pos + idx + n)


if __name__ == '__main__':
    log = logger()
    main()
