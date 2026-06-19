import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image
import numpy as np
import socket
import threading
import time

class AutoAsciiArtSender:
    def __init__(self, master):
        self.master = master
        master.title("自动字符画发送工具")
        
        # 设置窗口大小
        master.geometry("750x650")
        
        # 初始化变量
        self.image_path = None
        self.ascii_art = None
        self.client_socket = None
        self.connection_active = False
        self.sending_active = False
        self.send_interval = 1.0  # 默认发送间隔1秒
        
        # 使用全角字符集
        self.CHARS = "　．：－＝＋＊＃％＠"  # 全角字符，确保等宽
        
        # 创建GUI界面
        self.create_widgets()
    
    def create_widgets(self):
        """创建GUI组件"""
        # 主框架
        main_frame = tk.Frame(self.master)
        main_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
        
        # 左侧控制面板
        control_frame = tk.Frame(main_frame)
        control_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # 图片选择区域
        img_frame = tk.LabelFrame(control_frame, text="图片处理", padx=5, pady=5)
        img_frame.pack(fill=tk.X, pady=5)
        
        self.select_btn = tk.Button(img_frame, text="选择图片", command=self.select_image, width=15)
        self.select_btn.pack(pady=5)
        
        self.convert_btn = tk.Button(img_frame, text="生成字符画", command=self.generate_art, state=tk.DISABLED, width=15)
        self.convert_btn.pack(pady=5)
        
        self.save_btn = tk.Button(img_frame, text="保存结果", command=self.save_art, state=tk.DISABLED, width=15)
        self.save_btn.pack(pady=5)
        
        # Socket连接区域
        socket_frame = tk.LabelFrame(control_frame, text="Socket设置", padx=5, pady=5)
        socket_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(socket_frame, text="目标IP:").pack(anchor=tk.W)
        self.ip_entry = tk.Entry(socket_frame)
        self.ip_entry.insert(0, "localhost")
        self.ip_entry.pack(fill=tk.X, pady=2)
        
        tk.Label(socket_frame, text="端口:").pack(anchor=tk.W)
        self.port_entry = tk.Entry(socket_frame)
        self.port_entry.insert(0, "12345")
        self.port_entry.pack(fill=tk.X, pady=2)
        
        tk.Label(socket_frame, text="发送间隔(秒):").pack(anchor=tk.W)
        self.interval_entry = tk.Entry(socket_frame)
        self.interval_entry.insert(0, "1.0")
        self.interval_entry.pack(fill=tk.X, pady=2)
        
        self.connect_btn = tk.Button(socket_frame, text="连接", command=self.toggle_connection, width=15)
        self.connect_btn.pack(pady=5)
        
        self.auto_send_btn = tk.Button(socket_frame, text="开始自动发送", command=self.toggle_auto_send, state=tk.DISABLED, width=15)
        self.auto_send_btn.pack(pady=5)
        
        # 状态栏
        self.status_var = tk.StringVar()
        self.status_var.set("就绪")
        self.status_bar = tk.Label(control_frame, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 右侧输出区域
        output_frame = tk.Frame(main_frame)
        output_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        self.text_output = tk.Text(output_frame, height=20, width=60, 
                                 font=('Microsoft YaHei', 10), wrap=tk.NONE,
                                 bg='black', fg='white')
        scroll_x = tk.Scrollbar(output_frame, orient=tk.HORIZONTAL, command=self.text_output.xview)
        scroll_y = tk.Scrollbar(output_frame, command=self.text_output.yview)
        
        self.text_output.configure(xscrollcommand=scroll_x.set, yscrollcommand=scroll_y.set)
        
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_output.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    def select_image(self):
        """选择图片文件"""
        filetypes = [
            ('图片文件', '*.jpg *.jpeg *.png *.bmp'),
            ('所有文件', '*.*')
        ]
        
        self.image_path = filedialog.askopenfilename(
            title="选择图片文件",
            initialdir='/',
            filetypes=filetypes
        )
        
        if self.image_path:
            self.convert_btn.config(state=tk.NORMAL)
            self.update_status(f"已选择: {self.image_path.split('/')[-1]}")
    
    def generate_art(self):
        """生成字符画"""
        if not self.image_path:
            messagebox.showerror("错误", "请先选择图片文件")
            return
        
        try:
            # 打开并处理图片
            img = Image.open(self.image_path).convert('L')  # 转为灰度
            img = img.resize((15, 9), Image.Resampling.LANCZOS)  # 调整到16x9
            
            # 反转亮度，使暗区显示更多字符
            pixels = 255 - np.array(img)
            
            # 归一化到字符集范围
            min_val, max_val = pixels.min(), pixels.max()
            if max_val == min_val:
                normalized = np.zeros_like(pixels)
            else:
                normalized = (pixels - min_val) / (max_val - min_val) * (len(self.CHARS) - 1)
            
            # 生成字符画
            self.ascii_art = ""
            for row in normalized:
                line = [self.CHARS[min(int(val), len(self.CHARS)-1)] for val in row]
                self.ascii_art += "".join(line) + "\n"
            
            # 显示结果
            self.text_output.delete(1.0, tk.END)
            self.text_output.insert(tk.END, self.ascii_art)
            self.save_btn.config(state=tk.NORMAL)
            self.auto_send_btn.config(state=tk.NORMAL if self.connection_active else tk.DISABLED)
            self.update_status("字符画生成完成")
            
        except Exception as e:
            messagebox.showerror("转换错误", f"生成字符画时出错:\n{str(e)}")
            self.update_status(f"错误: {str(e)}")
    
    def save_art(self):
        """保存字符画到文件"""
        if not self.ascii_art:
            messagebox.showerror("错误", "没有可保存的内容")
            return
        
        filetypes = [
            ('文本文件', '*.txt'),
            ('所有文件', '*.*')
        ]
        
        save_path = filedialog.asksaveasfilename(
            title="保存字符画",
            initialdir='/',
            filetypes=filetypes,
            defaultextension='.txt'
        )
        
        if save_path:
            try:
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(self.ascii_art)
                messagebox.showinfo("保存成功", f"字符画已保存到:\n{save_path}")
                self.update_status(f"已保存到: {save_path}")
            except Exception as e:
                messagebox.showerror("保存错误", f"保存文件时出错:\n{str(e)}")
                self.update_status(f"保存错误: {str(e)}")
    
    def toggle_connection(self):
        """连接/断开Socket"""
        if self.connection_active:
            self.stop_auto_send()
            self.disconnect()
        else:
            self.connect()
    
    def connect(self):
        """连接到Socket服务器"""
        ip = self.ip_entry.get()
        port = self.port_entry.get()
        
        if not ip or not port:
            messagebox.showerror("错误", "请输入有效的IP和端口")
            return
        
        try:
            port = int(port)
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((ip, port))
            self.connection_active = True
            self.connect_btn.config(text="断开")
            self.auto_send_btn.config(state=tk.NORMAL if self.ascii_art else tk.DISABLED)
            self.update_status(f"已连接到 {ip}:{port}")
        except Exception as e:
            messagebox.showerror("连接错误", f"连接失败:\n{str(e)}")
            self.update_status(f"连接错误: {str(e)}")
            if self.client_socket:
                self.client_socket.close()
                self.client_socket = None
    
    def disconnect(self):
        """断开Socket连接"""
        self.stop_auto_send()
        
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            finally:
                self.client_socket = None
        
        self.connection_active = False
        self.connect_btn.config(text="连接")
        self.auto_send_btn.config(state=tk.DISABLED, text="开始自动发送")
        self.update_status("已断开连接")
    
    def toggle_auto_send(self):
        """开始/停止自动发送"""
        if self.sending_active:
            self.stop_auto_send()
        else:
            self.start_auto_send()
    
    def start_auto_send(self):
        """开始自动发送"""
        if not self.connection_active or not self.client_socket:
            messagebox.showerror("错误", "未连接到服务器")
            return
        
        if not self.ascii_art:
            messagebox.showerror("错误", "没有可发送的内容")
            return
        
        try:
            self.send_interval = float(self.interval_entry.get())
            if self.send_interval <= 0:
                raise ValueError("间隔时间必须大于0")
        except ValueError as e:
            messagebox.showerror("错误", f"无效的发送间隔: {str(e)}")
            return
        
        self.sending_active = True
        self.auto_send_btn.config(text="停止自动发送")
        self.connect_btn.config(state=tk.DISABLED)
        self.update_status(f"开始自动发送，间隔 {self.send_interval} 秒")
        
        # 启动发送线程
        threading.Thread(
            target=self._auto_send_loop,
            daemon=True
        ).start()
    
    def stop_auto_send(self):
        """停止自动发送"""
        self.sending_active = False
        self.auto_send_btn.config(text="开始自动发送")
        self.connect_btn.config(state=tk.NORMAL)
        self.update_status("已停止自动发送")
    
    def _auto_send_loop(self):
        """自动发送循环"""
        while self.sending_active and self.connection_active:
            try:
                start_time = time.time()
                
                # 发送数据
                self.client_socket.sendall(self.ascii_art.encode('utf-8'))
                self.master.after(0, lambda: self.update_status(f"字符画已发送 ({time.strftime('%H:%M:%S')})"))
                
                # 计算剩余等待时间
                elapsed = time.time() - start_time
                remaining = max(0, self.send_interval - elapsed)
                time.sleep(remaining)
                
            except Exception as e:
                self.master.after(0, lambda: self.update_status(f"发送错误: {str(e)}"))
                self.master.after(0, self.disconnect)
                break
    
    def update_status(self, message):
        """更新状态栏"""
        self.status_var.set(message)
    
    def on_closing(self):
        """窗口关闭时的清理工作"""
        self.disconnect()
        self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = AutoAsciiArtSender(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()