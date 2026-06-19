import tkinter as tk
from tkinter import ttk, messagebox
from pythonosc import udp_client
from threading import Thread
import time

class VRChatOSCChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VRChat OSC 聊天文字工具")
        self.root.geometry("500x650")
        
        # OSC 客户端
        self.osc_client = None
        self.running = False
        self.permanent_running = False
        
        # 创建 GUI
        self.create_widgets()
        
    def create_widgets(self):
        # 连接设置框架
        connection_frame = ttk.LabelFrame(self.root, text="OSC 连接设置", padding=10)
        connection_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(connection_frame, text="IP 地址:").grid(row=0, column=0, sticky=tk.W)
        self.ip_entry = ttk.Entry(connection_frame)
        self.ip_entry.grid(row=0, column=1, sticky=tk.EW, padx=5)
        self.ip_entry.insert(0, "127.0.0.1")  # 默认本地
        
        ttk.Label(connection_frame, text="端口:").grid(row=1, column=0, sticky=tk.W)
        self.port_entry = ttk.Entry(connection_frame)
        self.port_entry.grid(row=1, column=1, sticky=tk.EW, padx=5)
        self.port_entry.insert(0, "9000")  # VRChat 默认 OSC 接收端口
        
        self.connect_btn = ttk.Button(connection_frame, text="连接", command=self.toggle_connection)
        self.connect_btn.grid(row=2, column=0, columnspan=2, pady=5)
        
        # 聊天消息框架
        chat_frame = ttk.LabelFrame(self.root, text="聊天消息设置", padding=10)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        ttk.Label(chat_frame, text="显示的文字:").pack(anchor=tk.W)
        self.chat_entry = tk.Text(chat_frame, height=5)
        self.chat_entry.pack(fill=tk.BOTH, expand=True, pady=5)
        
        ttk.Label(chat_frame, text="显示持续时间(秒):").pack(anchor=tk.W)
        self.duration_entry = ttk.Entry(chat_frame)
        self.duration_entry.pack(fill=tk.X, pady=5)
        self.duration_entry.insert(0, "10")  # 默认10秒
        
        # 按钮框架
        btn_frame = ttk.Frame(chat_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        self.send_btn = ttk.Button(btn_frame, text="发送消息", command=self.send_chat)
        self.send_btn.pack(side=tk.LEFT, padx=5)
        
        self.permanent_btn = ttk.Button(
            btn_frame, 
            text="永久持续", 
            command=self.toggle_permanent_display,
            style='Toggle.TButton' if 'Toggle.TButton' in ttk.Style().theme_names() else None
        )
        self.permanent_btn.pack(side=tk.LEFT, padx=5)
        
        # 自动更新选项
        self.auto_update_var = tk.IntVar()
        self.auto_update_cb = ttk.Checkbutton(
            chat_frame, 
            text="自动更新消息 (每5秒)", 
            variable=self.auto_update_var,
            command=self.toggle_auto_update
        )
        self.auto_update_cb.pack(pady=5)
        
        # 状态栏
        self.status_var = tk.StringVar()
        self.status_var.set("准备就绪")
        ttk.Label(self.root, textvariable=self.status_var).pack(fill=tk.X, padx=10, pady=5)
        
        # 设置列权重
        connection_frame.columnconfigure(1, weight=1)
        
    def toggle_connection(self):
        if self.osc_client is None:
            # 尝试连接
            try:
                ip = self.ip_entry.get()
                port = int(self.port_entry.get())
                self.osc_client = udp_client.SimpleUDPClient(ip, port)
                self.connect_btn.config(text="断开")
                self.status_var.set(f"已连接到 {ip}:{port}")
            except Exception as e:
                messagebox.showerror("连接错误", f"无法连接到 OSC 服务器:\n{str(e)}")
        else:
            # 断开连接
            self.stop_all_updates()
            self.osc_client = None
            self.connect_btn.config(text="连接")
            self.status_var.set("已断开连接")
            
    def send_chat(self):
        if self.osc_client is None:
            messagebox.showwarning("未连接", "请先连接到 OSC 服务器")
            return
            
        message = self.chat_entry.get("1.0", tk.END).strip()
        if not message:
            messagebox.showwarning("空消息", "请输入要显示的文字")
            return
            
        try:
            # VRChat 的 OSC 聊天消息地址
            self.osc_client.send_message("/chatbox/input", [message, True])
            duration = int(self.duration_entry.get())
            self.status_var.set(f"消息已发送: {message} (显示 {duration} 秒)")
        except Exception as e:
            messagebox.showerror("发送错误", f"无法发送消息:\n{str(e)}")
            
    def toggle_auto_update(self):
        if self.auto_update_var.get() == 1:
            if self.permanent_running:
                self.toggle_permanent_display()  # 关闭永久持续如果正在运行
            self.running = True
            Thread(target=self.auto_update_loop, daemon=True).start()
        else:
            self.running = False
            
    def toggle_permanent_display(self):
        if not self.permanent_running:
            if self.auto_update_var.get() == 1:
                self.auto_update_var.set(0)
                self.running = False
            self.permanent_running = True
            self.permanent_btn.config(text="停止持续")
            Thread(target=self.permanent_display_loop, daemon=True).start()
            self.status_var.set("永久持续模式已启用 - 每隔1秒更新消息")
        else:
            self.permanent_running = False
            self.permanent_btn.config(text="永久持续")
            self.status_var.set("永久持续模式已停止")
            
    def stop_all_updates(self):
        """停止所有自动更新"""
        self.running = False
        self.permanent_running = False
        self.auto_update_var.set(0)
        if hasattr(self, 'permanent_btn'):
            self.permanent_btn.config(text="永久持续")
            
    def auto_update_loop(self):
        while self.running:
            if self.osc_client is not None:
                message = self.chat_entry.get("1.0", tk.END).strip()
                if message:
                    try:
                        self.osc_client.send_message("/chatbox/input", [message, True])
                        self.root.event_generate("<<AutoUpdateSuccess>>")
                    except:
                        pass
            time.sleep(5)  # 每5秒更新一次
            
    def permanent_display_loop(self):
        while self.permanent_running:
            if self.osc_client is not None:
                message = self.chat_entry.get("1.0", tk.END).strip()
                if message:
                    try:
                        self.osc_client.send_message("/chatbox/input", [message, True])
                        self.root.event_generate("<<PermanentUpdateSuccess>>")
                    except:
                        pass
            time.sleep(1)  # 每1秒更新一次
            
    def on_auto_update_success(self, event):
        self.status_var.set(f"自动更新消息: {self.chat_entry.get('1.0', tk.END).strip()}")
        
    def on_permanent_update_success(self, event):
        self.status_var.set(f"永久持续更新: {self.chat_entry.get('1.0', tk.END).strip()}")
            
if __name__ == "__main__":
    root = tk.Tk()
    app = VRChatOSCChatApp(root)
    root.bind("<<AutoUpdateSuccess>>", app.on_auto_update_success)
    root.bind("<<PermanentUpdateSuccess>>", app.on_permanent_update_success)
    root.mainloop()