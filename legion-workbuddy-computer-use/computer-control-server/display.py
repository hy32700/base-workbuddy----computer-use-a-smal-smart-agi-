"""Set DPI awareness BEFORE either capture or mouse APIs are used."""

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL('user32', use_last_error=True)
user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
user32.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
user32.GetAwarenessFromDpiAwarenessContext.argtypes = [ctypes.c_void_p]
user32.GetAwarenessFromDpiAwarenessContext.restype = ctypes.c_int


def ensure_physical_pixels():
    if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
        return
    context = user32.GetThreadDpiAwarenessContext()
    if user32.GetAwarenessFromDpiAwarenessContext(context) != 2:
        raise RuntimeError('Per-monitor DPI awareness is required; restart the MCP server')


ensure_physical_pixels()


class MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]


def monitors():
    result = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE,
                                       wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                           callback_type, wintypes.LPARAM]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL

    def collect(handle, hdc, rect, data):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            r = info.rcMonitor
            result.append({'x': r.left, 'y': r.top, 'width': r.right - r.left,
                           'height': r.bottom - r.top, 'primary': bool(info.dwFlags & 1)})
        return True

    if not user32.EnumDisplayMonitors(None, None, callback_type(collect), 0) or not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return sorted(result, key=lambda m: (not m['primary'], m['x'], m['y']))
