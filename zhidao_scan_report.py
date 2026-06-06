"""
知到弹窗特征扫描与报告工具

功能：截屏后对弹窗进行 OCR 识别和像素颜色扫描，
      生成详细的特征报告文件，用于调试和调整检测参数。

用法：
  python zhidao_scan_report.py

  程序启动后有 5 秒倒计时，请让知到弹窗显示在屏幕上。
  结果保存到当前目录下：
    - zhidao_screenshot.png  截图
    - zhidao_report.txt      特征报告
"""

import ctypes
import sys
import time
import numpy as np


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


print("=" * 50, flush=True)
print("知到弹窗特征扫描工具 (管理员模式)", flush=True)
print("=" * 50, flush=True)

print("\n正在加载模块...", flush=True)
import dxcam
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

camera = dxcam.create()
print("正在加载 OCR 引擎（首次可能需要 10-30 秒）...", flush=True)
ocr_engine = RapidOCR()
print("加载完成！\n", flush=True)

print("5 秒后截屏，请让知到弹窗显示在屏幕上...", flush=True)
for i in range(5, 0, -1):
    print(f"  {i}...", flush=True)
    time.sleep(1)

frame = camera.grab()
if frame is None:
    time.sleep(0.3)
    frame = camera.grab()
if frame is None:
    print("截屏失败！", flush=True)
    del camera
    sys.exit(1)

img = Image.fromarray(frame)
img.save("zhidao_screenshot.png")
pixels = np.array(img)
h, w = pixels.shape[:2]

results, _ = ocr_engine(img)

with open("zhidao_report.txt", "w", encoding="utf-8") as f:
    f.write(f"截图尺寸: {w}x{h}\n\n")

    # ---- OCR 结果 ----
    f.write("===== OCR 结果 =====\n")
    close_btn = None
    question_tag = None

    if not results:
        f.write("OCR 未识别到任何文字\n")
    else:
        f.write(f"共识别到 {len(results)} 条文字\n\n")
        for i, (box, text, confidence) in enumerate(results):
            xs = [pt[0] for pt in box]
            ys = [pt[1] for pt in box]
            cx, cy = int((min(xs)+max(xs))/2), int((min(ys)+max(ys))/2)
            left, right = int(min(xs)), int(max(xs))
            top, bottom = int(min(ys)), int(max(ys))
            t = text.strip()

            marker = ""
            if "关闭" in t:
                marker = " <-- 关闭按钮"
                close_btn = {"cx": cx, "cy": cy, "left": left, "right": right, "top": top, "bottom": bottom}
            if any(kw in t for kw in ("单选题", "多选题", "判断题")):
                marker = " <-- 题目类型"
                question_tag = {"cx": cx, "cy": cy, "left": left, "right": right, "top": top, "bottom": bottom}

            f.write(f"[{i:2d}] conf={confidence:.2f}  center=({cx},{cy})  rect=({left},{top})-({right},{bottom})  \"{t}\"{marker}\n")

    f.write(f"\n关闭按钮: {close_btn}\n")
    f.write(f"题目标记: {question_tag}\n\n")

    # ---- 弹窗区域颜色扫描 ----
    if close_btn and question_tag:
        popup_left = question_tag["left"] - 30
        popup_right = close_btn["right"] + 30
        popup_top = min(close_btn["top"], question_tag["top"]) - 10
        popup_bottom = min(h, popup_top + int((popup_right - popup_left) * 0.9))

        popup_left = max(0, popup_left)
        popup_right = min(w, popup_right)
        popup_top = max(0, popup_top)

        f.write(f"===== 弹窗区域估算 =====\n")
        f.write(f"弹窗范围: ({popup_left},{popup_top})-({popup_right},{popup_bottom})\n\n")

        f.write(f"===== 弹窗区域逐行颜色扫描 (每5行采样) =====\n")
        f.write(f"{'行Y':>5}  {'R':>4}  {'G':>4}  {'B':>4}  {'亮度':>6}  描述\n")

        scan_left = popup_left + 20
        scan_right = popup_right - 20

        for y in range(popup_top, min(popup_bottom, h), 5):
            row = pixels[y, scan_left:scan_right]
            avg_r = int(np.mean(row[:, 0]))
            avg_g = int(np.mean(row[:, 1]))
            avg_b = int(np.mean(row[:, 2]))
            brightness = (avg_r + avg_g + avg_b) / 3

            if brightness > 252:
                desc = "纯白"
            elif brightness >= 230:
                desc = "灰白 <<<选项条?"
            elif brightness > 200:
                desc = "浅灰"
            elif brightness > 100:
                desc = "中灰"
            else:
                desc = "深色"

            f.write(f"{y:5d}  {avg_r:4d}  {avg_g:4d}  {avg_b:4d}  {brightness:6.1f}  {desc}\n")
    else:
        f.write("未检测到弹窗锚点（关闭/题目类型），无法进行颜色扫描。\n")

del camera
print("截图已保存: zhidao_screenshot.png", flush=True)
print("报告已保存: zhidao_report.txt", flush=True)
input("按回车退出...")
