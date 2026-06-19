import sys
import time
import threading
import os
import json
import psutil
import math
import re  # 引入正则用于解析日志中的 Avatar ID 和解包状态
import tkinter as tk
from tkinter import font
from tkinter import ttk  # 用于选项卡组件
import keyboard  # 确保执行过 pip install keyboard

# 引入 Windows 底层窗口控制与进程捕获 API
try:
    import win32gui
    import win32con
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

from collections import deque

# --- 配置文件路径 ---
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.txt")

# --- 动态获取当前系统的 VRChat 默认日志路径（摆脱 KFCv50 硬编码限制） ---
DEFAULT_VRC_LOG_PATH = os.path.join(os.environ.get("USERPROFILE", "C:\\Users\\Default"), r"AppData\LocalLow\VRChat\VRChat")

# --- 全局基础状态与配置 ---
CONFIG = {
    "VRC_IP": "127.0.0.1",
    "VRC_PORT": 9000,
    "UPDATE_INTERVAL": 1.5,
    "MENU_X": 100,
    "MENU_Y": 100,
    "CHAT_TEMPLATE": "ㅤ[rslist]\n[CPU%]\n[RAM%]\nGPU:[GPU%] Temp:[GPUTemp]",
    "MAX_APP_NUM": 3,
    "TITLE_LEN": 14,
    "PROC_LEN": 10,
    # --- VRChat 联动日志默认配置项（此处已变更为自适应动态路径） ---
    "VRC_LOG_ENABLED": True,
    "VRC_LOG_PATH": DEFAULT_VRC_LOG_PATH,
    "VRC_NOTIFY_JOIN_LEAVE": True,
    "VRC_AUTO_COPY_AVATAR": True
}

state = {
    "running": True,
    "osc_client": None,
    "cpu_usage": 0,
    "ram_usage": 0,
    "gpu_usage": 0,
    "gpu_temp": 0,
    "gpu_mem_usage": 0,
    "has_nvidia_gpu": True,      
    "t_mode_active": False,      
    "t_mode_end_time": 0,        
    "enable_auto_sync": True,    
    "app_history": deque(maxlen=5), 
    
    # --- OSC 模拟与控制器状态流 ---
    "hr_enabled": False,         # 心率模拟开关
    "hr_bpm": 80,                # 心率数值
    "eye_enabled": False,        # 眼追踪开关
    "eye_x": 0.0,                # 眼 X (-1.0 ~ 1.0)
    "eye_y": 0.0,                # 眼 Y (-1.0 ~ 1.0)
    "gyro_enabled": False,       # 陀螺移动开关
    "gyro_speed": 1.5,           # 陀螺转速
    
    # --- 日志状态防重追踪器 ---
    "last_copied_avatar": "",    
    "last_avatar_time": 0        
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                CONFIG.update(saved)
        except Exception: pass

def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "MENU_X": CONFIG["MENU_X"],
                "MENU_Y": CONFIG["MENU_Y"],
                "UPDATE_INTERVAL": CONFIG["UPDATE_INTERVAL"],
                "CHAT_TEMPLATE": CONFIG["CHAT_TEMPLATE"],
                "MAX_APP_NUM": CONFIG["MAX_APP_NUM"],
                "TITLE_LEN": CONFIG["TITLE_LEN"],
                "PROC_LEN": CONFIG["PROC_LEN"],
                # --- 确保联动日志参数一并保存持久化 ---
                "VRC_LOG_ENABLED": CONFIG["VRC_LOG_ENABLED"],
                "VRC_LOG_PATH": CONFIG["VRC_LOG_PATH"],
                "VRC_NOTIFY_JOIN_LEAVE": CONFIG["VRC_NOTIFY_JOIN_LEAVE"],
                "VRC_AUTO_COPY_AVATAR": CONFIG["VRC_AUTO_COPY_AVATAR"]
            }, f, indent=4)
    except Exception: pass

load_config()

from oscpy.client import OSCClient
try:
    state["osc_client"] = OSCClient(CONFIG["VRC_IP"], CONFIG["VRC_PORT"])
    print(f"OSC 客户端绑定成功 -> {CONFIG['VRC_IP']}:{CONFIG['VRC_PORT']}")
except Exception as e:
    print(f"OSC 初始化失败: {e}")


# ====================================================================
# ✨ ✨ ✨ 核心封装：绝对坐标钉死防挤压、0.1 位高精倒计时、上限 8 个自动顶替关闭
# ====================================================================
class ToastManager:
    active_toasts = []  
    lock = threading.Lock()

    @classmethod
    def show(cls, title="系统提示", message="", title_size=12, msg_size=10, duration=4000, width=320, height=85):
        if threading.current_thread() != threading.main_thread():
            raise RuntimeError("Toast 必须在 Tkinter 主线程中调用。")
        with cls.lock:
            # 超过 8 个时，主动通过滑动效果弹退并清除最顶端（最老）的一个通知
            while len(cls.active_toasts) >= 8:
                try:
                    oldest_toast = cls.active_toasts[0]
                    # 直接引发它的滑出退出逻辑（它会把自己从列表中 remove 并重新整理排列）
                    oldest_toast.start_slide_out()
                except Exception:
                    break

            toast = cls(title, message, title_size, msg_size, duration, width, height)
            cls.active_toasts.append(toast)
            cls.rearrange()

    @classmethod
    def rearrange(cls):
        start_y = 60
        spacing = 15
        for idx, toast in enumerate(cls.active_toasts):
            target_y = start_y
            for i in range(idx):
                target_y += cls.active_toasts[i].height + spacing
            toast.target_y = target_y
            if not toast.is_animating_in:
                toast.slide_to_y()

    def __init__(self, title, message, title_size, msg_size, duration, width, height):
        self.width = width
        self.height = height
        self.duration_ms = duration  
        self.remaining_time = duration / 1000.0 
        
        self.root = tk.Toplevel()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.0)  
        self.root.config(bg="#1c1c1c")
        
        self.screen_w = self.root.winfo_screenwidth()
        self.margin_x = 25  
        self.current_x = self.screen_w
        self.target_x = self.screen_w - self.width - self.margin_x
        self.target_y = 60
        self.current_y = 60
        
        self.root.geometry(f"{self.width}x{self.height}+{int(self.current_x)}+{int(self.current_y)}")

        left_bar = tk.Frame(self.root, width=5, bg="#4ccdec")
        left_bar.pack(side="left", fill="y")

        main_container = tk.Frame(self.root, bg="#1c1c1c", padx=12, pady=6)
        main_container.pack(side="left", fill="both", expand=True)

        font_title = font.Font(family="Microsoft YaHei", size=title_size, weight="bold")
        lbl_title = tk.Label(main_container, text=title, bg="#1c1c1c", fg="#4ccdec", font=font_title, anchor="w")
        lbl_title.pack(fill="x", side="top", pady=(0, 1))

        font_msg = font.Font(family="Microsoft YaHei", size=msg_size, weight="bold")
        lbl_msg = tk.Label(main_container, text=message, bg="#1c1c1c", fg="#e0e0e0", font=font_msg, 
                           justify="left", anchor="nw", wraplength=self.width - 35)
        lbl_msg.pack(fill="both", expand=True, side="top", pady=(0, 12))

        font_time = font.Font(family="Consolas", size=9, weight="bold") 
        self.lbl_countdown = tk.Label(main_container, text=f"{self.remaining_time:.1f}s", bg="#1c1c1c", fg="#666666", font=font_time, anchor="se")
        self.lbl_countdown.place(relx=1.0, rely=1.0, x=0, y=0, anchor="se")

        self.root.bind("<Button-1>", lambda e: self.start_slide_out())
        self.alpha = 0.0
        self.is_animating_in = True
        self.is_closing = False
        self.animate_fade_in_slide()

    def animate_fade_in_slide(self):
        if self.is_closing: return
        dx = self.target_x - self.current_x
        if abs(dx) > 1.0:
            self.current_x += dx * 0.22  
            self.alpha = min(0.82, self.alpha + 0.12)  
            self.root.attributes("-alpha", self.alpha)
            self.root.geometry(f"+{int(self.current_x)}+{int(self.target_y)}")
            self.root.after(16, self.animate_fade_in_slide)
        else:
            self.current_x = self.target_x
            self.current_y = self.target_y
            self.root.attributes("-alpha", 0.82) 
            self.root.geometry(f"+{int(self.current_x)}+{int(self.target_y)}")
            self.is_animating_in = False
            self.start_timestamp = time.time()
            self.update_countdown_loop()

    def update_countdown_loop(self):
        if self.is_closing: return
        passed = time.time() - self.start_timestamp
        self.remaining_time = max(0.0, (self.duration_ms / 1000.0) - passed)
        self.lbl_countdown.config(text=f"{self.remaining_time:.1f}s")
        if self.remaining_time > 0.0:
            self.root.after(100, self.update_countdown_loop)
        else:
            self.start_slide_out()

    def slide_to_y(self):
        if self.is_closing or self.is_animating_in: return
        dy = self.target_y - self.current_y
        if abs(dy) > 1.0:
            self.current_y += dy * 0.2
            self.root.geometry(f"+{int(self.current_x)}+{int(self.current_y)}")
            self.root.after(16, self.slide_to_y)
        else:
            self.current_y = self.target_y
            self.root.geometry(f"+{int(self.current_x)}+{int(self.target_y)}")

    def start_slide_out(self):
        if self.is_closing: return
        self.is_closing = True
        if self in ToastManager.active_toasts:
            ToastManager.active_toasts.remove(self)
            ToastManager.rearrange()
        self.animate_fade_out_slide()

    def animate_fade_out_slide(self):
        dx = self.screen_w - self.current_x
        if dx > 1.0 and self.alpha > 0.02:
            self.current_x += dx * 0.2  
            self.alpha = max(0.0, self.alpha - 0.12)
            self.root.attributes("-alpha", self.alpha)
            self.root.geometry(f"+{int(self.current_x)}+{int(self.current_y)}")
            self.root.after(16, self.animate_fade_out_slide)
        else:
            try: self.root.destroy()
            except Exception: pass


def make_progress_bar(percent, width=9):
    filled_len = int(round(width * percent / 100))
    return '█' * filled_len + '▒' * (width - filled_len)

def get_foreground_app():
    if not HAS_WIN32: return "", ""
    try:
        window = win32gui.GetForegroundWindow()
        if window:
            title = win32gui.GetWindowText(window)
            if not title or "VRChat Minimal Chatbox" in title or "VRChat OSC Config Menu" in title:
                return "", ""
            _, pid = win32process.GetWindowThreadProcessId(window)
            process = psutil.Process(pid)
            process_name = process.name()
            return title, process_name
    except Exception: pass
    return "", ""

def fetch_gpu_status_via_smi():
    try:
        cmd = 'nvidia-smi --query-gpu=utilization.gpu,temperature.gpu,utilization.memory --format=csv,noheader,nounits'
        with os.popen(cmd) as f:
            line = f.readline()
            if line:
                parts = line.strip().split(',')
                state["gpu_usage"] = float(parts[0].strip())
                state["gpu_temp"] = float(parts[1].strip())
                state["gpu_mem_usage"] = float(parts[2].strip())
                state["has_nvidia_gpu"] = True
                return
    except Exception: pass
    state["has_nvidia_gpu"] = False

def get_processed_template_message():
    template = CONFIG["CHAT_TEMPLATE"]
    if "[rslist]" in template:
        num_to_show = min(CONFIG["MAX_APP_NUM"], len(state["app_history"]))
        app_list = []
        for title, exe in list(state["app_history"])[:num_to_show]:
            t_len = CONFIG["TITLE_LEN"]
            p_len = CONFIG["PROC_LEN"]
            fmt_title = (title[:t_len] + '..') if (t_len > 0 and len(title) > t_len) else title
            fmt_proc = (exe[:p_len] + '..') if (p_len > 0 and len(exe) > p_len) else exe
            if t_len == 0: fmt_title = ""
            if p_len == 0: fmt_proc = ""
            if fmt_title and fmt_proc: app_list.append(f"{fmt_title} | {fmt_proc}")
            elif fmt_title or fmt_proc: app_list.append(fmt_title if fmt_title else fmt_proc)
        if app_list: template = template.replace("[rslist]", "\n".join(app_list))
        else: template = template.replace("[rslist]", "(正在捕获应用...)")

    if "[CPU%]" in template:
        cpu_bar = make_progress_bar(state["cpu_usage"])
        template = template.replace("[CPU%]", f"CPU: [{cpu_bar}] {int(state['cpu_usage'])}%")
    if "[RAM%]" in template:
        ram_bar = make_progress_bar(state["ram_usage"])
        template = template.replace("[RAM%]", f"RAM: [{ram_bar}] {int(state['ram_usage'])}%")
    if state["has_nvidia_gpu"]:
        if "[GPU%]" in template:
            gpu_bar = make_progress_bar(state["gpu_usage"])
            template = template.replace("[GPU%]", f"GPU: [{gpu_bar}] {int(state['gpu_usage'])}%")
        if "[GPUTemp]" in template:
            template = template.replace("[GPUTemp]", f"{int(state['gpu_temp'])}°C")
        if "[GPUMem%]" in template:
            gpu_mem_bar = make_progress_bar(state["gpu_mem_usage"])
            template = template.replace("[GPUMem%]", f"VRAM: [{gpu_mem_bar}] {int(state['gpu_mem_usage'])}%")
    else:
        template = template.replace("[GPU%]", "GPU: N/A").replace("[GPUTemp]", "N/A").replace("[GPUMem%]", "VRAM: N/A")
    return template


# ====================================================================
# 🚀 异步高频线程流：控制独立 high 频参数发送
# ====================================================================
def osc_simulation_high_frequency_loop():
    last_hr_time = 0
    while state["running"]:
        now = time.time()
        client = state["osc_client"]
        
        if client:
            if state["hr_enabled"] and state["hr_bpm"] > 0:
                interval = 60.0 / state["hr_bpm"]
                if now - last_hr_time >= interval:
                    try:
                        client.send_message(b'/avatar/parameters/Heartrate', [float(state["hr_bpm"])])
                    except Exception: pass
                    last_hr_time = now

            if state["eye_enabled"]:
                try:
                    client.send_message(b'/avatar/parameters/EyesX', [float(state["eye_x"])])
                    client.send_message(b'/avatar/parameters/EyesY', [float(state["eye_y"])])
                except Exception: pass

            if state["gyro_enabled"]:
                try:
                    client.send_message(b'/input/LookHorizontal', [float(state["gyro_speed"])])
                    forward_thrust = min(0.8, abs(state["gyro_speed"]) * 0.15)
                    client.send_message(b'/input/MoveForward', [float(forward_thrust)])
                except Exception: pass
        
        time.sleep(0.02)


def data_monitor_loop(chat_app, menu_app):
    last_app = ("", "")
    while state["running"]:
        try:
            state["cpu_usage"] = psutil.cpu_percent(interval=None)
            state["ram_usage"] = psutil.virtual_memory().percent
            fetch_gpu_status_via_smi()

            curr_title, curr_proc = get_foreground_app()
            if curr_title and curr_proc:
                current_app = (curr_title, curr_proc)
                if current_app != last_app:
                    last_app = current_app
                    if current_app not in state["app_history"]:
                        state["app_history"].appendleft(current_app)

            if menu_app and menu_app.is_visible:
                try:
                    preview_msg = get_processed_template_message()
                    menu_app.lbl_preview_box.config(text=preview_msg)
                except Exception: pass

            current_time = time.time()
            if state["t_mode_active"]:
                if current_time > state["t_mode_end_time"]: state["t_mode_active"] = False  
                else:
                    time.sleep(0.2)
                    continue

            if state["enable_auto_sync"]:
                osc_msg = get_processed_template_message()
                if state["osc_client"] and osc_msg:
                    try: state["osc_client"].send_message(b'/chatbox/input', [osc_msg.encode('utf-8'), False, True])
                    except Exception: pass

            if chat_app and chat_app.is_visible and HAS_WIN32:
                try:
                    hwnd = win32gui.FindWindow(None, "VRChat Minimal Chatbox")
                    if hwnd:
                        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, 
                                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
                except Exception: pass
            time.sleep(CONFIG["UPDATE_INTERVAL"])
        except Exception: time.sleep(1)


class VrcChatOverlay:
    def __init__(self, root):
        self.root = tk.Toplevel(root)
        self.root.title("VRChat Minimal Chatbox")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)
        self.root.config(bg="#141414")
        
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        box_w, box_h = 600, 45
        self.root.geometry(f"{box_w}x{box_h}+{(screen_w - box_w) // 2}+{int(screen_h * 0.72)}")

        chat_font = font.Font(family="Microsoft YaHei", size=11, weight="bold")
        lbl_icon = tk.Label(self.root, text=" 💬 ⌨ ", bg="#141414", fg="#4ccdec", font=chat_font)
        lbl_icon.pack(side="left", padx=(12, 0))

        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(self.root, textvariable=self.entry_var, bg="#1f1f1f", fg="#ffffff", 
                              insertbackground="#4ccdec", relief="flat", font=chat_font)
        self.entry.pack(side="left", fill="x", expand=True, padx=12, ipady=3)
        
        self.is_composing = False
        self.entry.bind("<<IMEComposition>>", self.on_ime_composition)
        self.entry.bind("<Return>", self.handle_return)
        self.entry.bind("<Escape>", lambda e: self.hide_box())
        self.root.withdraw()
        self.is_visible = False

    def on_ime_composition(self, event): self.is_composing = True
    def handle_return(self, event): self.root.after(20, self.check_and_send)
    def check_and_send(self):
        if self.is_composing:
            self.is_composing = False
            return
        self.send_message_same_channel()

    def toggle_box(self):
        if not self.is_visible:
            if HAS_WIN32:
                hwnd_fg = win32gui.GetForegroundWindow()
                title_fg = win32gui.GetWindowText(hwnd_fg) if hwnd_fg else ""
                if not ("VRChat" in title_fg or "VRChat OSC Config Menu" in title_fg or "VRChat Minimal Chatbox" in title_fg):
                    return
            self.is_composing = False
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            if HAS_WIN32:
                try:
                    hwnd = win32gui.FindWindow(None, "VRChat Minimal Chatbox")
                    if hwnd:
                        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                        shell = win32gui.GetForegroundWindow()
                        if shell != hwnd:
                            keyboard.press_and_release('alt')
                            win32gui.SetForegroundWindow(hwnd)
                except Exception: pass
            self.entry.focus_set()
            self.entry.focus_force()
            self.is_visible = True

    def hide_box(self):
        if self.is_visible:
            self.entry_var.set("")
            self.root.withdraw()
            self.is_visible = False

    def send_message_same_channel(self):
        text = self.entry_var.get().strip()
        if text and state["osc_client"]:
            try:
                formatted_text = " " + text
                state["osc_client"].send_message(b'/chatbox/input', [formatted_text.encode('utf-8'), False, True])
                state["t_mode_active"] = True
                state["t_mode_end_time"] = time.time() + 5.0
            except Exception as e: print(e)
        self.hide_box()


class VrcConfigMenu:
    def __init__(self, root):
        self.root = tk.Toplevel(root)
        self.root.title("VRChat OSC Config Menu")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.96)
        self.root.config(bg="#1a1a1a")
        
        menu_w, menu_h = 440, 590
        self.root.geometry(f"{menu_w}x{menu_h}+{CONFIG['MENU_X']}+{CONFIG['MENU_Y']}")

        ui_font = font.Font(family="Microsoft YaHei", size=10, weight="bold")

        self.lbl_title = tk.Label(self.root, text=" 📊 EasyChatOSC", bg="#2d2d2d", fg="#4ccdec", font=ui_font, anchor="w", padx=8)
        self.lbl_title.pack(fill="x", ipady=6)
        self.lbl_title.bind("<Button-1>", self.start_drag)
        self.lbl_title.bind("<B1-Motion>", self.on_drag)

        style = ttk.Style()
        style.theme_use('default')
        style.configure('TNotebook', background='#1a1a1a', borderwidth=0)
        style.configure('TNotebook.Tab', background='#2d2d2d', foreground='#888888', font=ui_font, borderwidth=0, padding=[15, 4])
        style.map('TNotebook.Tab', background=[('selected', '#1a1a1a')], foreground=[('selected', '#4ccdec')])

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)

        tab_general = tk.Frame(notebook, bg="#1a1a1a")
        tab_more = tk.Frame(notebook, bg="#1a1a1a")
        tab_vrc_monitor = tk.Frame(notebook, bg="#1a1a1a")

        notebook.add(tab_general, text=" 常规 ")
        notebook.add(tab_more, text=" 更多模拟控制 ")
        notebook.add(tab_vrc_monitor, text=" VRChat 联动监控 ")

        # ------------------- 常规 选项卡内容 -------------------
        frame_template = tk.LabelFrame(tab_general, text="💬 模板", bg="#1a1a1a", fg="#4ccdec", font=ui_font, padx=10, pady=5)
        frame_template.pack(fill="x", padx=10, pady=4)

        self.txt_template = tk.Text(frame_template, height=3, bg="#232323", fg="#ffffff", insertbackground="#4ccdec", relief="flat", font=ui_font)
        self.txt_template.pack(fill="x", pady=2)
        self.txt_template.insert("1.0", CONFIG["CHAT_TEMPLATE"])
        self.txt_template.bind("<KeyRelease>", self.on_template_changed)

        lbl_tips = tk.Label(frame_template, text="可用: [rslist] [CPU%] [RAM%] [GPU%] [GPUMem%] [GPUTemp]", bg="#1a1a1a", fg="#888888", font=font.Font(size=9))
        lbl_tips.pack(anchor="w")

        frame_ctrl = tk.Frame(tab_general, bg="#1a1a1a", padx=10)
        frame_ctrl.pack(fill="x")
        self.sync_var = tk.BooleanVar(value=True)
        self.cb_sync = tk.Checkbutton(frame_ctrl, text="启用发送", variable=self.sync_var, bg="#1a1a1a", fg="#ffffff", 
                                      selectcolor="#2b2b2b", activebackground="#1a1a1a", activeforeground="#ffffff", font=ui_font, command=self.toggle_sync)
        self.cb_sync.pack(side="left", pady=2)

        frame_spin = tk.Frame(tab_general, bg="#1a1a1a", padx=10, pady=4)
        frame_spin.pack(fill="x")
        tk.Label(frame_spin, text="历史应用数:", bg="#1a1a1a", fg="#ffffff", font=ui_font).grid(row=0, column=0, sticky="w", pady=2)
        self.spin_num = tk.Spinbox(frame_spin, from_=1, to=5, width=3, font=ui_font, bg="#232323", fg="#ffffff", buttonbackground="#2d2d2d", command=self.update_spin_params)
        self.spin_num.delete(0, "end"); self.spin_num.insert(0, str(CONFIG["MAX_APP_NUM"]))
        self.spin_num.grid(row=0, column=1, padx=(5, 12))

        tk.Label(frame_spin, text="标题长:", bg="#1a1a1a", fg="#ffffff", font=ui_font).grid(row=0, column=2, sticky="w")
        self.spin_tlen = tk.Spinbox(frame_spin, from_=0, to=30, width=3, font=ui_font, bg="#232323", fg="#ffffff", command=self.update_spin_params)
        self.spin_tlen.delete(0, "end"); self.spin_tlen.insert(0, str(CONFIG["TITLE_LEN"]))
        self.spin_tlen.grid(row=0, column=3, padx=(5, 12))

        tk.Label(frame_spin, text="进程长:", bg="#1a1a1a", fg="#ffffff", font=ui_font).grid(row=0, column=4, sticky="w")
        self.spin_plen = tk.Spinbox(frame_spin, from_=0, to=30, width=3, font=ui_font, bg="#232323", fg="#ffffff", command=self.update_spin_params)
        self.spin_plen.delete(0, "end"); self.spin_plen.insert(0, str(CONFIG["PROC_LEN"]))
        self.spin_plen.grid(row=0, column=5, padx=5)

        for sp in (self.spin_num, self.spin_tlen, self.spin_plen):
            sp.bind("<KeyRelease>", lambda e: self.update_spin_params())
            sp.bind("<FocusOut>", lambda e: self.update_spin_params())

        frame_scale = tk.Frame(tab_general, bg="#1a1a1a", padx=10, pady=4)
        frame_scale.pack(fill="x")
        tk.Label(frame_scale, text="发送间隔 (秒):", bg="#1a1a1a", fg="#ffffff", font=ui_font).pack(side="left")
        self.scale = tk.Scale(frame_scale, from_=1.5, to=5.0, resolution=0.1, orient="horizontal", 
                              bg="#1a1a1a", fg="#4ccdec", highlightthickness=0, troughcolor="#2b2b2b", command=self.interval_changed)
        self.scale.set(CONFIG["UPDATE_INTERVAL"])
        self.scale.pack(side="left", fill="x", expand=True, padx=10)

        # ------------------- 更多 选项卡内容 -------------------
        more_scroll_container = tk.Frame(tab_more, bg="#1a1a1a")
        more_scroll_container.pack(fill="both", expand=True, padx=8, pady=5)

        frame_hr = tk.LabelFrame(more_scroll_container, text="❤️ OSC 心率虚拟", bg="#1a1a1a", fg="#4ccdec", font=ui_font, padx=10, pady=4)
        frame_hr.pack(fill="x", pady=4)
        
        self.hr_var = tk.BooleanVar(value=False)
        self.cb_hr = tk.Checkbutton(frame_hr, text="激活心率虚拟发送", variable=self.hr_var, bg="#1a1a1a", fg="#ffffff",
                                    selectcolor="#2b2b2b", font=ui_font, command=self.on_hr_toggle)
        self.cb_hr.pack(side="left", padx=5)
        
        self.sc_hr = tk.Scale(frame_hr, from_=40, to=200, orient="horizontal", label="心率值 (BPM)", bg="#1a1a1a", fg="#e0e0e0",
                              highlightthickness=0, troughcolor="#2b2b2b", font=font.Font(size=9, weight="bold"), command=self.on_hr_val_changed)
        self.sc_hr.set(state["hr_bpm"])
        self.sc_hr.pack(side="right", fill="x", expand=True, padx=10)

        frame_eye = tk.LabelFrame(more_scroll_container, text="👁️ OSC 眼部追踪控制摇杆", bg="#1a1a1a", fg="#4ccdec", font=ui_font, padx=10, pady=4)
        frame_eye.pack(fill="x", pady=4)

        eye_top_bar = tk.Frame(frame_eye, bg="#1a1a1a")
        eye_top_bar.pack(fill="x", pady=2)
        
        self.eye_var = tk.BooleanVar(value=False)
        self.cb_eye = tk.Checkbutton(eye_top_bar, text="启用眼部模拟参数", variable=self.eye_var, bg="#1a1a1a", fg="#ffffff",
                                     selectcolor="#2b2b2b", font=ui_font, command=self.on_eye_toggle)
        self.cb_eye.pack(side="left", padx=5)

        self.btn_eye_reset = tk.Button(eye_top_bar, text="眼睛恢复居中", font=font.Font(size=9, weight="bold"), bg="#2d2d2d", fg="#4ccdec",
                                       bd=0, cursor="hand2", padx=8, command=self.reset_eye_joystick)
        self.btn_eye_reset.pack(side="right", padx=5)

        self.joy_size = 110
        self.joy_center = self.joy_size // 2
        self.joy_radius = 48
        
        self.canvas_frame = tk.Frame(frame_eye, bg="#1a1a1a")
        self.canvas_frame.pack(pady=4)

        self.joystick = tk.Canvas(self.canvas_frame, width=self.joy_size, height=self.joy_size, bg="#232323", highlightthickness=1, highlightbackground="#333333")
        self.joystick.pack(side="left")
        
        self.joystick.create_line(0, self.joy_center, self.joy_size, self.joy_center, fill="#3a3a3a", dash=(2, 2))
        self.joystick.create_line(self.joy_center, 0, self.joy_center, self.joy_size, fill="#3a3a3a", dash=(2, 2))
        self.joystick.create_oval(self.joy_center-self.joy_radius, self.joy_center-self.joy_radius, self.joy_center+self.joy_radius, self.joy_center+self.joy_radius, outline="#3a3a3a")
        
        self.joy_dot_r = 6
        self.joy_dot = self.joystick.create_oval(self.joy_center-self.joy_dot_r, self.joy_center-self.joy_dot_r, self.joy_center+self.joy_dot_r, self.joy_center+self.joy_dot_r, fill="#ef476f", outline="")

        self.joystick.bind("<B1-Motion>", self.update_joystick_pos)
        self.joystick.bind("<Button-1>", self.update_joystick_pos)

        self.lbl_joy_data = tk.Label(self.canvas_frame, text="X: 0.00\nY: 0.00", bg="#1a1a1a", fg="#888888", font=font.Font(family="Consolas", size=10), justify="left")
        self.lbl_joy_data.pack(side="left", padx=15)

        frame_gyro = tk.LabelFrame(more_scroll_container, text="陀螺", bg="#1a1a1a", fg="#4ccdec", font=ui_font, padx=10, pady=4)
        frame_gyro.pack(fill="x", pady=4)

        self.gyro_var = tk.BooleanVar(value=False)
        self.cb_gyro = tk.Checkbutton(frame_gyro, text="激活陀螺", variable=self.gyro_var, bg="#1a1a1a", fg="#ffffff",
                                      selectcolor="#2b2b2b", font=ui_font, command=self.on_gyro_toggle)
        self.cb_gyro.pack(side="left", padx=5)

        self.sc_gyro = tk.Scale(frame_gyro, from_=-5.0, to=5.0, resolution=0.1, orient="horizontal", label="自旋转速与偏航修正", bg="#1a1a1a", fg="#e0e0e0",
                                highlightthickness=0, troughcolor="#2b2b2b", font=font.Font(size=9, weight="bold"), command=self.on_gyro_speed_changed)
        self.sc_gyro.set(state["gyro_speed"])
        self.sc_gyro.pack(side="right", fill="x", expand=True, padx=10)

        btn_test = tk.Button(more_scroll_container, text="测试通知", font=ui_font, bg="#2d2d2d", fg="#4ccdec", 
                             activebackground="#4ccdec", activeforeground="#1a1a1a", bd=0, cursor="hand2", command=self.trigger_test_toast, padx=15, pady=4)
        btn_test.pack(fill="x", pady=5)

        # ------------------- VRChat 联动监控 选项卡内容 -------------------
        monitor_container = tk.Frame(tab_vrc_monitor, bg="#1a1a1a")
        monitor_container.pack(fill="both", expand=True, padx=8, pady=5)

        frame_log = tk.LabelFrame(monitor_container, text="📁 实时日志行为监听", bg="#1a1a1a", fg="#4ccdec", font=ui_font, padx=10, pady=4)
        frame_log.pack(fill="x", pady=4)

        self.log_enabled_var = tk.BooleanVar(value=CONFIG["VRC_LOG_ENABLED"])
        self.cb_log_enabled = tk.Checkbutton(frame_log, text="开启 VRChat 游戏日志实时监控", variable=self.log_enabled_var, bg="#1a1a1a", fg="#ffffff",
                                             selectcolor="#2b2b2b", font=ui_font, command=self.on_vrc_log_config_changed)
        self.cb_log_enabled.pack(anchor="w", padx=5, pady=4)

        self.notify_jl_var = tk.BooleanVar(value=CONFIG["VRC_NOTIFY_JOIN_LEAVE"])
        self.cb_notify_jl = tk.Checkbutton(frame_log, text="玩家 [进入/离开房间] 气泡提示", variable=self.notify_jl_var, bg="#1a1a1a", fg="#ffffff",
                                           selectcolor="#2b2b2b", font=ui_font, command=self.on_vrc_log_config_changed)
        self.cb_notify_jl.pack(anchor="w", padx=5, pady=4)

        self.auto_avatar_var = tk.BooleanVar(value=CONFIG["VRC_AUTO_COPY_AVATAR"])
        self.cb_auto_avatar = tk.Checkbutton(frame_log, text="房间内玩家变动模型时 [自动复制并提示]", variable=self.auto_avatar_var, bg="#1a1a1a", fg="#ffffff",
                                             selectcolor="#2b2b2b", font=ui_font, command=self.on_vrc_log_config_changed)
        self.cb_auto_avatar.pack(anchor="w", padx=5, pady=4)

        lbl_path_title = tk.Label(frame_log, text="日志监听目录:", bg="#1a1a1a", fg="#888888", font=font.Font(size=9, weight="bold"))
        lbl_path_title.pack(anchor="w", padx=5, pady=(8, 2))
        
        self.ent_log_path = ttk.Entry(frame_log)
        self.ent_log_path.insert(0, CONFIG["VRC_LOG_PATH"])
        self.ent_log_path.pack(fill="x", padx=5, pady=(0, 6))
        self.ent_log_path.bind("<KeyRelease>", lambda e: self.on_vrc_log_config_changed())
        self.ent_log_path.bind("<FocusOut>", lambda e: self.on_vrc_log_config_changed())

        # ------------------- 底部公用本地效果预览栏 -------------------
        tk.Frame(self.root, height=1, bg="#333333").pack(fill="x", padx=15, pady=2)
        frame_prev = tk.Frame(self.root, bg="#1a1a1a", padx=15)
        frame_prev.pack(fill="x", pady=(2, 8))
        tk.Label(frame_prev, text="💻 预览:", bg="#1a1a1a", fg="#a0a0a0", font=ui_font).pack(anchor="w", pady=(0, 2))
        self.lbl_preview_box = tk.Label(frame_prev, text="", bg="#232323", fg="#ffffff", font=ui_font, justify="left", anchor="nw", padx=10, pady=6, width=45, height=3)
        self.lbl_preview_box.pack(fill="x")

        self.root.withdraw()
        self.is_visible = False

    def on_vrc_log_config_changed(self, event=None):
        CONFIG["VRC_LOG_ENABLED"] = self.log_enabled_var.get()
        CONFIG["VRC_NOTIFY_JOIN_LEAVE"] = self.notify_jl_var.get()
        CONFIG["VRC_AUTO_COPY_AVATAR"] = self.auto_avatar_var.get()
        CONFIG["VRC_LOG_PATH"] = self.ent_log_path.get().strip()
        save_config()

    def on_hr_toggle(self):
        state["hr_enabled"] = self.hr_var.get()

    def on_hr_val_changed(self, val):
        state["hr_bpm"] = int(float(val))

    def on_eye_toggle(self):
        state["eye_enabled"] = self.eye_var.get()
        if not state["eye_enabled"]:
            self.clear_eye_signals_safely()

    def update_joystick_pos(self, event):
        dx = event.x - self.joy_center
        dy = event.y - self.joy_center
        distance = math.sqrt(dx*dx + dy*dy)
        
        if distance > self.joy_radius:
            dx = (dx / distance) * self.joy_radius
            dy = (dy / distance) * self.joy_radius

        nx = self.joy_center + dx
        ny = self.joy_center + dy
        
        self.joystick.coords(self.joy_dot, nx-self.joy_dot_r, ny-self.joy_dot_r, nx+self.joy_dot_r, ny+self.joy_dot_r)
        
        state["eye_x"] = round(dx / self.joy_radius, 2)
        state["eye_y"] = round(-dy / self.joy_radius, 2)
        self.lbl_joy_data.config(text=f"X: {state['eye_x']:.2f}\nY: {state['eye_y']:.2f}")

    def reset_eye_joystick(self):
        self.joystick.coords(self.joy_dot, self.joy_center-self.joy_dot_r, self.joy_center-self.joy_dot_r, self.joy_center+self.joy_dot_r, self.joy_center+self.joy_dot_r)
        state["eye_x"] = 0.0
        state["eye_y"] = 0.0
        self.lbl_joy_data.config(text="X: 0.00\nY: 0.00")
        self.clear_eye_signals_safely()

    def clear_eye_signals_safely(self):
        if state["osc_client"]:
            try:
                state["osc_client"].send_message(b'/avatar/parameters/EyesX', [0.0])
                state["osc_client"].send_message(b'/avatar/parameters/EyesY', [0.0])
            except Exception: pass

    def on_gyro_toggle(self):
        state["gyro_enabled"] = self.gyro_var.get()
        if not state["gyro_enabled"]:
            self.clear_gyro_signals_safely()

    def on_gyro_speed_changed(self, val):
        state["gyro_speed"] = float(val)

    def clear_gyro_signals_safely(self):
        if state["osc_client"]:
            try:
                state["osc_client"].send_message(b'/input/LookHorizontal', [0.0])
                state["osc_client"].send_message(b'/input/MoveForward', [0.0])
            except Exception: pass

    def trigger_test_toast(self):
        ToastManager.show(
            title="测试通知", 
            message="这是测试！",
            title_size=12,
            msg_size=10,
            duration=5000,
            width=340,
            height=90
        )

    def start_drag(self, event):
        self.drag_x = event.x
        self.drag_y = event.y

    def on_drag(self, event):
        x = self.root.winfo_x() - self.drag_x + event.x
        y = self.root.winfo_y() - self.drag_y + event.y
        self.root.geometry(f"+{x}+{y}")
        CONFIG["MENU_X"] = x
        CONFIG["MENU_Y"] = y
        save_config()

    def toggle_menu(self):
        self.is_visible = not self.is_visible
        if self.is_visible:
            self.txt_template.delete("1.0", "end")
            self.txt_template.insert("1.0", CONFIG["CHAT_TEMPLATE"])
            self.root.deiconify()
            self.root.attributes("-topmost", True)
        else:
            self.save_current_text_snapshot()
            self.root.withdraw()

    def on_template_changed(self, event=None): self.save_current_text_snapshot()
    def save_current_text_snapshot(self):
        raw_text = self.txt_template.get("1.0", "end-1c")
        CONFIG["CHAT_TEMPLATE"] = raw_text
        save_config()

    def update_spin_params(self):
        try:
            val_num = self.spin_num.get().strip()
            CONFIG["MAX_APP_NUM"] = int(val_num) if val_num.isdigit() else 3
            if CONFIG["MAX_APP_NUM"] < 1: CONFIG["MAX_APP_NUM"] = 1
            if CONFIG["MAX_APP_NUM"] > 5: CONFIG["MAX_APP_NUM"] = 5

            val_tlen = self.spin_tlen.get().strip()
            CONFIG["TITLE_LEN"] = int(val_tlen) if val_tlen.isdigit() else 14
            if CONFIG["TITLE_LEN"] < 0: CONFIG["TITLE_LEN"] = 0

            val_plen = self.spin_plen.get().strip()
            CONFIG["PROC_LEN"] = int(val_plen) if val_plen.isdigit() else 10
            if CONFIG["PROC_LEN"] < 0: CONFIG["PROC_LEN"] = 0
            save_config()
        except Exception: pass

    def toggle_sync(self): state["enable_auto_sync"] = self.sync_var.get()
    def interval_changed(self, val):
        CONFIG["UPDATE_INTERVAL"] = float(val)
        save_config()


