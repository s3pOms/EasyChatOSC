import tkinter as tk
from tkinter import ttk, messagebox
from pythonosc import udp_client
from threading import Thread, Event, Lock
import time
import psutil
from collections import deque
import win32gui
import win32process
import socket
import threading
import queue

class VRChatOSCChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("EasyChatOSC")
        self.root.geometry("550x750")  # 稍微增大窗口以适应新控件
        
        # 性能监控
        self.cpu_usage = 0
        self.ram_usage = 0
        self.perf_monitor_active = True
        self.perf_monitor_thread = None
        
        # OSC 客户端
        self.osc_client = None
        self.running = False
        self.permanent_running = False
        self.permanent_interval = 1.5  # 默认1.5秒
        
        # 应用监控
        self.max_app_history = 3  # 默认显示3个
        self.title_length = 14    # 默认标题显示长度
        self.process_length = 10  # 默认进程名显示长度
        self.app_history = deque(maxlen=5)  # 最大存储5个
        self.current_app = ("", "")
        self.monitor_active = True
        self.monitor_thread = None
        
        # Socket 服务器
        self.socket_server = None
        self.socket_thread = None
        self.socket_receive_thread = None
        self.socket_clients = []
        self.socket_response = "等待Socket响应..."
        self.socket_lock = Lock()
        self.socket_queue = queue.Queue()
        
        # 创建主界面
        self.create_widgets()
        
        # 启动监控线程
        self.start_monitoring()
        self.start_performance_monitoring()
        self.create_socket_server()
        self.start_socket_receiver()
    
    def create_widgets(self):
        """创建主界面控件"""
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
        self.chat_entry.insert("1.0", "在此输入文字\n可用标记: [rslist] [CPU%] [RAM%] [scoket]")
        
        ttk.Label(chat_frame, text="显示持续时间(秒):").pack(anchor=tk.W)
        self.duration_entry = ttk.Entry(chat_frame)
        self.duration_entry.pack(fill=tk.X, pady=5)
        self.duration_entry.insert(0, "10")
        
        # 性能监控框架
        perf_frame = ttk.LabelFrame(chat_frame, text="系统性能", padding=10)
        perf_frame.pack(fill=tk.X, pady=5)
        
        # 修改为进度条样式
        self.cpu_label = ttk.Label(perf_frame, text="CPU: [▒▒▒▒▒▒▒▒▒] 0.0%")
        self.cpu_label.pack(side=tk.LEFT, padx=5)
        
        self.ram_label = ttk.Label(perf_frame, text="RAM: [▒▒▒▒▒▒▒▒▒] 0.0%")
        self.ram_label.pack(side=tk.LEFT, padx=5)
        
        # 应用历史设置框架
        history_setting_frame = ttk.Frame(chat_frame)
        history_setting_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(history_setting_frame, text="显示最近应用数量:").pack(side=tk.LEFT)
        self.history_num = tk.IntVar(value=3)
        ttk.Spinbox(
            history_setting_frame,
            from_=1,
            to=5,
            textvariable=self.history_num,
            width=3,
            command=self.update_history_display
        ).pack(side=tk.LEFT, padx=5)
        
        # 添加标题长度设置
        ttk.Label(history_setting_frame, text="标题长度:").pack(side=tk.LEFT, padx=(10,0))
        self.title_length_var = tk.IntVar(value=14)
        ttk.Spinbox(
            history_setting_frame,
            from_=0,
            to=30,
            textvariable=self.title_length_var,
            width=3,
            command=self.update_history_display
        ).pack(side=tk.LEFT)
        
        # 添加进程名长度设置
        ttk.Label(history_setting_frame, text="进程名长度:").pack(side=tk.LEFT, padx=(10,0))
        self.process_length_var = tk.IntVar(value=10)
        ttk.Spinbox(
            history_setting_frame,
            from_=0,
            to=30,
            textvariable=self.process_length_var,
            width=3,
            command=self.update_history_display
        ).pack(side=tk.LEFT)
        
        # 应用历史框架
        history_frame = ttk.LabelFrame(chat_frame, text="最近应用 (标题|进程名)", padding=10)
        history_frame.pack(fill=tk.BOTH, expand=True)
        
        self.history_text = tk.Text(history_frame, height=3)
        self.history_text.pack(fill=tk.BOTH, expand=True)
        self.history_text.insert("1.0", "[rslist]")
        
        # 持续发送设置框架
        permanent_frame = ttk.Frame(chat_frame)
        permanent_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(permanent_frame, text="持续发送间隔:").pack(side=tk.LEFT)
        
        self.interval_slider = ttk.Scale(
            permanent_frame,
            from_=1.5,
            to=5.0,
            value=1.5,
            command=self.update_interval_value
        )
        self.interval_slider.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        self.interval_value = ttk.Label(permanent_frame, text="1.5s")
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
    
    def draw_progress_bar(self, percentage, bar_length=9):
        """绘制进度条"""
        filled_length = int(bar_length * percentage // 100)
        bar = '█' * filled_length + '▒' * (bar_length - filled_length)
        return f"[{bar}]"
    
    def start_performance_monitoring(self):
        """启动性能监控线程"""
        self.perf_monitor_thread = Thread(target=self.monitor_performance, daemon=True)
        self.perf_monitor_thread.start()
        self.status_var.set("性能监控已启动")
    
    def monitor_performance(self):
        """监控系统性能"""
        while self.perf_monitor_active:
            try:
                # 获取CPU使用率
                self.cpu_usage = psutil.cpu_percent(interval=1)
                
                # 获取内存使用率
                mem = psutil.virtual_memory()
                self.ram_usage = mem.percent
                
                # 更新UI
                self.root.after(0, self.update_performance_display)
                
            except Exception as e:
                self.status_var.set(f"性能监控错误: {e}")
                time.sleep(1)
    
    def update_performance_display(self):
        """更新性能显示"""
        cpu_bar = self.draw_progress_bar(self.cpu_usage)
        ram_bar = self.draw_progress_bar(self.ram_usage)
        
        self.cpu_label.config(text=f"CPU: {cpu_bar} {self.cpu_usage:.1f}%")
        self.ram_label.config(text=f"RAM: {ram_bar} {self.ram_usage:.1f}%")
    
    def start_monitoring(self):
        """启动应用监控线程"""
        self.monitor_thread = Thread(target=self.monitor_applications, daemon=True)
        self.monitor_thread.start()
        self.status_var.set("应用监控已启动")
    
    def monitor_applications(self):
        """监控当前活动窗口的应用程序"""
        last_app = ("", "")
        while self.monitor_active:
            try:
                window = win32gui.GetForegroundWindow()
                if window:
                    title = win32gui.GetWindowText(window)
                    # 不再在这里截断标题，将在显示时处理
                    
                    _, pid = win32process.GetWindowThreadProcessId(window)
                    process = psutil.Process(pid)
                    process_name = process.name()
                    # 不再在这里截断进程名，将在显示时处理
                    
                    current_app = (title, process_name)
                    
                    if current_app != last_app:
                        last_app = current_app
                        self.current_app = current_app
                        self.app_history.appendleft(current_app)
                        self.root.after(0, self.update_history_display)
                
                time.sleep(1)
            except (psutil.NoSuchProcess, psutil.AccessDenied, win32process.error):
                pass
            except Exception as e:
                self.status_var.set(f"应用监控错误: {e}")
    
    def format_app_entry(self, title, process_name):
        """格式化应用条目，根据设置的长度截断"""
        title_len = self.title_length_var.get()
        process_len = self.process_length_var.get()
        
        # 处理标题
        if title_len == 0:
            formatted_title = ""
        else:
            formatted_title = (title[:title_len] + '..') if len(title) > title_len and title_len > 0 else title
        
        # 处理进程名
        if process_len == 0:
            formatted_process = ""
        else:
            formatted_process = (process_name[:process_len] + '..') if len(process_name) > process_len and process_len > 0 else process_name
        
        # 根据是否为空决定分隔符
        if formatted_title and formatted_process:
            return f"{formatted_title} | {formatted_process}"
        elif formatted_title:
            return formatted_title
        elif formatted_process:
            return formatted_process
        else:
            return ""  # 如果两者都设置为0长度，则返回空字符串
    
    def update_history_display(self):
        """更新应用历史显示"""
        history_content = self.history_text.get("1.0", tk.END).strip()
        if "[rslist]" in history_content:
            # 根据设置的数量显示最近的应用
            num_to_show = min(self.history_num.get(), len(self.app_history))
            app_list = []
            for title, exe in list(self.app_history)[:num_to_show]:
                formatted_entry = self.format_app_entry(title, exe)
                if formatted_entry:  # 只有格式化后不为空才添加
                    app_list.append(formatted_entry)
            
            if app_list:  # 如果有要显示的内容
                new_content = history_content.replace(
                    "[rslist]", 
                    "\n".join(app_list)
                )
            else:  # 如果所有条目都因为长度为0被过滤掉了
                new_content = history_content.replace("[rslist]", "(应用显示已关闭)")
            
            self.history_text.delete("1.0", tk.END)
            self.history_text.insert("1.0", new_content)
    
    def create_socket_server(self):
        """创建本地Socket服务器"""
        try:
            self.socket_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket_server.bind(('localhost', 12345))
            self.socket_server.listen(5)
            self.socket_thread = threading.Thread(target=self.accept_socket_connections, daemon=True)
            self.socket_thread.start()
            self.status_var.set("Socket服务器已启动 (端口:12345)")
        except Exception as e:
            messagebox.showerror("Socket错误", f"无法启动Socket服务器:\n{str(e)}")
    
    def start_socket_receiver(self):
        """启动Socket消息接收线程"""
        self.socket_receive_thread = threading.Thread(target=self.process_socket_messages, daemon=True)
        self.socket_receive_thread.start()
    
    def process_socket_messages(self):
        """处理Socket队列中的消息（在独立线程中运行）"""
        while True:
            try:
                client, message = self.socket_queue.get(timeout=0.1)
                
                with self.socket_lock:
                    self.socket_response = message
                
                if "REQUEST_DATA" in message:
                    response = "这是来自Socket的实时数据"
                    try:
                        client.sendall(response.encode('utf-8'))
                    except Exception as e:
                        print(f"发送响应失败: {e}")
                
            except queue.Empty:
                if not self.socket_server:  # 如果服务器已关闭则退出
                    break
                continue
            except Exception as e:
                print(f"处理消息错误: {e}")
    
    def accept_socket_connections(self):
        """接受Socket连接（在独立线程中运行）"""
        while True:
            try:
                client, addr = self.socket_server.accept()
                self.socket_clients.append(client)
                self.status_var.set(f"新的Socket连接: {addr[0]}")
                
                # 为每个客户端启动接收线程
                threading.Thread(
                    target=self.receive_from_socket_client,
                    args=(client,),
                    daemon=True
                ).start()
                
            except Exception as e:
                if self.socket_server:
                    print(f"接受连接错误: {e}")
                break
    
    def receive_from_socket_client(self, client):
        """从Socket客户端接收消息（每个客户端一个线程）"""
        try:
            while True:
                data = client.recv(1024).decode('utf-8')
                if not data:
                    break
                
                self.socket_queue.put((client, data))
                
        except Exception as e:
            print(f"接收客户端消息错误: {e}")
        finally:
            client.close()
            if client in self.socket_clients:
                self.socket_clients.remove(client)
    
    def send_to_socket_clients(self, message):
        """向所有Socket客户端发送消息"""
        for client in self.socket_clients[:]:
            try:
                client.sendall(message.encode('utf-8'))
            except Exception as e:
                print(f"发送到Socket客户端失败: {e}")
                self.socket_clients.remove(client)
    
    def update_interval_value(self, value):
        """更新滑块显示的值"""
        interval = max(1.5, min(5.0, round(float(value), 1)))  # 限制在1.5-5.0之间
        self.permanent_interval = interval
        self.interval_value.config(text=f"{interval:.1f}s")
    
    def get_processed_message(self):
        """获取处理后的消息内容（替换各种标记）"""
        message = self.chat_entry.get("1.0", tk.END).strip()
        
        if "[rslist]" in message:
            # 根据设置的数量显示最近的应用
            num_to_show = min(self.history_num.get(), len(self.app_history))
            app_list = []
            for title, exe in list(self.app_history)[:num_to_show]:
                formatted_entry = self.format_app_entry(title, exe)
                if formatted_entry:  # 只有格式化后不为空才添加
                    app_list.append(formatted_entry)
            
            if app_list:  # 如果有要显示的内容
                message = message.replace("[rslist]", "\n".join(app_list))
            else:  # 如果所有条目都因为长度为0被过滤掉了
                message = message.replace("[rslist]", "(应用显示已关闭)")
        
        if "[CPU%]" in message:
            cpu_bar = self.draw_progress_bar(self.cpu_usage)
            message = message.replace("[CPU%]", f"{cpu_bar} CPU {self.cpu_usage:.1f}%")
        
        if "[RAM%]" in message:
            ram_bar = self.draw_progress_bar(self.ram_usage)
            message = message.replace("[RAM%]", f"{ram_bar} RAM {self.ram_usage:.1f}%")
        
        if "[scoket]" in message:
            # 向所有Socket客户端请求数据
            self.socket_response = "等待Socket响应..."
            self.send_to_socket_clients("REQUEST_DATA")
            
            # 等待响应（最多2秒）
            start_time = time.time()
            while self.socket_response == "等待Socket响应..." and time.time() - start_time < 2:
                time.sleep(0.1)
            
            message = message.replace("[scoket]", self.socket_response)
        
        return message
    
    def toggle_connection(self):
        if self.osc_client is None:
            try:
                ip = self.ip_entry.get()
                port = int(self.port_entry.get())
                self.osc_client = udp_client.SimpleUDPClient(ip, port)
                self.connect_btn.config(text="断开")
                self.status_var.set(f"已连接到 OSC 服务器 {ip}:{port}")
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
            self.status_var.set(f"消息已发送: {message[:50]}... (显示 {duration} 秒)")
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
            self.status_var.set(f"持续发送已启用 ({self.permanent_interval:.1f}s间隔)")
        else:
            self.permanent_running = False
            self.permanent_btn.config(text="开始持续发送")
            self.status_var.set("持续发送已停止")
    
    def permanent_display_loop(self):
        """持续发送循环"""
        while self.permanent_running and self.osc_client is not None:
            start_time = time.time()
            
            message = self.get_processed_message()
            if message:
                try:
                    self.osc_client.send_message("/chatbox/input", [message, True])
                    self.root.event_generate("<<PermanentUpdateSuccess>>")
                except Exception as e:
                    self.status_var.set(f"持续发送错误: {e}")
            
            elapsed = time.time() - start_time
            remaining = max(0, self.permanent_interval - elapsed)
            time.sleep(remaining)
    
    def stop_all_updates(self):
        """停止所有自动更新"""
        self.running = False
        self.permanent_running = False
        self.permanent_btn.config(text="开始持续发送")
    
    def on_permanent_update_success(self, event):
        self.status_var.set(f"持续发送: {self.get_processed_message()[:50]}...")
    
    def on_closing(self):
        """关闭窗口时的清理工作"""
        # 停止所有监控
        self.monitor_active = False
        self.perf_monitor_active = False
        self.stop_all_updates()
        
        # 关闭Socket服务器
        if self.socket_server:
            self.socket_server.close()
            self.socket_server = None
        
        # 关闭所有Socket客户端
        for client in self.socket_clients:
            client.close()
        
        # 等待线程结束
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1)
        
        if self.perf_monitor_thread and self.perf_monitor_thread.is_alive():
            self.perf_monitor_thread.join(timeout=1)
        
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = VRChatOSCChatApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.bind("<<PermanentUpdateSuccess>>", app.on_permanent_update_success)
    root.mainloop()
