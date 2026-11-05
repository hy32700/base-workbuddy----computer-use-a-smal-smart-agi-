"""
鼠标控制模块 — 使用 ctypes + Win32 SendInput API
支持移动、点击、双击、拖拽、滚轮
"""

import time
import ctypes
from win32_defs import (
    INPUT, INPUT_MOUSE, MOUSEINPUT, POINT,
    MOUSEEVENTF_MOVE, MOUSEEVENTF_ABSOLUTE,
    MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP,
    MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP,
    MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP,
    MOUSEEVENTF_WHEEL,
    user32,
)


def _send_mouse_input(dwFlags, dx=0, dy=0, mouseData=0):
    """发送单个鼠标输入事件"""
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.union.mi = MOUSEINPUT(
        dx=dx,
        dy=dy,
        mouseData=mouseData,
        dwFlags=dwFlags,
        time=0,
        dwExtraInfo=None,
    )
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def get_position():
    """获取当前鼠标位置，返回 (x, y)"""
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)


def move_to(x, y, speed="smooth"):
    """
    移动鼠标到 (x, y)。

    speed="smooth": 平滑移动（约 200ms，分步移动）
    speed="instant": 瞬间移动
    """
    if speed == "instant":
        user32.SetCursorPos(x, y)
        return

    # 平滑移动
    start_x, start_y = get_position()
    steps = 40
    duration = 0.2  # 200ms
    delay = duration / steps

    for i in range(1, steps + 1):
        t = i / steps
        # ease-out 缓动
        eased = 1 - (1 - t) ** 3
        cur_x = int(start_x + (x - start_x) * eased)
        cur_y = int(start_y + (y - start_y) * eased)
        user32.SetCursorPos(cur_x, cur_y)
        time.sleep(delay)


def click(button="left"):
    """点击鼠标（当前光标位置）"""
    down_flags = {
        "left": MOUSEEVENTF_LEFTDOWN,
        "right": MOUSEEVENTF_RIGHTDOWN,
        "middle": MOUSEEVENTF_MIDDLEDOWN,
    }
    up_flags = {
        "left": MOUSEEVENTF_LEFTUP,
        "right": MOUSEEVENTF_RIGHTUP,
        "middle": MOUSEEVENTF_MIDDLEUP,
    }
    btn = button.lower()
    if btn not in down_flags:
        raise ValueError(f"无效的鼠标按钮: {button}，可选: left/right/middle")

    _send_mouse_input(down_flags[btn])
    time.sleep(0.03)
    _send_mouse_input(up_flags[btn])


def double_click():
    """双击左键"""
    click("left")
    time.sleep(0.05)
    click("left")


def drag(x1, y1, x2, y2):
    """
    从 (x1, y1) 拖拽到 (x2, y2)。
    先移动到起点，按下左键，平滑移动到终点，释放。
    """
    move_to(x1, y1, speed="instant")
    time.sleep(0.05)
    _send_mouse_input(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.05)
    move_to(x2, y2, speed="smooth")
    time.sleep(0.05)
    _send_mouse_input(MOUSEEVENTF_LEFTUP)


def scroll(direction="down", amount=3):
    """
    滚轮滚动。
    direction: "up" 或 "down"
    amount: 滚动"格数"（WHEEL_DELTA=120 单位/格）
    """
    delta = 120 * amount
    if direction.lower() == "down":
        delta = -delta
    _send_mouse_input(MOUSEEVENTF_WHEEL, mouseData=delta)


def click_at(x, y, button="left"):
    """移动到 (x,y) 然后点击"""
    move_to(x, y, speed="smooth")
    time.sleep(0.05)
    click(button)
