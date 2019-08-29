
import struct
import os
import logging

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
            type(self).__name__, id(self), self.fields)

    @property
    def fields(self):
        attrs = vars(type(self)).iterkeys()
        return {k: getattr(self, k) for k in attrs if not k.startswith('_')}


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
    def wchar_to_str(b):
        s = ''.join(b).decode(UTF_16)
        return s.rstrip('\0')

    @staticmethod
    def str_to_wchar(s, pad=64):
        raise NotImplementedError()
        b = s.encode(UTF_16)
        while len(b) < pad:
            b += '\0'.encode(UTF_16)  # todo: encode once
        return b  # todo: test padding


class Header(Table):
    magic = Field('I', 0)
    count_albums = Field('I', 4)
    next_album_id = Field('I', 8)
    album_ids = Field('100I', 12)
    next_track_id = Field('I', 412)


class Album(Table):
    magic = Field('I', 0)
    album_id = Field('I', 4)
    count_tracks = Field('I', 8)
    track_group_ids = Field('84I', 12)
    album_length = Field('I', 348)
    album_name = Field('64sx', 352,
                       to_py=Field.wchar_to_str,
                       to_db=Field.str_to_wchar)


class TrackGroup(Table):
    magic = Field('I', 0)
    album_id = Field('I', 4)
    track_group_id = Field('I', 8)
    padding = Field('x', 12)
    track_ids = Field('6I', 16)
    track_lengths = Field('6I', 40)
    # track_names = Field('384s', 40,
    #                     to_py=Field.wchar_to_str,
    #                     to_db=Field.str_to_wchar)


class STDB:
    block_size = 512

    def __init__(self, path):
        self.f = open(path, 'rb')
        self.path = path
        self.root = os.path.dirname(path)

        self.seek(0, 2)
        self.size = self.tell()
        self.seek(0)

        self.header = Header(self, 0)
        log.debug(self.header)

        self.albums = tuple(self.iter_albums())
        log.debug(self.albums)

        self.track_groups = tuple(self.iter_track_groups())
        log.debug(self.track_groups)

    def iter_albums(self):
        start = self.block_size
        stop = start + self.header.count_albums * self.block_size
        step = self.block_size
        for offset in xrange(start, stop, step):
            yield Album(self, offset)

    def iter_track_groups(self):
        start = 101 * self.block_size  # header + 100 soundtracks
        stop = self.size  # eof
        step = self.block_size
        for offset in xrange(start, stop, step):
            yield TrackGroup(self, offset)

    def seek(self, *args, **kwargs):
        return self.f.seek(*args, **kwargs)

    def read(self, *args, **kwargs):
        return self.f.read(*args, **kwargs)

    def tell(self):
        return self.f.tell()


def main():
    db = STDB(r'/Users/greg/Scripts/pystdb/data/fffe0000/music/ST.DB')

    print 'Database: {}'.format(db.path)

    return 0


if __name__ == '__main__':
    main()
