# greaseweazle/image/sony1dd.py
#
# Sony SMC-777 ".1DD" disk images.
#
# These are D88 containers holding a single-sided, 70-cylinder 3.5" disk
# (media type 0x30 or 0x40), typically 16 x 256-byte MFM sectors per track.
# Unlike a standard 2D/2DD D88 image, the track table is indexed by
# cylinder (not cyl*2+head). The SMC-777 drive runs at 600rpm with a
# 500kbit/s data rate, which is equivalent to 250kbit/s at 300rpm. Greaseweazle
# scales the written flux to the drive's measured rotation speed anyway.
#
# This is free and unencumbered software released into the public domain.
# See the file COPYING for more details, or visit <http://unlicense.org>.

import struct

from greaseweazle import error
from .d88 import D88, D88Opts, TrackDict

# Physical sector order (3:1 interleave) of Sony Filer / SMC-DOS tracks,
# per smc777.com/software/smcdef.txt. D88 images store these in logical order.
INTERLEAVE = [1,4,7,10,13,16,3,6,9,12,15,2,5,8,11,14]

def interleave_sectors(secs, interleave: int = 3):
    """Apply the Sony 3:1 interleave to a full 16x256 track with sector IDs
    1-16 (SMC1) or 129-144 (SMC2). Other layouts (eg. 5x1024 G-OS tracks,
    copy-protected tracks) keep the order given in the image."""
    if interleave == 1:
        return sorted(secs, key=lambda s: s[2])
    if len(secs) != 16 or any(s[3] != 1 for s in secs):
        return secs
    ids = sorted(s[2] for s in secs)
    base = ids[0]
    if base not in (1, 129) or ids != list(range(base, base + 16)):
        return secs
    by_id = {s[2]: s for s in secs}
    return [by_id[base + i - 1] for i in INTERLEAVE]

class SONY1DDOpts(D88Opts):
    """index: Index into multi-disk image.
    interleave: Sector interleave (3 = Sony Filer default, 1 = sequential)."""

    r_settings = [ 'index', 'interleave' ]

    def __init__(self) -> None:
        super().__init__()
        self._interleave = 3

    @property
    def interleave(self) -> int:
        return self._interleave
    @interleave.setter
    def interleave(self, interleave: int):
        try:
            self._interleave = int(interleave)
            if self._interleave not in (1, 3):
                raise ValueError
        except ValueError:
            raise error.Fatal("SONY1DD: interleave must be 1 or 3: '%s'"
                              % interleave)


class SONY1DD(D88):

    default_format = 'sony.1dd'

    def __init__(self, name: str, _fmt):
        super().__init__(name, _fmt)
        self.opts = SONY1DDOpts()

    @staticmethod
    def disk_from_file(f, disk_offset: int, opts=None) -> TrackDict:
        il = opts.interleave if opts is not None else 3
        f.seek(disk_offset)
        to_track: TrackDict = dict()

        header = struct.unpack('<16sB9xBBL', f.read(32))
        _, _, _, _, disk_size = header
        track_table = list(struct.unpack('<160L', f.read(640)))
        s_off = min(filter(lambda x: x != 0, track_table), default=672)
        if s_off == 688:
            track_table.extend(list(struct.unpack('<4L', f.read(16))))
        elif s_off != 672:
            raise error.Fatal("D88: Unsupported track table length.")

        for cyl, track_offset in enumerate(track_table):
            if track_offset == 0:
                continue
            f.seek(disk_offset + track_offset)
            if f.tell() >= disk_offset + disk_size:
                continue
            # media_flag 0x00 selects 250kbit/s (MFM) at 300rpm.
            t = D88.track_from_file(f, cyl, 0, 0x00,
                                    reorder=lambda secs: interleave_sectors(secs, il))
            if t is not None:
                to_track[cyl, 0] = t

        return to_track

# Local variables:
# python-indent: 4
# End:
