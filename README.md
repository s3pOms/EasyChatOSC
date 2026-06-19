# EasyChatOSC
* [！！！]{TIP:这个文件'README.md'也是ai生成的}[！！！]
* {TIP:本项目完全使用AI编写 | 基于python | v3之前为deepseek , v3后为Gemini}
# 
* EasyChatOSC 是一款专为 VRChat 玩家打造的、基于 OSC 协议的多功能跨进程辅助工具。它通过异步监听游戏日志与系统状态，为玩家提供低延迟的硬件监测广播、游戏内事件气泡提醒（如玩家进出、模型解包提示），并集成了心率、眼动控制、陀螺仪虚拟模拟等高级 OSC 功能。

项目采用原生 Tkinter 进行了深度动画性能优化，拥有丝滑的跨进程悬浮窗交互体验。

## 🎯 核心功能

* **🖥️ 实时系统状态广播 (OSC)**
  * 自动采集 CPU 使用率、RAM 使用率、GPU 使用率、显存占用及 GPU 温度。
  * **动态进程聚焦**：自动获取当前活动窗口的进程名（如 `msedge.exe`, `QQ.exe`），并与硬件数据一起格式化。
  * 支持自定义文本模版（如 `[rlist] [CPU%] [RAM%]`），支持滑块调节广播频率。
* **📜 VRChat 游戏日志异步联动**
  * 基于文件流异步监听，对游戏性能**零影响**。
  * **玩家进出提醒**：实时弹出带玩家 ID 的 [进入/离开房间] 气泡提示。
  * **模型变动捕获**：当房间内有玩家更换模型时，自动弹出“正在解包模型”提示，并**自动复制头像/模型相关 ID 到剪贴板**，方便一键查询。
* **🎮 高级 OSC 虚拟控制器**
  * **OSC 心率虚拟**：激活后可通过滑块自由调节并发送虚拟心率（BPM）数据。
  * **OSC 眼部追踪控制摇杆**：内置二维坐标虚拟摇杆，支持鼠标拖动模拟眼球转动参数（支持一键居中）。
  * **陀螺仪模拟**：支持自旋转速与偏航修正（Yaw）的高级微调。
* **✨ 丝滑的 UI 与快捷键**
  * **全局快捷键**：全局监听 `Home` 键一键唤醒/隐藏主设置面板；`T` 键快速唤醒迷你聊天输入框。
  * **防卡顿设计**：所有的日志监听、OSC 发送及硬件采集均在独立线程运行，Tkinter 界面永不未响应。

## 📸 界面预览与效果展示

### 1. 软件设置界面

| 常规设置 | 更多模拟控制 | VRChat 联动监控 |
| :---: | :---: | :---: |
| <img width="480" height="613" alt="image" src="https://github.com/user-attachments/assets/106f578b-50e7-4b8b-a285-7d5125bbe011" /><br>配置广播模版、发送间隔与历史应用数 | <img width="464" height="629" alt="image" src="https://github.com/user-attachments/assets/48d0b365-b2dd-4774-a6ee-efde188383a4" /><br>心率虚拟、眼动摇杆控制及陀螺仪调节 | <img width="470" height="614" alt="image" src="https://github.com/user-attachments/assets/0f016c9f-e30a-4f72-96ae-c33872b59c8a" /><br>实时日志行为监听与日志路径配置 |

### 2. 状态监测与聊天输入框

* **系统状态悬浮窗**：实时监控硬件占用、温度，以及当前聚焦的活动窗口。
  <img width="478" height="327" alt="image" src="https://github.com/user-attachments/assets/654e0acb-2b25-4dde-93af-d7c47b6034c0" />
* **迷你快捷聊天输入框**：
  <img width="703" height="122" alt="image" src="https://github.com/user-attachments/assets/8def6620-fb5c-4979-9af5-14879767b099" />

### 3. 系统通知与 VRChat 游戏联动效果

* **系统服务激活提示**：
  <img width="412" height="183" alt="image" src="https://github.com/user-attachments/assets/cda5b2c8-619e-4431-a6a0-6e89add3e199" />
* **测试通知效果**：
  <img width="375" height="119" alt="image" src="https://github.com/user-attachments/assets/921c1c89-e954-4245-bcb5-eec8820994b1" />
* **玩家进入/离开房间实时气泡通知**：
  <table>
    <tr>
      <td><b>玩家进入房间通知序列</b></td>
      <td><b>玩家离开房间通知序列(截图正好没截到动画结束后的样子)</b></td>
    </tr>
    <tr>
      <td><img width="672" height="826" alt="image" src="https://github.com/user-attachments/assets/bce5e5fc-b331-4454-b601-1bc4acab5b06" /></td>
      <td><img width="309" height="525" alt="image" src="https://github.com/user-attachments/assets/9eef7ccd-c7be-4d1a-8f57-31cf84e633a7" /></td>
    </tr>
  </table>
* **自动捕获模型变动提示**：
  <img width="355" height="124" alt="image" src="https://github.com/user-attachments/assets/c9ba3395-abd8-4819-894e-bf34ed94bffd" />
* **捕获好友模型变动[无图片演示]**：
* 会自动复制avtr_XXXXXXXXXXX并加上前缀让他可以直接访问
* **捕获过大模型[无图片演示]**：
* 会自动复制avtr_XXXXXXXXXXX并加上前缀让他可以直接访问

## 🚀 快速开始

### 运行环境准备
1. 确保你的 VRChat 已经开启了 **OSC** 功能（在游戏内圆盘菜单 -> Options -> OSC -> Set Enabled）。
2. 本程序默认会自动读取 VRChat 标准日志目录 `C:\Users\[UserName]\AppData\LocalLow\VRChat\VRChat`，若有自定义请在面板中修改。

### 快捷键操作
* **`Home` 键**：呼出 / 隐藏主设置菜单。
* **`T` 键**：呼出迷你聊天输入框（输入完成后回车即可直接通过 OSC 发送到游戏内聊天框）。

## 🛠️ 开发指南 (本地运行与打包)

如果你想自行修改源码或编译，请参考以下步骤：

### 1. 安装依赖
```bash
pip install pyautogui psutil GPUtil pywin32 python-osc keyboard
