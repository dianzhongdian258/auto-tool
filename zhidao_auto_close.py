"""
知到 App 弹窗自动关闭工具

功能：自动检测"知到"桌面客户端课程视频中弹出的答题弹窗，
      点击第一个选项后关闭弹窗，实现无人值守观看。

原理：
  1. 用 dxcam 截屏（支持硬件加速渲染的窗口）
  2. 用 RapidOCR 识别屏幕文字，定位"关闭"和"单选题/多选题/判断题"确定弹窗边界
  3. 在弹窗区域内用像素亮度扫描找到第一个灰白色选项条（亮度 230-252）
  4. 用 Win32 SetCursorPos + SendInput 发送鼠标点击（需管理员权限）

用法：
  pip install -r requirements.txt
  python zhidao_auto_close.py

  程序启动后有 5 秒倒计时，请在此期间切换到知到 App 全屏。
  按 Ctrl+C 退出。
"""

import ctypes
import sys
import time
import numpy as np
from ctypes import wintypes, Structure, Union, sizeof


# ===================== 管理员提权 =====================

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


if not is_admin():
    print("正在请求管理员权限...", flush=True)
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )
    sys.exit(0)


# ===================== 初始化 =====================

print("=" * 50, flush=True)
print("知到弹窗自动关闭工具 (管理员模式)", flush=True)
print("=" * 50, flush=True)

print("\n正在加载模块...", flush=True)
import dxcam
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

print("正在初始化截屏引擎...", flush=True)
camera = dxcam.create()
print("正在加载 OCR 引擎（首次可能需要 10-30 秒）...", flush=True)
ocr_engine = RapidOCR()
print("加载完成！\n", flush=True)

STARTUP_DELAY = 5
CHECK_INTERVAL = 2


# ===================== Win32 鼠标点击 =====================

INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class MOUSEINPUT(Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


def send_click(x, y):
    """移动鼠标到 (x, y) 并左键单击"""
    ctypes.windll.user32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    down = INPUT()
    down.type = INPUT_MOUSE
    down.union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
    up = INPUT()
    up.type = INPUT_MOUSE
    up.union.mi.dwFlags = MOUSEEVENTF_LEFTUP
    ctypes.windll.user32.SendInput(1, ctypes.byref(down), sizeof(INPUT))
    time.sleep(0.05)
    ctypes.windll.user32.SendInput(1, ctypes.byref(up), sizeof(INPUT))


# ===================== 弹窗检测 =====================

def find_popup_bounds(ocr_results):
    """用 OCR 结果定位弹窗边界，返回边界字典或 None"""
    if not ocr_results:
        return None

    close_info = None
    question_info = None

    for box, text, confidence in ocr_results:
        if confidence < 0.3:
            continue
        t = text.strip()
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        info = {
            "cx": int((min(xs) + max(xs)) / 2),
            "cy": int((min(ys) + max(ys)) / 2),
            "left": int(min(xs)), "right": int(max(xs)),
            "top": int(min(ys)), "bottom": int(max(ys)),
        }

        if "关闭" in t:
            close_info = info
        if any(kw in t for kw in ("单选题", "多选题", "判断题")):
            question_info = info

    if close_info and question_info:
        return {
            "left": question_info["left"] - 20,
            "right": close_info["right"] + 20,
            "top": min(close_info["top"], question_info["top"]) - 10,
            "question_bottom": question_info["bottom"],
            "close_cx": close_info["cx"],
            "close_cy": close_info["cy"],
        }
    return None


def find_first_option_row(pixels, popup):
    """在弹窗区域内扫描像素亮度，找到第一个灰白色选项条的中心坐标"""
    h, w = pixels.shape[:2]

    p_left = max(0, popup["left"])
    p_right = min(w, popup["right"])
    scan_x = p_right - 150
    if scan_x < p_left:
        scan_x = (p_left + p_right) // 2

    start_y = popup["question_bottom"] + 20
    end_y = min(h, popup["top"] + int((p_right - p_left) * 0.9))

    half_strip = 10
    x_lo = max(0, scan_x - half_strip)
    x_hi = min(w, scan_x + half_strip)

    bands = []
    in_band = False
    band_start = 0

    for y in range(start_y, end_y):
        brightness = float(np.mean(pixels[y, x_lo:x_hi]))

        if 230 <= brightness <= 252:
            if not in_band:
                band_start = y
                in_band = True
        else:
            if in_band:
                if y - band_start >= 50:
                    bands.append((band_start, y))
                in_band = False

    if in_band and end_y - band_start >= 50:
        bands.append((band_start, end_y))

    if bands:
        cy = (bands[0][0] + bands[0][1]) // 2
        cx = (p_left + p_right) // 2
        return (cx, cy)
    return None


# ===================== 截屏 =====================

def grab_screen():
    """用 dxcam 截取一帧屏幕，返回 PIL Image 或 None"""
    frame = camera.grab()
    if frame is None:
        time.sleep(0.1)
        frame = camera.grab()
    if frame is None:
        return None
    return Image.fromarray(frame)


# ===================== 主循环 =====================

def main():
    print(f"程序将在 {STARTUP_DELAY} 秒后开始监测，请切换到知到 App 全屏...", flush=True)
    for i in range(STARTUP_DELAY, 0, -1):
        print(f"  {i}...", flush=True)
        time.sleep(1)
    print("开始监测弹窗 (按 Ctrl+C 退出)\n", flush=True)

    scan_count = 0
    while True:
        try:
            scan_count += 1
            img = grab_screen()
            if img is None:
                if scan_count % 5 == 1:
                    print(f"[扫描 #{scan_count}] 截屏失败", flush=True)
                time.sleep(CHECK_INTERVAL)
                continue

            results, _ = ocr_engine(img)

            if scan_count % 5 == 1:
                c = len(results) if results else 0
                print(f"[扫描 #{scan_count}] OCR={c}条", flush=True)

            if not results:
                time.sleep(CHECK_INTERVAL)
                continue

            popup = find_popup_bounds(results)
            if not popup:
                time.sleep(CHECK_INTERVAL)
                continue

            pixels = np.array(img)
            option_pos = find_first_option_row(pixels, popup)
            if not option_pos:
                time.sleep(CHECK_INTERVAL)
                continue

            print(f"\n[检测到弹窗!]", flush=True)
            print(f"  -> 点击选项 ({option_pos[0]}, {option_pos[1]})", flush=True)
            send_click(option_pos[0], option_pos[1])
            time.sleep(1.0)

            print(f"  -> 点击关闭 ({popup['close_cx']}, {popup['close_cy']})", flush=True)
            send_click(popup["close_cx"], popup["close_cy"])
            print("  -> 弹窗已处理\n", flush=True)

            time.sleep(3)

        except KeyboardInterrupt:
            print("\n已退出监测。", flush=True)
            break
        except Exception as e:
            print(f"[错误] {e}", flush=True)
            time.sleep(CHECK_INTERVAL)

    del camera


if __name__ == "__main__":
    main()
