"""
Protects Gmail App Passwords at rest.

On Windows the secret is encrypted with DPAPI (bound to the current Windows
user account).  Elsewhere it falls back to base64 obfuscation.
"""
import base64
import sys

_PREFIX_DPAPI = "dpapi:"
_PREFIX_B64 = "b64:"


def _dpapi(data: bytes, encrypt: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    fn = crypt32.CryptProtectData if encrypt else crypt32.CryptUnprotectData
    if not fn(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise OSError("DPAPI operation failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def protect(secret: str) -> str:
    if not secret:
        return ""
    raw = secret.encode("utf-8")
    if sys.platform == "win32":
        try:
            return _PREFIX_DPAPI + base64.b64encode(_dpapi(raw, True)).decode("ascii")
        except Exception:
            pass
    return _PREFIX_B64 + base64.b64encode(raw).decode("ascii")


def reveal(stored: str) -> str:
    if not stored:
        return ""
    if stored.startswith(_PREFIX_DPAPI):
        return _dpapi(base64.b64decode(stored[len(_PREFIX_DPAPI):]), False).decode("utf-8")
    if stored.startswith(_PREFIX_B64):
        return base64.b64decode(stored[len(_PREFIX_B64):]).decode("utf-8")
    return stored  # legacy plaintext


def normalize_app_password(pw: str) -> str:
    """Google shows App Passwords as 'abcd efgh ijkl mnop' — store without spaces."""
    return "".join((pw or "").split())


def is_valid_app_password(pw: str) -> bool:
    p = normalize_app_password(pw)
    return len(p) == 16 and p.isalnum()