# ====================================================================
# 🚀 封装：VRChat 异步日志分析流与剪贴板安全写入
# ====================================================================
def safe_write_clipboard(root_win, text_content):
    try:
        root_win.clipboard_clear()
        root_win.clipboard_append(text_content)
        root_win.update()
    except Exception as err:
        print(f"写入剪贴板失败: {err}")

def vrchat_log_monitor_worker(menu_app):
    last_file = None
    file_handler = None
    
    avatar_pattern = re.compile(r'(avtr_[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})')
    unpack_pattern = re.compile(r'Unpacking Avatar \((.*?)\)')

    while state["running"]:
        if not CONFIG.get("VRC_LOG_ENABLED", True):
            if file_handler:
                file_handler.close()
                file_handler = None
                last_file = None
            time.sleep(1.5)
            continue

        log_dir = CONFIG.get("VRC_LOG_PATH", DEFAULT_VRC_LOG_PATH)
        if not os.path.exists(log_dir):
            time.sleep(3.0)
            continue

        try:
            log_files = [
                os.path.join(log_dir, f) for f in os.listdir(log_dir)
                if f.startswith("output_log_") and f.endswith(".txt")
            ]
            if not log_files:
                time.sleep(2.0)
                continue
                
            latest_file = max(log_files, key=os.path.getmtime)
            
            if latest_file != last_file:
                if file_handler:
                    file_handler.close()
                last_file = latest_file
                file_handler = open(latest_file, "r", encoding="utf-8", errors="ignore")
                file_handler.seek(0, 2)

        except Exception as e:
            print(f"解析日志流异常: {e}")
            time.sleep(2.0)
            continue

        if file_handler:
            line = file_handler.readline()
            if not line:
                time.sleep(0.2)
                continue
            
            clean_line = line.strip()
            
            if "[Behaviour] OnPlayerJoined" in clean_line:
                if CONFIG.get("VRC_NOTIFY_JOIN_LEAVE", True):
                    try:
                        raw_name = clean_line.split("[Behaviour] OnPlayerJoined")[-1].strip()
                        player_name = raw_name.split("(")[0].strip()
                        
                        menu_app.root.after(0, lambda name=player_name: ToastManager.show(
                            title="VRChat 房间动态",
                            message=f"[{name}] 进入了房间",
                            duration=3500,
                            height=90
                        ))
                    except Exception: pass

            elif "[Behaviour] OnPlayerLeft" in clean_line:
                if CONFIG.get("VRC_NOTIFY_JOIN_LEAVE", True):
                    try:
                        raw_name = clean_line.split("[Behaviour] OnPlayerLeft")[-1].strip()
                        player_name = raw_name.split("(")[0].strip()
                        
                        menu_app.root.after(0, lambda name=player_name: ToastManager.show(
                            title="VRChat 房间动态",
                            message=f"[{name}] 离开了房间",
                            duration=3500,
                            height=90
                        ))
                    except Exception: pass

            elif "Unpacking Avatar" in clean_line:
                unpack_match = unpack_pattern.search(clean_line)
                if unpack_match:
                    try:
                        avatar_name = unpack_match.group(1)
                        menu_app.root.after(0, lambda name=avatar_name: ToastManager.show(
                            title="正在解包模型...",
                            message=f"名称: {name}",
                            duration=3000,
                            height=90
                        ))
                    except Exception: pass

            elif "avtr_" in clean_line and "[Behaviour]" in clean_line:
                avatar_match = avatar_pattern.search(clean_line)
                if avatar_match:
                    avtr_id = avatar_match.group(1)
                    now_time = time.time()
                    
                    if avtr_id != state["last_copied_avatar"] or (now_time - state["last_avatar_time"]) > 2.5:
                        state["last_copied_avatar"] = avtr_id
                        state["last_avatar_time"] = now_time
                        web_avatar_url = f"https://vrchat.com/home/avatar/{avtr_id}"
                        
                        if CONFIG.get("VRC_AUTO_COPY_AVATAR", True):
                            menu_app.root.after(0, lambda url=web_avatar_url: safe_write_clipboard(menu_app.root, url))
                            
                            menu_app.root.after(0, lambda aid=avtr_id: ToastManager.show(
                                title="检测到模型变动 (已自动复制)",
                                message=f"模型ID: {aid}\n\n前缀链接已妥善送入剪贴板，可直接在浏览器贴上打开！",
                                duration=5000,
                                height=110
                            ))


