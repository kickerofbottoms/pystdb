
import argparse
import logging
import os
import struct

UTF_16 = 'UTF-16-LE'

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


class DBError(Exception):
    pass


class Table(object):
    block_size = 512

    def __init__(self, db, offset):
        self.db = db
        self.offset = offset

    def __repr__(self):
        return '<{} instance at 0x{:x} with {}>'.format(
            type(self).__name__, id(self), self.fields_)

    def __nonzero__(self):
        return not self.empty_

    @property
    def fields_(self):
        it = vars(type(self)).iteritems()
        return {k: getattr(self, k) for k, v in it if isinstance(v, Field)}

    @property
    def empty_(self):
        return not any(self.fields_.itervalues())


class Field(object):
    def __init__(self, format_, offset, to_py=lambda x: x, to_db=lambda x: x):
        self.struct = struct.Struct(format_)
        self.offset = offset
        self.size = self.struct.size
        self.to_py = to_py
        self.to_db = to_db

    def __get__(self, table, owner):
        table.db.seek(table.offset + self.offset)
        value = self.struct.unpack(table.db.read(self.size))
        value = self.to_py(value)
        if len(value) == 1:
            value = value[0]
        return value

    def __set__(self, instance, value):
        raise NotImplementedError()

    def __delete__(self, instance):
        raise NotImplementedError()

    @staticmethod
    def wchar_to_str(items, n=64):
        result = []
        for b in items:
            for i in xrange(0, len(b), n):
                c = ''.join(b[i:i+n])
                s = c.decode(UTF_16)
                result.append(s.rstrip('\0'))
        return tuple(result)

    @staticmethod
    def str_to_wchar(s, n=64):
        raise NotImplementedError()


class Header(Table):
    """
    int32   magic               always 0x01 0x00 0x00 0x00
    int32   count_albums
    int32   next_album_id
    int32   album_ids[100]
    int32   next_track_id
    char    padding[96]
    """
    magic = Field('I', 0)
    count_albums = Field('I', 4)
    next_album_id = Field('I', 8)
    album_ids = Field('100I', 12)
    next_track_id = Field('I', 412)


class Album(Table):
    """
    int32   magic               always 0x71 0x13 0x02 0x00
    int32   album_id
    int32   count_tracks
    int32   track_group_ids[84]
    int32   album_length        in ms
    wchar   album_name[64]      Unicode string
    char    padding[64]
    """
    magic = Field('I', 0)
    album_id = Field('I', 4)
    count_tracks = Field('I', 8)
    track_group_ids = Field('84I', 12)
    album_length = Field('I', 348)
    album_name = Field('64sx', 352,
                       to_py=Field.wchar_to_str,
                       to_db=Field.str_to_wchar)


class TrackGroup(Table):
    """
    int32   magic               always 0x73 0x10 0x03 0x00
    int32   album_id
    int32   track_group_id
    int32   padding             why is this not null?
    int32   track_ids[6]
    int32   track_lengths[6]    in ms
    wchar   track_names[64][6]
    char    padding[64]
    """
    magic = Field('I', 0)
    album_id = Field('I', 4)
    track_group_id = Field('I', 8)
    padding = Field('x', 12)
    track_ids = Field('6I', 16)
    track_lengths = Field('6I', 40)
    track_names = Field('384s', 64,
                        to_py=Field.wchar_to_str,
                        to_db=Field.str_to_wchar)


class STDB(object):
    def __init__(self, path):
        self.f = None
        self.path = path
        self.root = os.path.dirname(path)

        self._header = None

    def __enter__(self):
        return self.open(self.path)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.f.close()

    def assert_open(self):
        if not self.f:
            raise IOError('database not open for reading')

    def open(self, mode='rb'):
        self.f = open(self.path, mode)
        return self

    def close(self):
        self.assert_open()
        self.f.close()

    def seek(self, *args, **kwargs):
        self.assert_open()
        return self.f.seek(*args, **kwargs)

    def read(self, *args, **kwargs):
        self.assert_open()
        return self.f.read(*args, **kwargs)

    def tell(self):
        self.assert_open()
        return self.f.tell()

    @property
    def size(self):
        pos = self.tell()
        self.seek(0, 2)
        size = self.tell()
        self.seek(pos)
        return size

    @property
    def header(self):
        if not self._header:
            self._header = Header(self, 0)
        return self._header

    @property
    def albums(self):
        return tuple(self.iter_albums())

    def iter_albums(self):
        start = Header.block_size
        stop = start + self.header.count_albums * Album.block_size
        step = Album.block_size
        for offset in xrange(start, stop, step):
            yield Album(self, offset)

    @property
    def track_groups(self):
        return tuple(self.iter_track_groups())

    def iter_track_groups(self):
        start = Header.block_size + 100 * Album.block_size
        stop = self.size  # eof
        step = TrackGroup.block_size
        for offset in xrange(start, stop, step):
            yield TrackGroup(self, offset)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('db_path')
    args = parser.parse_args()

    with STDB(args.db_path) as db:
        print 'Database: {}'.format(db.path)
        print 'Header:\n{}'.format(db.header.fields_)
        for album in db.iter_albums():
            print '  {:02d}: {}'.format(album.album_id, album.album_name)
            group_ids = album.track_group_ids

            # todo: integrate iteration logic into classes
            for i, gid in enumerate(group_ids, group_ids[0]):
                if i != gid:
                    break
                group = db.track_groups[gid]
                for track_info in zip(group.track_ids,
                                      group.track_names,
                                      group.track_lengths):
                    print '    {:02d}: {} ({})'.format(*track_info)

    return 0


if __name__ == '__main__':
    main()
