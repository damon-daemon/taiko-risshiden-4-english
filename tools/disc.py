"""The disc this patch is for: Taiko Risshiden IV (Japan), SLPM-62105, PS2 CD."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERIAL = 'SLPM-62105'
ELF = 'SLPM_621.05'
DATA = 'TR4DATA.DAT'
CLEAN = os.path.join(ROOT, 'taiko_risshiden_4.bin')
CLEAN_SHA1 = 'c932ea1de4247240a2868064f9deb21bc53cba30'
CLEAN_SIZE = 455224896
CLEAN_CRC32 = '40c1be2b'
CLEAN_MD5 = '56a6636542bf2ad9e256cf0a1f83f876'

def extract(name):
    """Path of a file extracted from the clean disc (extract/, git-ignored; dev tools)."""
    return os.path.join(ROOT, 'extract', name)
