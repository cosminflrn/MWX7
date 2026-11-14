#!/usr/bin/python3
"""Self-check of the product-name reader behind "Run Windows programs" (lib/mwx7pe.py): builds a minimal PE file in memory (PE32
and PE32+, one .rsrc section holding a version resource), and checks ProductName, the FileDescription fallback, the file-name
fallback and that junk never raises. No display needed. Run: python3 distro/tests/test_pe_name.py"""
import importlib.util
import os
import struct
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'desktop', 'overlay', 'usr', 'share', 'mwx7', 'lib', 'mwx7pe.py')
spec = importlib.util.spec_from_file_location('mwx7pe_under_test', SRC)
pe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pe)


def u16(s):
    return s.encode('utf-16-le') + b'\0\0'


def string_entry(key, value):
    k = u16(key)
    hdr = struct.pack('<HHH', 0, len(value) + 1, 1) + k   # wLength (unused by the reader), wValueLength, wType=text
    hdr += b'\0' * ((-len(hdr)) % 4)
    return hdr + u16(value) + b'\0' * ((-(len(hdr) + len(u16(value)))) % 4)


def version_blob(**strings):
    body = b''.join(string_entry(k, v) for k, v in strings.items())
    return struct.pack('<HHH', 0, 0, 0) + u16('VS_VERSION_INFO') + b'\0\0' + body


def build_pe(blob, plus=False):
    """DOS header, PE header, one section .rsrc at RVA 0x1000 (file offset 0x400): type 16 -> id 1 -> lang 0x409 -> data."""
    dos = b'MZ' + b'\0' * 58 + struct.pack('<I', 0x40)
    opt_size = 240 if plus else 224
    opt = struct.pack('<H', 0x20b if plus else 0x10b).ljust(opt_size, b'\0')
    dd = 112 if plus else 96
    opt = opt[:dd + 16] + struct.pack('<II', 0x1000, 0x400) + opt[dd + 24:]
    coff = b'PE\0\0' + struct.pack('<HHIIIHH', 0x8664 if plus else 0x14c, 1, 0, 0, 0, opt_size, 0x102)
    sect = b'.rsrc\0\0\0' + struct.pack('<IIIIIIHHI', 0x400, 0x1000, 0x400, 0x400, 0, 0, 0, 0, 0x40000040)

    def directory(rows):
        return b'\0' * 12 + struct.pack('<HH', 0, len(rows)) + b''.join(struct.pack('<II', i, t) for i, t in rows)
    data_off = 0x48
    res = directory([(16, 0x80000018)])                          # at 0x00: root -> type dir at 0x18
    res += directory([(1, 0x80000030)])                          # at 0x18: type 16 -> name dir at 0x30
    res += directory([(0x409, data_off - 0x0)])                  # at 0x30: name 1 -> language data entry at 0x48
    res = res.ljust(0x48, b'\0') + struct.pack('<IIII', 0x1060, len(blob), 0, 0)
    res = res.ljust(0x60, b'\0') + blob
    return (dos + coff + opt + sect).ljust(0x400, b'\0') + res.ljust(0x400, b'\0')


class PeName(unittest.TestCase):
    def name(self, data):
        with tempfile.NamedTemporaryFile(suffix='.exe', delete=False) as f:
            f.write(data)
        try:
            return pe.product_name(f.name)
        finally:
            os.unlink(f.name)

    def test_product_name_pe32_and_pe32plus(self):
        blob = version_blob(CompanyName='Example Co', ProductName='Example Writer', FileDescription='Writer setup')
        self.assertEqual(self.name(build_pe(blob)), 'Example Writer')
        self.assertEqual(self.name(build_pe(blob, plus=True)), 'Example Writer')

    def test_unicode_and_description_fallback(self):
        self.assertEqual(self.name(build_pe(version_blob(ProductName='Café Köln'))), 'Café Köln')
        self.assertEqual(self.name(build_pe(version_blob(FileDescription='Tiny Tool'))), 'Tiny Tool')

    def test_not_a_pe_never_raises(self):
        good = build_pe(version_blob(ProductName='X'))
        for junk in (b'', b'MZ', b'hello world', good[:0x50], good[:0x300], b'MZ' + b'\xff' * 100):
            self.assertIsNone(self.name(junk))
        self.assertIsNone(pe.product_name('/nonexistent/file.exe'))

    def test_file_name_fallback(self):
        self.assertEqual(pe.name_from_file('/home/u/Downloads/Notepad++_Setup-v8.6.2_x64.exe'), 'Notepad++')
        self.assertEqual(pe.name_from_file('VLC-media-player-3.0.20-win64.exe'), 'VLC media player')
        self.assertEqual(pe.name_from_file('setup.exe'), 'setup')
        self.assertEqual(pe.program_name('/nonexistent/Foo_Bar.msi'), 'Foo Bar')


if __name__ == '__main__':
    unittest.main()
