import tkinter as tk
from tkinter import ttk, messagebox
from pythonosc import udp_client
from threading import Thread, Event
import time
import psutil
from collections import deque
import win32gui
import win32process

class VRChatOSCChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VRChat OSC 聊天文字工具")
        self.root.geometry("500x700")  # 增加高度以适应滑块
        
        # OSC 客户端
        self.osc_client = None
        self.running = False
        self.permanent_running = False
        self.permanent_interval = 1.0  # 默认1秒
        
        # 应用监控 - 限制最多3个应用
        self.app_history = deque(maxlen=3)
        self.current_app = ""
        self.monitor_active = True
        self.monitor_thread = None
        
        # 创建 GUI
        self.create_widgets()
        
        # 启动应用监控
        self.start_monitoring()
    
    def create_widgets(self):
        """创建用户界面"""
        # 连接设置框架
        connection_frame = ttk.LabelFrame(self.root, text="OSC 连接设置", padding=10)
        connection_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(connection_frame, text="IP 地址:").grid(row=0, column=0, sticky=tk.W)
        self.ip_entry = ttk.Entry(connection_frame)
        self.ip_entry.grid(row=0, column=1, sticky=tk.EW, padx=5)
        self.ip_entry.insert(0, "127.0.0.1")
        
        ttk.Label(connection_frame, text="端口:").grid(row=1, column=0, sticky=tk.W)
        self.port_entry = ttk.Entry(connection_frame)
        self.port_entry.grid(row=1, column=1, sticky=tk.EW, padx=5)
        self.port_entry.insert(0, "9000")
        
        self.connect_btn = ttk.Button(connection_frame, text="连接", command=self.toggle_connection)
        self.connect_btn.grid(row=2, column=0, columnspan=2, pady=5)
        
        # 聊天消息框架
        chat_frame = ttk.LabelFrame(self.root, text="聊天消息设置", padding=10)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        ttk.Label(chat_frame, text="显示的文字:").pack(anchor=tk.W)
        self.chat_entry = tk.Text(chat_frame, height=5)
        self.chat_entry.pack(fill=tk.BOTH, expand=True, pady=5)
        self.chat_entry.insert("1.0", "在此输入文字\n可使用[rslist]插入应用列表")
        
        ttk.Label(chat_frame, text="显示持续时间(秒):").pack(anchor=tk.W)
        self.duration_entry = ttk.Entry(chat_frame)
        self.duration_entry.pack(fill=tk.X, pady=5)
        self.duration_entry.insert(0, "10")
        
        # 应用历史框架
        history_frame = ttk.LabelFrame(chat_frame, text="最近3个应用 (含[rslist]标记)", padding=10)
        history_frame.pack(fill=tk.BOTH, expand=True)
        
        self.history_text = tk.Text(history_frame, height=3)
        self.history_text.pack(fill=tk.BOTH, expand=True)
        self.history_text.insert("1.0", "[rslist]")
        
        # 永久持续设置框架
        permanent_frame = ttk.Frame(chat_frame)
        permanent_frame.pack(fill=tk.X, pady=5)
        
        # 间隔时间滑块
        ttk.Label(permanent_frame, text="发送间隔:").pack(side=tk.LEFT)
        
        self.interval_slider = ttk.Scale(
            permanent_frame,
            from_=1.0,
            to=5.0,
            value=1.0,
            command=self.update_interval_value
        )
        self.interval_slider.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        self.interval_value = ttk.Label(permanent_frame, text="1.0s")
        self.interval_value.pack(side=tk.LEFT)
        
        # 按钮框架
        btn_frame = ttk.Frame(chat_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        self.send_btn = ttk.Button(btn_frame, text="发送消息", command=self.send_chat)
        self.send_btn.pack(side=tk.LEFT, padx=5)
        
        self.permanent_btn = ttk.Button(
            btn_frame, 
            text="开始持续发送", 
            command=self.toggle_permanent_display
        )
        self.permanent_btn.pack(side=tk.LEFT, padx=5)
        
        # 状态栏
        self.status_var = tk.StringVar()
        self.status_var.set("准备就绪")
        ttk.Label(self.root, textvariable=self.status_var).pack(fill=tk.X, padx=10, pady=5)
        
        # 设置列权重
        connection_frame.columnconfigure(1, weight=1)
    
    def update_interval_value(self, value):
        """更新滑块显示的值"""
        interval = round(float(value), 1)
        self.permanent_interval = interval
        self.interval_value.config(text=f"{interval}s")
    
    def start_monitoring(self):
        """启动应用监控线程"""
        self.monitor_thread = Thread(target=self.monitor_applications, daemon=True)
        self.monitor_thread.start()
    
    def monitor_applications(self):
        """监控当前活动窗口的应用程序"""
        last_app = ""
        while self.monitor_active:
            try:
                window = win32gui.GetForegroundWindow()
                if window:
                    _, pid = win32process.GetWindowThreadProcessId(window)
                    process = psutil.Process(pid)
                    current_app = process.name()
                    
                    if current_app and current_app != last_app:
                        last_app = current_app
                        self.current_app = current_app
                        self.app_history.appendleft(current_app)
                        self.root.after(0, self.update_history_display)
                
                time.sleep(1)
            except (psutil.NoSuchProcess, psutil.AccessDenied, win32process.error):
                pass
            except Exception as e:
                print(f"监控错误: {e}")
    
    def update_history_display(self):
        """更新应用历史显示"""
        history_content = self.history_text.get("1.0", tk.END).strip()
        if "[rslist]" in history_content:
            new_content = history_content.replace(
                "[rslist]", 
                "\n".join(self.app_history)
            )
            self.history_text.delete("1.0", tk.END)
            self.history_text.insert("1.0", new_content)
    
    def get_processed_message(self):
        """获取处理后的消息内容（替换[rslist]）"""
        message = self.chat_entry.get("1.0", tk.END).strip()
        if "[rslist]" in message:
            return message.replace(
                "[rslist]", 
                "\n".join(self.app_history)
            )
        return message
    
    def toggle_connection(self):
        if self.osc_client is None:
            try:
                ip = self.ip_entry.get()
                port = int(self.port_entry.get())
                self.osc_client = udp_client.SimpleUDPClient(ip, port)
                self.connect_btn.config(text="断开")
                self.status_var.set(f"已连接到 {ip}:{port}")
            except Exception as e:
                messagebox.showerror("连接错误", f"无法连接到 OSC 服务器:\n{str(e)}")
        else:
            self.stop_all_updates()
            self.osc_client = None
            self.connect_btn.config(text="连接")
            self.status_var.set("已断开连接")
    
    def send_chat(self):
        if self.osc_client is None:
            messagebox.showwarning("未连接", "请先连接到 OSC 服务器")
            return
        
        message = self.get_processed_message()
        if not message:
            messagebox.showwarning("空消息", "请输入要显示的文字")
            return
        
        try:
            self.osc_client.send_message("/chatbox/input", [message, True])
            duration = int(self.duration_entry.get())
            self.status_var.set(f"消息已发送: {message[:20]}... (显示 {duration} 秒)")
        except Exception as e:
            messagebox.showerror("发送错误", f"无法发送消息:\n{str(e)}")
    
    def toggle_permanent_display(self):
        if not self.permanent_running:
            if self.osc_client is None:
                messagebox.showwarning("未连接", "请先连接到 OSC 服务器")
                return
            
            self.permanent_running = True
            self.permanent_btn.config(text="停止持续发送")
            Thread(target=self.permanent_display_loop, daemon=True).start()
            self.status_var.set(f"持续发送已启用 ({self.permanent_interval}s间隔)")
        else:
            self.permanent_running = False
            self.permanent_btn.config(text="开始持续发送")
            self.status_var.set("持续发送已停止")
    
    def permanent_display_loop(self):
        """持续发送循环，使用滑块设置的间隔时间"""
        while self.permanent_running and self.osc_client is not None:
            start_time = time.time()
            
            message = self.get_processed_message()
            if message:
                try:
                    self.osc_client.send_message("/chatbox/input", [message, True])
                    self.root.event_generate("<<PermanentUpdateSuccess>>")
                except Exception as e:
                    print(f"发送错误: {e}")
            
            # 计算剩余等待时间
            elapsed = time.time() - start_time
            remaining = max(0, self.permanent_interval - elapsed)
            time.sleep(remaining)
    
    def stop_all_updates(self):
        """停止所有自动更新"""
        self.running = False
        self.permanent_running = False
        self.permanent_btn.config(text="开始持续发送")
    
    def on_permanent_update_success(self, event):
        self.status_var.set(f"持续发送: {self.get_processed_message()[:20]}... (间隔 {self.permanent_interval}s)")
    
    def on_closing(self):
        """关闭窗口时的清理工作"""
        self.monitor_active = False
        self.stop_all_updates()
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1)
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = VRChatOSCChatApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.bind("<<PermanentUpdateSuccess>>", app.on_permanent_update_success)
    root.mainloop()