def main():
    base_root = tk.Tk()
    base_root.withdraw()

    chat_app = VrcChatOverlay(base_root)
    menu_app = VrcConfigMenu(base_root)

    t_monitor = threading.Thread(target=data_monitor_loop, args=(chat_app, menu_app), daemon=True)
    t_monitor.start()

    t_sim = threading.Thread(target=osc_simulation_high_frequency_loop, daemon=True)
    t_sim.start()

    t_log = threading.Thread(target=vrchat_log_monitor_worker, args=(menu_app,), daemon=True)
    t_log.start()

    base_root.after(150, lambda: ToastManager.show(
        title="系统服务激活", 
        message="EasyChatOSC 已成功就绪\n按 Home 键打开设置界面\n按 T 键打开聊天输入框",
        title_size=12,
        msg_size=10,
        width=340,
        height=120,
        duration=4000
    ))

    def on_t_pressed(): chat_app.root.after(0, chat_app.toggle_box)
    def on_home_pressed():
        if not chat_app.is_visible: menu_app.root.after(0, menu_app.toggle_menu)

    def on_system_switch_triggered():
        if chat_app and chat_app.is_visible: chat_app.root.after(0, chat_app.hide_box)

    def on_exit_triggered():
        print("执行退出...")
        state["running"] = False
        if menu_app:
            menu_app.save_current_text_snapshot()
            menu_app.clear_eye_signals_safely()
            menu_app.clear_gyro_signals_safely()
        save_config()
        try: base_root.after(0, base_root.destroy)
        except Exception: pass
        sys.exit(0)

    keyboard.add_hotkey('t', on_t_pressed, suppress=False)
    keyboard.add_hotkey('home', on_home_pressed, suppress=False)
    keyboard.add_hotkey('home+end', on_exit_triggered)

    keyboard.add_hotkey('windows', on_system_switch_triggered, suppress=False)
    keyboard.add_hotkey('alt+tab', on_system_switch_triggered, suppress=False)
    keyboard.add_hotkey('windows+d', on_system_switch_triggered, suppress=False)
    keyboard.add_hotkey('windows+r', on_system_switch_triggered, suppress=False)

    try: base_root.mainloop()
    except KeyboardInterrupt: pass

if __name__ == "__main__":
    main()