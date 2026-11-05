"""
Win32 API 定义：结构体、常量、虚拟键码映射表
用于鼠标/键盘控制，纯 ctypes 实现，无外部依赖
"""

import ctypes
from ctypes import wintypes
from display import ensure_physical_pixels

ensure_physical_pixels()

# ── 常量 ──────────────────────────────────────────────

# 输入类型
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

# 鼠标事件标志
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000

# 键盘事件标志
KEYEVENTF_KEYDOWN = 0x0000
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_EXTENDEDKEY = 0x0001

# 系统指标
SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

# ── 结构体 ────────────────────────────────────────────

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUT_UNION),
    ]


class POINT(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


# ── 虚拟键码映射表 ─────────────────────────────────────

# Windows Virtual-Key Codes
# https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes

VK_CODE = {
    # 鼠标
    "left_button": 0x01,
    "right_button": 0x02,
    "middle_button": 0x04,
    # 控制键
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "caps_lock": 0x14,
    "escape": 0x1B,
    "esc": 0x1B,
    "space": 0x20,
    "spacebar": 0x20,
    "page_up": 0x21,
    "pgup": 0x21,
    "page_down": 0x22,
    "pgdn": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "print_screen": 0x2C,
    "prtsc": 0x2C,
    "insert": 0x2D,
    "ins": 0x2D,
    "delete": 0x2E,
    "del": 0x2E,
    # 数字键 0-9
    "0": 0x30,
    "1": 0x31,
    "2": 0x32,
    "3": 0x33,
    "4": 0x34,
    "5": 0x35,
    "6": 0x36,
    "7": 0x37,
    "8": 0x38,
    "9": 0x39,
    # 字母键 A-Z
    "a": 0x41,
    "b": 0x42,
    "c": 0x43,
    "d": 0x44,
    "e": 0x45,
    "f": 0x46,
    "g": 0x47,
    "h": 0x48,
    "i": 0x49,
    "j": 0x4A,
    "k": 0x4B,
    "l": 0x4C,
    "m": 0x4D,
    "n": 0x4E,
    "o": 0x4F,
    "p": 0x50,
    "q": 0x51,
    "r": 0x52,
    "s": 0x53,
    "t": 0x54,
    "u": 0x55,
    "v": 0x56,
    "w": 0x57,
    "x": 0x58,
    "y": 0x59,
    "z": 0x5A,
    # Windows 键
    "win": 0x5B,
    "windows": 0x5B,
    "left_win": 0x5B,
    "right_win": 0x5C,
    "apps": 0x5D,  # 菜单键
    # 小键盘
    "numpad_0": 0x60,
    "numpad_1": 0x61,
    "numpad_2": 0x62,
    "numpad_3": 0x63,
    "numpad_4": 0x64,
    "numpad_5": 0x65,
    "numpad_6": 0x66,
    "numpad_7": 0x67,
    "numpad_8": 0x68,
    "numpad_9": 0x69,
    "numpad_multiply": 0x6A,
    "numpad_add": 0x6B,
    "numpad_separator": 0x6C,
    "numpad_subtract": 0x6D,
    "numpad_decimal": 0x6E,
    "numpad_divide": 0x6F,
    # 功能键
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
    "f13": 0x7C,
    "f14": 0x7D,
    "f15": 0x7E,
    "f16": 0x7F,
    "f17": 0x80,
    "f18": 0x81,
    "f19": 0x82,
    "f20": 0x83,
    "f21": 0x84,
    "f22": 0x85,
    "f23": 0x86,
    "f24": 0x87,
    # 其他
    "num_lock": 0x90,
    "scroll_lock": 0x91,
    "left_shift": 0xA0,
    "right_shift": 0xA1,
    "left_ctrl": 0xA2,
    "right_ctrl": 0xA3,
    "left_alt": 0xA4,
    "right_alt": 0xA5,
    # 浏览器键
    "browser_back": 0xA6,
    "browser_forward": 0xA7,
    "browser_refresh": 0xA8,
    "browser_stop": 0xA9,
    "browser_search": 0xAA,
    "browser_favorites": 0xAB,
    "browser_home": 0xAC,
    # 媒体键
    "volume_mute": 0xAD,
    "volume_down": 0xAE,
    "volume_up": 0xAF,
    "media_next": 0xB0,
    "media_prev": 0xB1,
    "media_stop": 0xB2,
    "media_play_pause": 0xB3,
    # 符号键（通过 char_to_vk 更准确，此为备用）
    ";": 0xBA,
    "=": 0xBB,
    ",": 0xBC,
    "-": 0xBD,
    ".": 0xBE,
    "/": 0xBF,
    "`": 0xC0,
    "[": 0xDB,
    "\\": 0xDC,
    "]": 0xDD,
    "'": 0xDE,
}

# 修饰键列表（按发送顺序）
MODIFIER_KEYS = {"shift", "ctrl", "control", "alt", "win", "windows",
                 "left_shift", "right_shift", "left_ctrl", "right_ctrl",
                 "left_alt", "right_alt", "left_win", "right_win"}


def char_to_vk(char: str) -> int:
    """将字符转换为虚拟键码（通过 Win32 VkKeyScanW）"""
    result = ctypes.windll.user32.VkKeyScanW(ord(char))
    return result & 0xFF  # 低 8 位是虚拟键码


def get_vk(key: str) -> int:
    """
    获取键的虚拟键码。
    先查映射表，再尝试 char_to_vk，最后尝试单字符。
    """
    key_lower = key.lower()
    if key_lower in VK_CODE:
        return VK_CODE[key_lower]

    # 单字符符号（如 '@', '#', '$' 等）
    if len(key) == 1:
        return char_to_vk(key)

    raise ValueError(f"未知的键名: {key}")


# ── 加载 user32 函数 ──────────────────────────────────

# 使用 argtypes/restype 确保类型安全
user32 = ctypes.windll.user32

# SetCursorPos
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = ctypes.c_bool

# GetCursorPos
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = ctypes.c_bool

# SendInput
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

# GetSystemMetrics
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int

# GetForegroundWindow
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND

# SetForegroundWindow
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = ctypes.c_bool
