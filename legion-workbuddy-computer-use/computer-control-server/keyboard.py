"""
键盘控制模块 — 使用 ctypes + Win32 SendInput API
支持 Unicode 文字输入、组合键、按住+点按
"""

import time
import ctypes
from win32_defs import (
    INPUT, INPUT_KEYBOARD, KEYBDINPUT,
    KEYEVENTF_KEYDOWN, KEYEVENTF_KEYUP,
    KEYEVENTF_UNICODE, KEYEVENTF_SCANCODE,
    MODIFIER_KEYS, get_vk, user32,
)


def _send_keyboard_input(wVk=0, wScan=0, dwFlags=0):
    """发送单个键盘输入事件"""
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.union.ki = KEYBDINPUT(
        wVk=wVk,
        wScan=wScan,
        dwFlags=dwFlags,
        time=0,
        dwExtraInfo=None,
    )
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def type_text(text, delay_ms=20):
    """
    逐字符输入文字（支持 Unicode）。

    使用 KEYEVENTF_UNICODE 模式，支持中文、emoji 等。
    每个字符之间有 delay_ms 毫秒延迟，防止输入过快。
    """
    for ch in text:
        code_point = ord(ch)

        # BMP 字符 (U+0000 ~ U+FFFF)
        if code_point <= 0xFFFF:
            _send_keyboard_input(wScan=code_point, dwFlags=KEYEVENTF_UNICODE)
            _send_keyboard_input(wScan=code_point, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
        else:
            # 补充平面字符 (U+10000 ~ U+10FFFF)，使用 UTF-16 代理对
            surrogate = ch.encode("utf-16-le")
            for i in range(0, len(surrogate), 2):
                lo = surrogate[i]
                hi = surrogate[i + 1]
                code_unit = lo | (hi << 8)
                _send_keyboard_input(wScan=code_unit, dwFlags=KEYEVENTF_UNICODE)
                _send_keyboard_input(wScan=code_unit, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)

        time.sleep(delay_ms / 1000.0)


def press_keys(keys, hold_ms=80):
    """
    按组合键。例如 press_keys(["ctrl", "c"]) 发送 Ctrl+C。

    顺序：
    1. 按顺序按下所有键
    2. 等待 hold_ms 毫秒
    3. 逆序松开所有键
    """
    # 分离修饰键和普通键
    normal_keys = []
    modifier_keys = []

    for key in keys:
        if key.lower() in MODIFIER_KEYS:
            modifier_keys.append(key)
        else:
            normal_keys.append(key)

    # 1. 按下所有修饰键
    for key in modifier_keys:
        vk = get_vk(key)
        _send_keyboard_input(wVk=vk, dwFlags=KEYEVENTF_KEYDOWN)

    # 2. 按下普通键（一个一个按）
    for key in normal_keys:
        vk = get_vk(key)
        _send_keyboard_input(wVk=vk, dwFlags=KEYEVENTF_KEYDOWN)

    time.sleep(hold_ms / 1000.0)

    # 3. 松开普通键（逆序）
    for key in reversed(normal_keys):
        vk = get_vk(key)
        _send_keyboard_input(wVk=vk, dwFlags=KEYEVENTF_KEYUP)

    # 4. 松开修饰键（逆序）
    for key in reversed(modifier_keys):
        vk = get_vk(key)
        _send_keyboard_input(wVk=vk, dwFlags=KEYEVENTF_KEYUP)


def hold_and_tap(hold_keys, tap_key, hold_ms=100):
    """
    按住修饰键，点按一个键，再松开修饰键。
    用于需要长按修饰键的场景，如 Ctrl+Shift+Right。
    """
    # 按下所有 hold 键
    for key in hold_keys:
        vk = get_vk(key)
        _send_keyboard_input(wVk=vk, dwFlags=KEYEVENTF_KEYDOWN)

    time.sleep(0.03)

    # 点按 tap 键
    vk = get_vk(tap_key)
    _send_keyboard_input(wVk=vk, dwFlags=KEYEVENTF_KEYDOWN)
    time.sleep(hold_ms / 1000.0)
    _send_keyboard_input(wVk=vk, dwFlags=KEYEVENTF_KEYUP)

    time.sleep(0.03)

    # 逆序松开 hold 键
    for key in reversed(hold_keys):
        vk = get_vk(key)
        _send_keyboard_input(wVk=vk, dwFlags=KEYEVENTF_KEYUP)
