# 知到弹窗自动关闭工具

自动检测"知到"Windows 桌面客户端课程视频中的答题弹窗，点击选项后关闭弹窗。

## 环境要求

- Windows 10/11
- Python 3.10+

## 安装

```bash
pip install -r requirements.txt
```

## 使用

### 自动关闭弹窗

```bash
python zhidao_auto_close.py
```

1. 程序启动后会请求管理员权限（UAC 弹窗点"是"）
2. 5 秒倒计时内切换到知到 App 全屏播放课程
3. 程序每 2 秒截屏检测一次，发现弹窗自动点击选项并关闭
4. 按 `Ctrl+C` 退出

### 扫描弹窗特征（调试用）

```bash
python zhidao_scan_report.py
```

让知到弹窗显示在屏幕上后运行，会生成：
- `zhidao_screenshot.png` — 截图
- `zhidao_report.txt` — 特征报告（OCR 识别结果 + 逐行像素亮度扫描）

用于检查 OCR 是否正确识别锚点、选项条的亮度范围是否匹配等。

## 工作原理

1. **截屏** — 使用 dxcam (DXGI Desktop Duplication) 截屏，支持硬件加速渲染的窗口
2. **弹窗定位** — 用 RapidOCR 识别屏幕文字，通过"关闭"和"单选题/多选题/判断题"两个锚点确定弹窗边界
3. **选项定位** — 在弹窗区域内逐行扫描像素亮度，找到第一个灰白色背景条（亮度 230-252，高度 ≥50px）即为选项 A
4. **鼠标点击** — 使用 Win32 API（SetCursorPos + SendInput）发送点击事件，需管理员权限以穿透 UIPI 保护
