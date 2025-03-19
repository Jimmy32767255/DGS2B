"""
DG-LAB V3 SOCKET To V2 BLE 转换器
--------------------------------

这个程序实现了DG-LAB V3协议到V2 BLE协议的转换功能。
主要功能包括：
1. 蓝牙设备扫描和连接
2. WebSocket服务器连接
3. 实时波形显示
4. 多语言支持
5. 深色/浅色主题切换
6. 日志记录和显示

主要组件：
- MainWindow: 主窗口类，处理UI和主要业务逻辑
- DeviceScanner: 蓝牙设备扫描对话框
- LogWindow: 日志显示窗口
- DeviceSignals: 信号处理类

作者: 我张智杰实名上网、赵明
版本: 1.0.0 semver
"""

import sys
import asyncio
import json
import struct
import logging
import os
import glob
import re
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTextEdit, QGroupBox, QDialog, QListWidget, QFrame,
    QComboBox, QMessageBox, QColorDialog, QFileDialog
)
from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QIcon, QFont, QColor
from qasync import QEventLoop, asyncSlot
import websockets
from bleak import BleakClient, discover, BleakError
from collections import deque
from PySide6.QtGui import QIntValidator
import pyqtgraph as pg

# ------------ 事件循环策略（Windows必需）------------
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ------------ 控制台Debug日志设置 ------------
logging.basicConfig(level=logging.DEBUG)

# ------------ 全局配置 ------------
# 配置文件路径
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dg_lab_config.json")
# WebSocket服务器地址
SOCKET_URI = ""
# 蓝牙设备地址
BLE_DEVICE_ADDRESS = ""
# 设备ID
DEVICE_ID = ""
# 默认最大强度设置
DEFAULT_MAX_STRENGTH = {'A': 100, 'B': 100}
# 语言包路径
LANG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "languages")
# 当前语言
CURRENT_LANG = "zh_CN"
# 翻译字典
TRANSLATIONS = {}
# 默认强调色
DEFAULT_ACCENT_COLOR = "#7f744f"
# 默认背景图片
DEFAULT_BACKGROUND_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "background.png")


# ------------ 蓝牙服务配置 ------------
# 主服务UUID
BLE_SERVICE_UUID = "955A180b-0FE2-F5AA-A094-84B8D4F3E8AD"
# 设备ID特征UUID
BLE_CHAR_DEVICE_ID = "955A1501-0FE2-F5AA-A094-84B8D4F3E8AD"
# 电池服务UUID
BLE_SERVICE_BATTERY = "0000180f-0000-1000-8000-00805f9b34fb"

# ------------ BLE 特征值 UUID ------------
# PWM通道A特征值UUID 
BLE_CHAR_PWM_A34 = "0000ffe1-0000-1000-8000-00805f9b34fb"
# PWM通道B特征值UUID 
BLE_CHAR_PWM_B34 = "0000ffe2-0000-1000-8000-00805f9b34fb"
# PWM通道AB特征值UUID 
BLE_CHAR_PWM_AB2 = "0000ffe3-0000-1000-8000-00805f9b34fb"
# 电池电量特征值UUID
BLE_CHAR_BATTERY = "0000ffe4-0000-1000-8000-00805f9b34fb"

# ------------ 多语言支持函数 ------------
def load_available_languages():
    """加载所有可用的语言包文件"""
    logging.info("开始加载可用语言...")
    languages = {}
    
    # 检查语言目录是否存在
    if not os.path.exists(LANG_PATH):
        logging.error(f"语言目录不存在: {os.path.abspath(LANG_PATH)}")
        return languages
    
    # 获取语言文件列表
    lang_files = glob.glob(os.path.join(LANG_PATH, "*.json"))
    logging.info(f"找到语言文件列表: {lang_files}")
    
    if not lang_files:
        logging.error(f"在目录 {os.path.abspath(LANG_PATH)} 中没有找到任何json文件")
        return languages
    
    for lang_file in lang_files:
        lang_code = os.path.splitext(os.path.basename(lang_file))[0]
        logging.info(f"正在处理语言文件: {lang_file}")
        
        try:
            with open(lang_file, 'r', encoding='utf-8') as f:
                try:
                    lang_data = json.load(f)
                    logging.info(f"成功解析语言文件: {lang_file}")
                    if "language_name" in lang_data:
                        lang_name = lang_data["language_name"]
                        logging.info(f"找到语言名称: {lang_name}")
                    else:
                        lang_name = lang_code
                        logging.warning(f"语言文件中没有language_name字段，使用文件名作为语言名称: {lang_code}")
                    languages[lang_code] = lang_name
                except json.JSONDecodeError as je:
                    logging.error(f"语言文件JSON解析失败 {lang_file}: {str(je)}")
                    continue
        except Exception as e:
            logging.error(f"读取语言文件失败 {lang_file}: {str(e)}")
            continue
    
    logging.info(f"最终加载的语言列表: {languages}")
    return languages

def load_language(lang_code):
    """加载指定的语言包"""
    global TRANSLATIONS
    logging.info(f"开始加载语言包: {lang_code}")
    
    try:
        lang_file = os.path.join(LANG_PATH, f"{lang_code}.json")
        abs_path = os.path.abspath(lang_file)
        logging.info(f"语言文件完整路径: {abs_path}")
        
        if not os.path.exists(lang_file):
            logging.error(f"语言文件不存在: {abs_path}")
            return False
            
        try:
            with open(lang_file, 'r', encoding='utf-8') as f:
                file_content = f.read()
                logging.info(f"成功读取语言文件，内容长度: {len(file_content)} 字节")
                try:
                    TRANSLATIONS = json.loads(file_content)
                    logging.info(f"成功解析语言文件，包含 {len(TRANSLATIONS)} 个翻译项")
                    return True
                except json.JSONDecodeError as je:
                    logging.error(f"语言文件JSON解析失败: {str(je)}")
                    return False
        except Exception as e:
            logging.error(f"读取语言文件失败: {str(e)}")
            return False
    except Exception as e:
        logging.error(f"加载语言包过程中发生错误: {str(e)}")
        return False

def translate(key, *args):
    """翻译指定的文本键值，支持格式化参数"""
    global TRANSLATIONS
    
    # 处理嵌套键，如 "status_updates.connection_failed"
    keys = key.split('.')
    value = TRANSLATIONS
    
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            # 键不存在，返回原始键
            return key
    
    # 如果不是字符串，返回原始键
    if not isinstance(value, str):
        return key
    
    # 格式化替换 {0}, {1} 等参数
    if args:
        try:
            return value.format(*args)
        except:
            return value
    
    return value

# ------------ 界面样式定义 ------------
def get_style(accent_color=DEFAULT_ACCENT_COLOR, background_image=None):
    """获取应用样式表
    
    根据强调色生成深色主题样式表。
    
    Args:
        accent_color: 强调色（十六进制颜色代码）
        background_image: 背景图片路径
        
    Returns:
        str: 样式表字符串
    """
    # 基础颜色
    base_bg = "#2b2b2b"
    text_color = "#ffffff"
    border_color = "#3f3f3f"
    hover_bg = "#3f3f3f"
    disabled_bg = "#404040"
    disabled_text = "#808080"
    
    # 背景图片样式
    background_style = ""
    if background_image and os.path.exists(background_image):
        bg_path = background_image.replace('\\', '/')
        background_style = """
            QMainWindow, QDialog {
                background-image: url("%s");
                background-position: center;
                background-repeat: no-repeat;
                background-attachment: fixed;
            }
        """ % bg_path
    
    base_style = """
        QMainWindow, QDialog {
            background-color: %s;
            color: %s;
        }
        
        QWidget {
            background-color: transparent;
            color: %s;
        }
        
        QPushButton {
            background-color: %s;
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 3px;
        }
        
        QPushButton:hover {
            background-color: %s;
        }
        
        QPushButton:disabled {
            background-color: %s;
            color: %s;
        }
        
        QLineEdit, QTextEdit, QComboBox {
            background-color: rgba(43, 43, 43, 180);
            color: %s;
            border: 1px solid %s;
            padding: 3px;
            border-radius: 2px;
        }
        
        QGroupBox {
            border: 1px solid rgba(63, 63, 63, 180);
            margin-top: 0.5em;
            padding-top: 0.5em;
            background-color: rgba(43, 43, 43, 120);
        }
        
        QGroupBox::title {
            color: %s;
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 3px;
            background-color: transparent;
        }
        
        QLabel {
            color: %s;
            background-color: transparent;
        }
        
        QMenuBar {
            background-color: rgba(43, 43, 43, 180);
            color: %s;
        }
        
        QMenuBar::item:selected {
            background-color: %s;
        }
        
        QMenu {
            background-color: rgba(43, 43, 43, 180);
            color: %s;
        }
        
        QMenu::item:selected {
            background-color: %s;
        }
        
        QListWidget {
            background-color: rgba(43, 43, 43, 180);
            color: %s;
            border: 1px solid rgba(63, 63, 63, 180);
        }
        
        QListWidget::item:selected {
            background-color: %s;
            color: white;
        }

        /* 滚动条样式 */
        QScrollBar:vertical {
            border: none;
            background-color: rgba(43, 43, 43, 120);
            width: 10px;
            margin: 0px;
        }

        QScrollBar::handle:vertical {
            background-color: rgba(63, 63, 63, 180);
            min-height: 20px;
            border-radius: 5px;
        }

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }

        QScrollBar:horizontal {
            border: none;
            background-color: rgba(43, 43, 43, 120);
            height: 10px;
            margin: 0px;
        }

        QScrollBar::handle:horizontal {
            background-color: rgba(63, 63, 63, 180);
            min-width: 20px;
            border-radius: 5px;
        }

        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }
    """ % (
        base_bg, text_color,  # QMainWindow, QDialog
        text_color,  # QWidget
        accent_color,  # QPushButton
        hover_bg,  # QPushButton:hover
        disabled_bg, disabled_text,  # QPushButton:disabled
        text_color, border_color,  # QLineEdit, QTextEdit, QComboBox
        text_color,  # QGroupBox::title
        text_color,  # QLabel
        text_color,  # QMenuBar
        hover_bg,  # QMenuBar::item:selected
        text_color,  # QMenu
        hover_bg,  # QMenu::item:selected
        text_color,  # QListWidget
        accent_color  # QListWidget::item:selected
    )
    
    return background_style + base_style

# ------------ 辅助函数 ------------
def is_valid_websocket_url(url):
    """验证WebSocket URL是否有效
    
    使用正则表达式检查URL格式是否符合WebSocket协议要求。
    
    Args:
        url (str): 要验证的WebSocket URL
        
    Returns:
        bool: URL格式是否有效
    """
    # 检查URL格式
    ws_pattern = r'^(ws|wss):\/\/[^\s\/$.?#].[^\s]*$'
    return bool(re.match(ws_pattern, url))

async def check_bluetooth_available():
    """检查蓝牙是否可用
    
    尝试执行设备发现操作来检查蓝牙功能是否正常。
    
    Returns:
        bool: 蓝牙是否可用
    """
    try:
        devices = await discover()
        return True
    except BleakError:
        return False
    except Exception:
        return False

class DeviceScanner(QDialog):
    """蓝牙设备扫描对话框
    
    这个类提供了一个模态对话框，用于扫描和选择蓝牙设备。
    主要功能：
    1. 自动扫描附近的蓝牙设备
    2. 显示设备列表
    3. 支持手动刷新设备列表
    4. 支持双击选择设备
    5. 适配深色/浅色主题
    
    属性:
        device_list (QListWidget): 显示扫描到的设备列表
        refresh_btn (QPushButton): 刷新按钮
        cancel_btn (QPushButton): 取消按钮
        status_label (QLabel): 显示扫描状态
        scan_task (asyncio.Task): 当前的扫描任务
    """
    
    def __init__(self, parent=None):
        """初始化扫描对话框
        
        Args:
            parent: 父窗口对象，通常是MainWindow实例
        """
        super().__init__(parent)
        self.setWindowTitle(translate("dialog.choose_device"))
        self.setGeometry(200, 200, 400, 400)
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowTitleHint)
        
        # 获取父窗口的强调色
        self.accent_color = parent.accent_color if parent else DEFAULT_ACCENT_COLOR
        
        # 创建布局
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # 标题
        title_label = QLabel(translate("dialog.choose_device"))
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # 设备列表
        self.device_list = QListWidget()
        self.device_list.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid #cccccc;
                border-radius: 5px;
                padding: 5px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-bottom: 1px solid #cccccc;
            }}
            QListWidget::item:selected {{
                background-color: {self.accent_color};
                color: white;
            }}
        """)
        layout.addWidget(self.device_list)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        self.refresh_btn = QPushButton(translate("dialog.refresh_devices"))
        self.refresh_btn.setMinimumWidth(120)
        self.cancel_btn = QPushButton(translate("dialog.cancel"))
        self.cancel_btn.setMinimumWidth(120)
        button_layout.addWidget(self.refresh_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)
        
        # 状态标签
        self.status_label = QLabel(translate("dialog.scanning"))
        self.status_label.setStyleSheet("color: #666666;")
        layout.addWidget(self.status_label)
        
        self.setLayout(layout)
        
        # 连接信号
        self.refresh_btn.clicked.connect(self.on_refresh_clicked)
        self.cancel_btn.clicked.connect(self.reject)
        
        # 扫描任务
        self.scan_task = None
        
        # 应用主题
        self.apply_theme()
        
        # 初始禁用刷新按钮，等待第一次扫描完成
        self.refresh_btn.setEnabled(False)
        
        # 使用QTimer延迟执行初始扫描
        QTimer.singleShot(100, self.start_initial_scan)

    def start_initial_scan(self):
        """初始化扫描"""
        try:
            loop = asyncio.get_event_loop()
            if self.scan_task and not self.scan_task.done():
                self.scan_task.cancel()
            self.scan_task = loop.create_task(self._do_scan())
        except Exception as e:
            logging.error(f"启动扫描失败: {str(e)}")
            self.status_label.setText(translate("dialog.scan_failed", str(e)))
            self.refresh_btn.setEnabled(True)

    async def _do_scan(self):
        """执行实际的扫描操作"""
        try:
            self.refresh_btn.setEnabled(False)
            self.status_label.setText(translate("dialog.scanning"))
            self.device_list.clear()
            
            # 检查蓝牙是否可用
            if not await check_bluetooth_available():
                self.status_label.setText(translate("dialog.bluetooth_not_available"))
                self.refresh_btn.setEnabled(True)
                return

            # 执行设备发现
            try:
                devices = await discover()
                logging.debug(f"发现设备数量: {len(devices)}")
                
                self.device_list.clear()
                for d in devices:
                    logging.debug(f"发现设备: {d.name} | {d.address}")
                    item_text = f"{d.name} | {d.address}" if d.name else f"{translate('device.unknown')} | {d.address}"
                    self.device_list.addItem(item_text)
                
                # 更新扫描状态
                if not devices:
                    self.status_label.setText(translate("dialog.no_devices_found"))
                else:
                    self.status_label.setText(translate("dialog.scan_complete"))
                    
            except BleakError as be:
                logging.error(f"蓝牙扫描错误: {str(be)}")
                self.status_label.setText(translate("dialog.scan_failed", str(be)))
            except Exception as e:
                logging.error(f"扫描过程发生错误: {str(e)}")
                self.status_label.setText(translate("dialog.scan_failed", str(e)))
                
        except Exception as e:
            logging.error(f"扫描操作失败: {str(e)}")
            self.status_label.setText(translate("dialog.scan_failed", str(e)))
        finally:
            self.refresh_btn.setEnabled(True)
            self.scan_task = None

    @asyncSlot()
    async def on_refresh_clicked(self):
        """处理刷新按钮点击事件"""
        try:
            if self.scan_task and not self.scan_task.done():
                self.scan_task.cancel()
            
            loop = asyncio.get_event_loop()
            self.scan_task = loop.create_task(self._do_scan())
            
        except Exception as e:
            logging.error(f"刷新扫描失败: {str(e)}")
            self.status_label.setText(translate("dialog.scan_failed", str(e)))

    def apply_theme(self):
        """应用深色主题"""
        self.setStyleSheet(get_style(accent_color=self.accent_color))
            
class DeviceSignals(QObject):
    """设备信号处理类
    
    管理程序中的所有自定义信号。
    使用Qt的信号机制实现组件间的通信。
    
    信号列表：
        status_update (str, str): 更新状态信息，参数为(通道, 状态值)
        log_message (str): 发送日志消息
        device_selected (str): 设备被选中，参数为设备地址
        device_id_updated (str): 设备ID更新，参数为新的设备ID
        connection_changed (bool): 连接状态改变，参数为是否连接
        language_changed (str): 语言改变，参数为新的语言名称
    """
    
    # 状态更新信号
    status_update = Signal(str, str)
    # 日志消息信号
    log_message = Signal(str)
    # 设备选择信号
    device_selected = Signal(str)
    # 设备ID更新信号
    device_id_updated = Signal(str)
    # 连接状态改变信号
    connection_changed = Signal(bool)
    # 语言改变信号
    language_changed = Signal(str)
        
class LogWindow(QMainWindow):
    """日志窗口类
    
    提供一个独立的窗口用于显示和管理程序运行日志。
    主要功能：
    1. 实时显示程序运行日志
    2. 支持清除日志
    3. 适配深色/浅色主题
    4. 支持多语言
    
    属性:
        log_area (QTextEdit): 日志显示区域
        clear_btn (QPushButton): 清除日志按钮
        signals (DeviceSignals): 信号对象，用于发送日志消息
    """
    
    def __init__(self, parent=None):
        """初始化日志窗口
        
        Args:
            parent: 父窗口对象，通常是MainWindow实例
        """
        super().__init__(parent)
        self.setGeometry(100, 100, 600, 400)
        
        # 获取父窗口的信号对象和强调色
        self.signals = parent.signals if parent else DeviceSignals()
        self.accent_color = parent.accent_color if parent else DEFAULT_ACCENT_COLOR
        
        # 创建中心部件和布局
        central_widget = QWidget()
        layout = QVBoxLayout()
        
        # 创建日志文本区域
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(self.log_area)
        
        # 清除日志按钮
        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(self.clear_logs)
        layout.addWidget(self.clear_btn)
        
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)
        
        # 应用当前主题
        self.apply_theme()
        
        # 更新所有文本元素的翻译
        self.update_texts()

    def clear_logs(self):
        """清除日志区域的所有内容"""
        self.log_area.clear()
        self.signals.log_message.emit(translate("status_updates.logs_cleared"))

    def update_texts(self):
        """更新所有文本元素的翻译
        
        更新窗口标题和按钮文本的翻译。
        在语言切换时会被调用。
        """
        self.setWindowTitle(translate("log.title"))
        if hasattr(self, 'clear_btn'):
            self.clear_btn.setText(translate("log.clear"))
        
    def apply_theme(self):
        """应用深色主题"""
        style = get_style(accent_color=self.accent_color)
        self.setStyleSheet(style)
        
    def closeEvent(self, event):
        """处理窗口关闭事件
        
        当窗口被关闭时，通知父窗口更新状态。
        
        Args:
            event: 关闭事件对象
        """
        # 通知父窗口日志窗口已关闭
        if isinstance(self.parent(), MainWindow):
            self.parent().on_log_window_closed()
        event.accept()
        
    def append_log(self, message):
        """添加新的日志消息
        
        在日志区域添加一条新的日志消息，包含时间戳。
        
        Args:
            message: 要添加的日志消息
        """
        self.log_area.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        
    def toggle_log_window(self):
        """切换日志窗口的显示状态
        
        控制日志窗口的显示和隐藏，并更新相关按钮的文本。
        """
        if self.log_window is None:
            self.log_window = LogWindow(self)  # 确保在这里初始化日志窗口
        
        if self.log_window.isVisible():
            self.log_window.hide()
            self.log_window_btn.setText(translate("log.show"))
        else:
            self.log_window.show()
            self.log_window_btn.setText(translate("log.hide"))

    def on_log_window_closed(self):
        """处理日志窗口关闭事件
        
        当日志窗口被关闭时更新显示按钮的文本。
        """
        self.log_window_btn.setText(translate("log.show"))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.signals = DeviceSignals()
        self.ble_client = None
        self.ws_client = None
        self.wave_queues = {'A': deque(maxlen=100), 'B': deque(maxlen=100)}
        self.current_strength = {'A': 0, 'B': 0}
        self.max_strength = DEFAULT_MAX_STRENGTH.copy()
        self.selected_device = ""
        self.log_window = None
        self.accent_color = DEFAULT_ACCENT_COLOR
        self.background_image = DEFAULT_BACKGROUND_IMAGE
        
        logging.info("开始初始化主窗口...")
        
        # 加载可用语言
        logging.info("开始加载可用语言列表...")
        self.available_languages = load_available_languages()
        logging.info(f"可用语言列表: {self.available_languages}")
        
        # 确保至少有一种语言可用
        if not self.available_languages:
            logging.warning("没有找到语言包文件，使用默认中文")
            self.available_languages = {"zh_CN": "简体中文"}
        
        # 加载配置
        logging.info("开始加载配置...")
        self.load_config()
        
        # 加载语言包
        global CURRENT_LANG
        logging.info(f"尝试加载默认语言: {CURRENT_LANG}")
        if not load_language(CURRENT_LANG):
            logging.warning(f"加载默认语言 {CURRENT_LANG} 失败，尝试加载备选语言")
            if "zh_CN" in self.available_languages and load_language("zh_CN"):
                logging.info("成功加载中文语言包")
                CURRENT_LANG = "zh_CN"
            elif self.available_languages:
                first_lang = next(iter(self.available_languages.keys()))
                logging.info(f"尝试加载第一个可用语言: {first_lang}")
                if load_language(first_lang):
                    logging.info(f"成功加载语言: {first_lang}")
                    CURRENT_LANG = first_lang
                else:
                    logging.error("所有语言包加载都失败")
        
        logging.info("开始初始化UI...")
        self.init_ui()
        self.setup_connections()
        self.apply_theme()
        
        # 启动波形更新定时器
        self.update_timer = pg.QtCore.QTimer()
        self.update_timer.timeout.connect(self.update_plot)
        self.update_timer.start(50)  # 每50ms更新一次
        
        logging.info("主窗口初始化完成")

    def load_config(self):
        """加载配置文件
        
        从CONFIG_FILE指定的文件中加载配置。
        如果加载失败，使用默认值。
        """
        global SOCKET_URI, CURRENT_LANG
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    SOCKET_URI = config.get('socket_uri', "")
                    self.max_strength['A'] = config.get('max_strength_a', DEFAULT_MAX_STRENGTH['A'])
                    self.max_strength['B'] = config.get('max_strength_b', DEFAULT_MAX_STRENGTH['B'])
                    CURRENT_LANG = config.get('language', "zh_CN")
                    self.accent_color = config.get('accent_color', DEFAULT_ACCENT_COLOR)
                    self.background_image = config.get('background_image', DEFAULT_BACKGROUND_IMAGE)
                    logging.info("配置文件加载成功")
        except Exception as e:
            logging.error(f"加载配置文件失败: {str(e)}")
            # 使用默认值
            SOCKET_URI = ""
            self.max_strength = DEFAULT_MAX_STRENGTH.copy()
            CURRENT_LANG = "zh_CN"
            self.accent_color = DEFAULT_ACCENT_COLOR
            self.background_image = DEFAULT_BACKGROUND_IMAGE

    def save_config(self):
        """保存配置到文件
        
        将当前的配置保存到CONFIG_FILE指定的文件中。
        包括：服务器地址、最大强度设置、语言设置等。
        
        Returns:
            bool: 保存是否成功
        """
        global CURRENT_LANG
        
        # 确保配置文件目录存在
        config_dir = os.path.dirname(CONFIG_FILE)
        if not os.path.exists(config_dir):
            try:
                os.makedirs(config_dir)
                logging.info(f"创建配置文件目录: {config_dir}")
            except Exception as e:
                logging.error(f"创建配置文件目录失败: {str(e)}")
                return False
        
        config = {
            'socket_uri': SOCKET_URI,
            'max_strength_a': self.max_strength['A'],
            'max_strength_b': self.max_strength['B'],
            'language': CURRENT_LANG,
            'accent_color': self.accent_color,
            'background_image': self.background_image
        }
        
        try:
            # 使用JSON格式保存，更安全和可靠
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            logging.info("配置文件保存成功")
            return True
        except Exception as e:
            logging.error(f"保存配置文件失败: {str(e)}")
            return False

    def apply_theme(self):
        style = get_style(self.accent_color, self.background_image)
        self.setStyleSheet(style)
        
        # 更新日志窗口主题
        if self.log_window:
            self.log_window.apply_theme()
            
        # 更新主题切换按钮文本
        if hasattr(self, 'theme_btn'):
            self.theme_btn.setText(translate("theme.toggle"))

    def show_personalization_dialog(self):
        """显示个性化设置对话框"""
        dialog = PersonalizationDialog(self, self.accent_color, self.background_image)
        if dialog.exec() == QDialog.Accepted:
            settings = dialog.get_settings()
            self.accent_color = settings['accent_color']
            self.background_image = settings['background_image']
            self.apply_theme()
            self.save_config()
            self.signals.log_message.emit(translate("status_updates.personalization_updated"))

    def update_plot(self):
        # 更新波形显示
        if self.wave_queues['A']:
            self.curve_a.setData(list(self.wave_queues['A']))
        if self.wave_queues['B']:
            self.curve_b.setData(list(self.wave_queues['B']))

    def toggle_log_window(self):
        """切换日志窗口的显示状态"""
        if self.log_window is None:
            self.log_window = LogWindow(self)  # 确保在这里初始化日志窗口
        
        if self.log_window.isVisible():
            self.log_window.hide()
            self.log_window_btn.setText(translate("log.show"))
        else:
            self.log_window.show()
            self.log_window_btn.setText(translate("log.hide"))

    def on_log_window_closed(self):
        """当日志窗口被关闭时调用"""
        self.log_window_btn.setText(translate("log.show"))

    def log_output(self, message):
        if self.log_window:
            self.log_window.append_log(message)

    def setup_connections(self):
        self.scan_btn.clicked.connect(self.show_scanner)
        self.connect_btn.clicked.connect(self.on_connect_clicked)
        self.connect_server_btn.clicked.connect(self.on_connect_server_clicked)
        self.signals.device_selected.connect(self.update_device_address)
        self.signals.device_id_updated.connect(self.update_device_id)
        self.signals.connection_changed.connect(self.update_ui_state)
        self.signals.status_update.connect(self.update_status)
        self.signals.log_message.connect(self.log_output)
        self.save_btn.clicked.connect(self.update_max_strength)
        self.test_a_btn.clicked.connect(lambda: self.send_strength_command(1, 1, 10))
        self.test_b_btn.clicked.connect(lambda: self.send_strength_command(2, 1, 10))
        self.clear_a_btn.clicked.connect(lambda: self.clear_queue('A'))
        self.clear_b_btn.clicked.connect(lambda: self.clear_queue('B'))
        self.save_server_btn.clicked.connect(self.update_server_address)
        self.lang_combo.currentIndexChanged.connect(self.on_language_changed)
        
    @asyncSlot()
    async def show_scanner(self):
        try:
            # 检查蓝牙是否可用
            if not await check_bluetooth_available():
                QMessageBox.critical(self, 
                    translate("dialog.error"),
                    translate("dialog.bluetooth_not_available"),
                    QMessageBox.Ok)
                return
                
            # 创建扫描窗口
            scanner = DeviceScanner(self)
            scanner.setStyleSheet(self.styleSheet())  # 应用相同的主题
            scanner.device_list.itemDoubleClicked.connect(lambda: self.select_device(scanner))
            
            # 显示窗口
            scanner.show()
            
            # 等待窗口关闭
            await asyncio.get_event_loop().run_in_executor(None, scanner.exec)
            
        except Exception as e:
            logging.error(f"显示扫描窗口时发生错误: {str(e)}")
            QMessageBox.critical(self,
                translate("dialog.error"),
                translate("dialog.scan_window_error", str(e)),
                QMessageBox.Ok)

    def select_device(self, scanner):
        selected = scanner.device_list.currentItem().text()
        address = selected.split("|")[-1].strip()
        self.signals.device_selected.emit(address)
        scanner.close()
        
    def update_server_address(self):
        global SOCKET_URI
        new_uri = self.server_input.text().strip()
        
        # 验证URL格式
        if not is_valid_websocket_url(new_uri):
            QMessageBox.warning(self,
                translate("dialog.error"),
                translate("dialog.invalid_url"),
                QMessageBox.Ok)
            return
        
        SOCKET_URI = new_uri
        if self.save_config():
            self.signals.log_message.emit(translate("status_updates.server_updated", SOCKET_URI))
        else:
            self.signals.log_message.emit(translate("status_updates.server_update_failed", SOCKET_URI))
            QMessageBox.warning(self,
                translate("dialog.error"),
                translate("dialog.save_config_failed"),
                QMessageBox.Ok)
        
    def update_device_address(self, address):
        global BLE_DEVICE_ADDRESS
        BLE_DEVICE_ADDRESS = address
        self.selected_device = address
        self.device_label.setText(translate("device.status", address))
        self.connect_btn.setEnabled(True)
        self.signals.log_message.emit(translate("status_updates.device_selected", address))
        
    def update_device_id(self, device_id):
        global DEVICE_ID
        DEVICE_ID = device_id
        self.signals.log_message.emit(translate("status_updates.get_device_id_success", device_id))
        
    @asyncSlot()
    async def on_connect_clicked(self):
        if not self.selected_device:
            self.signals.log_message.emit(translate("status_updates.please_select_device"))
            return
            
        try:
            self.ble_client = BleakClient(BLE_DEVICE_ADDRESS)
            await self.ble_client.connect()
            self.signals.log_message.emit(translate("status_updates.bluetooth_connected"))
            await self.get_device_id()
            asyncio.create_task(self.process_wave_queues())
            asyncio.create_task(self.monitor_connection())
            self.signals.connection_changed.emit(True)
            self.connect_server_btn.setEnabled(True)  # 启用服务器连接按钮
        except Exception as e:
            self.signals.log_message.emit(translate("status_updates.connection_failed", str(e)))
            self.signals.connection_changed.emit(False)
            self.connect_server_btn.setEnabled(False)

    @asyncSlot()
    async def on_connect_server_clicked(self):
        if not self.ble_client or not self.ble_client.is_connected:
            self.signals.log_message.emit("请先确保蓝牙设备已连接")
            return
            
        if not SOCKET_URI:
            self.signals.log_message.emit(translate("status_updates.server_address_empty"))
            return
            
        try:
            asyncio.create_task(self.listen_websocket())
            self.connect_server_btn.setEnabled(False)
            self.signals.log_message.emit("正在连接服务器...")
        except Exception as e:
            self.signals.log_message.emit(f"连接服务器失败: {str(e)}")
            self.connect_server_btn.setEnabled(True)

    async def read_battery(self):
        try:
            value = await self.ble_client.read_gatt_char(BLE_CHAR_BATTERY)
            battery_level = int.from_bytes(value, byteorder='little')
            self.battery_label.setText(translate("status.battery", battery_level))
        except Exception as e:
            self.signals.log_message.emit(translate("status_updates.battery_read_failed", str(e)))
            
    async def monitor_connection(self):
        while self.ble_client and self.ble_client.is_connected:
            rssi = self.ble_client.rssi if hasattr(self.ble_client, 'rssi') else None
            if rssi:
                self.rssi_label.setText(translate("status.signal_strength", rssi))
            else:
                self.rssi_label.setText(translate("status.signal_unknown"))
            await asyncio.sleep(5)  # 每5秒更新一次
            await self.read_battery()

    async def get_device_id(self):
        try:
            value = await self.ble_client.read_gatt_char(BLE_CHAR_DEVICE_ID)
            device_id = value.hex().upper()
            global DEVICE_ID
            DEVICE_ID = device_id
            self.signals.device_id_updated.emit(device_id)
            self.signals.log_message.emit(translate("status_updates.get_device_id_success", device_id))
        except Exception as e:
            self.signals.log_message.emit(translate("status_updates.get_device_id_failed", str(e)))

    def update_ui_state(self, connected):
        """更新UI状态
        
        根据设备连接状态更新各个UI元素的启用/禁用状态
        
        Args:
            connected (bool): 设备是否已连接
        """
        # 更新连接相关按钮状态
        self.connect_btn.setEnabled(not connected)
        self.scan_btn.setEnabled(not connected)
        self.connect_server_btn.setEnabled(connected)
        
        # 更新手动控制按钮状态
        self.test_a_btn.setEnabled(connected)
        self.test_b_btn.setEnabled(connected)
        self.clear_a_btn.setEnabled(connected)
        self.clear_b_btn.setEnabled(connected)
        
        # 更新状态显示
        status = translate("device.connected" if connected else "device.disconnected")
        self.device_label.setText(translate("device.status", status))
        
        # 更新实时状态
        self.update_status('A', self.current_strength['A'])
        self.update_status('B', self.current_strength['B'])
        
        # 更新电池和信号强度显示
        if hasattr(self, 'battery_label'):
            self.battery_label.setText(translate("status.battery", "--"))
        if hasattr(self, 'rssi_label'):
            self.rssi_label.setText(translate("status.signal_unknown"))

    def update_status(self, channel, value):
        try:
            if channel == 'A':
                text = translate("status.channel_a", int(value), self.max_strength[channel])
                self.a_status.setText(text)
            else:
                text = translate("status.channel_b", int(value), self.max_strength[channel])
                self.b_status.setText(text)
        except ValueError:
            self.signals.log_message.emit(translate("status_updates.invalid_status_value"))

    def clear_queue(self, channel):
        self.wave_queues[channel].clear()
        self.signals.log_message.emit(translate("status_updates.queue_cleared", channel))
        
    async def send_ble_command(self, char_uuid, data):
        if self.ble_client and self.ble_client.is_connected:
            try:
                await self.ble_client.write_gatt_char(char_uuid, data)
                self.signals.log_message.emit(translate("status_updates.command_send_success", char_uuid[-4:]))
            except Exception as e:
                self.signals.log_message.emit(translate("status_updates.command_send_failed", str(e)))

    def v3_freq_to_v2(self, freq_input):
        """将V3协议的频率值转换为V2协议的参数
        
        根据不同的频率范围使用不同的转换公式。
        
        Args:
            freq_input (int): V3协议的频率值
            
        Returns:
            tuple: (x, y) V2协议的参数对
        """
        if 10 <= freq_input <= 100:
            x = max(1, int(freq_input**0.5 * 0.8))
            y = 1000 // freq_input - x
        elif 101 <= freq_input <= 600:
            scaled = (freq_input - 100)/5 + 100
            x = int(scaled**0.5 * 1.2)
            y = max(1, (1000//freq_input)-x)
        elif 601 <= freq_input <= 1000:
            x = int((freq_input**0.5)*0.5)
            y = max(1, (1000//freq_input)-x)
        else: x,y = 1,9
        return max(1,min(31,x)), max(1,min(1023,y))

    def v3_intensity_to_v2_z(self, intensity):
        """将V3协议的强度值转换为V2协议的z参数
        
        Args:
            intensity (int): V3协议的强度值(0-100)
            
        Returns:
            int: V2协议的z参数值(1-31)
        """
        return min(31, int(20 + (15 * (intensity/100))))

    def encode_pwm_ab2(self, a, b):
        """编码PWM AB2通道的数据
        
        将A、B通道的强度值编码为V2协议的字节数据。
        
        Args:
            a (int): A通道强度值(0-200)
            b (int): B通道强度值(0-200)
            
        Returns:
            bytes: 编码后的3字节数据
        """
        a_val = min(int(a*2047/200),2047)
        b_val = min(int(b*2047/200),2047)
        return bytes([(a_val>>3)&0xFF, ((a_val&0x07)<<5)|((b_val>>6)&0x1F), (b_val&0x3F)<<2])

    def encode_pwm_channel(self, x, y, z):
        """编码单个PWM通道的数据
        
        将x、y、z参数编码为V2协议的字节数据。
        
        Args:
            x (int): 频率参数x(1-31)
            y (int): 频率参数y(1-1023)
            z (int): 强度参数z(1-31)
            
        Returns:
            bytes: 编码后的3字节数据
        """
        return struct.pack('<I', (z&0x1F)<<19 | (y&0x3FF)<<5 | (x&0x1F))[:3]

    async def process_wave_queues(self):
        while True:
            for ch in ['A','B']:
                if len(self.wave_queues[ch]) >=4:
                    params = [self.wave_queues[ch].popleft() for _ in range(4)]
                    avg_x = sum(p[0] for p in params)//4
                    avg_y = sum(p[1] for p in params)//4
                    avg_z = sum(p[2] for p in params)//4
                    data = self.encode_pwm_channel(avg_x, avg_y, avg_z)
                    char = BLE_CHAR_PWM_A34 if ch == 'A' else BLE_CHAR_PWM_B34
                    await self.send_ble_command(char, data)
            await asyncio.sleep(0.025)

    async def send_websocket_message(self, message):
        """发送消息到WebSocket服务器"""
        try:
            if not self.ws_client:
                self.signals.log_message.emit("WebSocket未连接")
                return
            
            await self.ws_client.send(json.dumps(message))
            self.signals.log_message.emit("消息已发送到服务器")
        except Exception as e:
            self.signals.log_message.emit(f"发送消息到服务器失败: {str(e)}")
            self.ws_client = None  # 连接可能已断开，重置连接

    async def listen_websocket(self):
        try:
            if not SOCKET_URI:
                self.signals.log_message.emit(translate("status_updates.server_address_empty"))
                return
            
            async with websockets.connect(SOCKET_URI) as ws:
                self.ws_client = ws  # 保存WebSocket连接
                await ws.send(json.dumps({
                    "type": "bind",
                    "clientId": DEVICE_ID,
                    "targetId": "",
                    "message": "DGLAB"
                }))
                while True:
                    try:
                        message = await ws.recv()
                        self.signals.log_message.emit(translate("status_updates.received_command", message[:50]))
                        await self.handle_socket_message(message)
                    except websockets.ConnectionClosed:
                        self.signals.log_message.emit("WebSocket连接已关闭")
                        break
                    except Exception as e:
                        self.signals.log_message.emit(f"处理WebSocket消息时出错: {str(e)}")
                        break
        except Exception as e:
            self.signals.log_message.emit(translate("status_updates.network_error", str(e)))
        finally:
            self.ws_client = None  # 清除连接

    async def handle_socket_message(self, message):
        try:
            msg = json.loads(message)
            if msg["type"] != "msg": return
            
            cmd = msg["message"]
            if cmd.startswith("strength-"):
                parts = cmd[9:].split('+')
                await self.handle_strength_change(int(parts[0]), int(parts[1]), int(parts[2]))
            elif cmd.startswith("pulse-"):
                ch_part, wave_data = cmd[6:].split(':')
                channel = ch_part.upper()
                hex_waves = json.loads(wave_data)
                for hex_str in hex_waves[:100]:
                    freq = int(hex_str[:2],16)
                    intensity = int(hex_str[2:4],16)
                    x,y = self.v3_freq_to_v2(freq)
                    z = self.v3_intensity_to_v2_z(intensity)
                    self.wave_queues[channel].append((x,y,z))
                    # 更新波形显示
                    self.wave_queues[channel].append(intensity)
            elif cmd.startswith("clear-"):
                channel = 'A' if cmd[6:] == '1' else 'B'
                self.wave_queues[channel].clear()
                self.signals.log_message.emit(translate("status_updates.queue_cleared", channel))
                
        except Exception as e:
            self.signals.log_message.emit(translate("status_updates.message_process_error", str(e)))

    def update_max_strength(self):
        try:
            # 获取输入值
            a_value = int(self.a_max_input.text())
            b_value = int(self.b_max_input.text())
            
            # 验证范围
            if a_value < 0 or a_value > 200 or b_value < 0 or b_value > 200:
                QMessageBox.warning(self,
                    translate("dialog.error"),
                    translate("status_updates.strength_limit_range_error"),
                    QMessageBox.Ok)
                # 恢复原值
                self.a_max_input.setText(str(self.max_strength['A']))
                self.b_max_input.setText(str(self.max_strength['B']))
                return
            
            # 更新值
            self.max_strength['A'] = a_value
            self.max_strength['B'] = b_value
            
            # 更新波形显示的Y轴范围
            self.check_plot_range()
            
            if self.save_config():
                self.signals.log_message.emit(translate("status_updates.strength_limit_updated", 
                    self.max_strength['A'], self.max_strength['B']))
            else:
                self.signals.log_message.emit(translate("status_updates.strength_limit_update_failed", 
                    self.max_strength['A'], self.max_strength['B']))
                
            self.update_status('A', self.current_strength['A'])
            self.update_status('B', self.current_strength['B'])
        except ValueError:
            QMessageBox.warning(self,
                translate("dialog.error"),
                translate("status_updates.invalid_number"),
                QMessageBox.Ok)
            # 恢复原值
            self.a_max_input.setText(str(self.max_strength['A']))
            self.b_max_input.setText(str(self.max_strength['B']))

    def send_strength_command(self, channel, mode, value):
        asyncio.create_task(self.handle_strength_change(channel, mode, value))

    async def handle_strength_change(self, channel_num, mode, value):
        ch = 'A' if channel_num == 1 else 'B'
        try:
            current = self.current_strength[ch]
            if mode == 0: new = current - value
            elif mode == 1: new = current + value
            elif mode == 2: new = value
            else: return
            
            if new > self.max_strength[ch]:
                self.signals.log_message.emit(translate("status_updates.channel_over_limit", ch, self.max_strength[ch]))
                return
                
            new = max(0, min(new, self.max_strength[ch]))
            old_value = self.current_strength[ch]  # 保存旧值
            self.current_strength[ch] = new
            data = self.encode_pwm_ab2(self.current_strength['A'], self.current_strength['B'])
            await self.send_ble_command(BLE_CHAR_PWM_AB2, data)
            self.signals.status_update.emit(ch, str(new))
            
            # 更新波形显示
            self.wave_queues[ch].append(new)
            
            # 只有当值真正改变时才发送到服务器
            if new != old_value:
                message = {
                    "type": "msg",
                    "clientId": DEVICE_ID,
                    "targetId": "",
                    "message": f"strength-{channel_num}+2+{new}"  # 使用mode 2表示直接设置强度值
                }
                await self.send_websocket_message(message)
            
        except Exception as e:
            self.signals.log_message.emit(translate("status_updates.strength_adjust_failed", str(e)))

    def on_language_changed(self, index):
        """语言选择改变时的处理函数"""
        logging.debug(f"语言选择改变: index={index}")
        try:
            lang_code = self.lang_combo.itemData(index)
            logging.debug(f"选择的语言代码: {lang_code}")
            if lang_code:
                self.change_language(lang_code)
        except Exception as e:
            logging.error(f"处理语言改变事件时发生错误: {str(e)}")

    def init_ui(self):
        """初始化用户界面
        
        创建和设置所有UI元素，包括：
        1. 主窗口设置
        2. 布局管理
        3. 控件创建和配置
        4. 波形显示初始化
        """
        self.setWindowTitle(translate("app_title"))
        self.setGeometry(100, 100, 800, 700)
        
        # 设置字体
        font = QFont("Microsoft YaHei", 9)
        self.setFont(font)
        
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # 顶部标题和主题切换
        top_layout = QHBoxLayout()
        self.title_label = QLabel(translate("main_title"))
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.personalization_btn = QPushButton(translate("personalization.button"))
        self.personalization_btn.clicked.connect(self.show_personalization_dialog)
        self.log_window_btn = QPushButton(translate("log.show"))
        self.log_window_btn.clicked.connect(self.toggle_log_window)
        top_layout.addWidget(self.title_label)
        top_layout.addStretch()
        top_layout.addWidget(self.log_window_btn)
        top_layout.addWidget(self.personalization_btn)
        main_layout.addLayout(top_layout)
        
        # 添加分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(line)
        
        # 语言选择
        self.lang_group = QGroupBox(translate("language.setting"))
        lang_layout = QHBoxLayout()
        self.lang_combo = QComboBox()
        
        # 填充语言下拉列表
        for lang_code, lang_name in self.available_languages.items():
            self.lang_combo.addItem(lang_name, lang_code)
            if lang_code == CURRENT_LANG:
                self.lang_combo.setCurrentText(lang_name)
        
        self.lang_combo.currentIndexChanged.connect(self.on_language_changed)
        lang_layout.addWidget(self.lang_combo)
        self.lang_group.setLayout(lang_layout)
        main_layout.addWidget(self.lang_group)
        
        # 设备管理组
        self.device_group = QGroupBox(translate("device.management"))
        device_layout = QHBoxLayout()
        self.scan_btn = QPushButton(translate("device.scan"))
        self.connect_btn = QPushButton(translate("device.connect"))
        self.connect_btn.setEnabled(False)
        self.device_label = QLabel(translate("device.status"))
        device_layout.addWidget(self.scan_btn)
        device_layout.addWidget(self.connect_btn)
        device_layout.addWidget(self.device_label)
        self.device_group.setLayout(device_layout)
        main_layout.addWidget(self.device_group)
        
        # 服务器配置组
        self.server_group = QGroupBox(translate("server.config"))
        server_layout = QHBoxLayout()
        self.server_address_label = QLabel(translate("server.address"))
        self.server_input = QLineEdit()
        self.server_input.setText(SOCKET_URI)
        self.save_server_btn = QPushButton(translate("server.save"))
        self.connect_server_btn = QPushButton(translate("server.connect"))
        self.connect_server_btn.setEnabled(False)  # 初始禁用
        server_layout.addWidget(self.server_address_label)
        server_layout.addWidget(self.server_input)
        server_layout.addWidget(self.save_server_btn)
        server_layout.addWidget(self.connect_server_btn)
        self.server_group.setLayout(server_layout)
        main_layout.addWidget(self.server_group)
        
        # 配置区域
        self.config_group = QGroupBox(translate("strength.config"))
        config_layout = QHBoxLayout()
        self.channel_a_limit_label = QLabel(translate("strength.channel_a_limit"))
        self.channel_b_limit_label = QLabel(translate("strength.channel_b_limit"))
        self.a_max_input = QLineEdit(str(self.max_strength['A']))
        self.b_max_input = QLineEdit(str(self.max_strength['B']))
        
        # 设置输入验证
        validator = QIntValidator(0, 200)
        self.a_max_input.setValidator(validator)
        self.b_max_input.setValidator(validator)
        
        self.save_btn = QPushButton(translate("strength.save"))
        config_layout.addWidget(self.channel_a_limit_label)
        config_layout.addWidget(self.a_max_input)
        config_layout.addWidget(self.channel_b_limit_label)
        config_layout.addWidget(self.b_max_input)
        config_layout.addWidget(self.save_btn)
        self.config_group.setLayout(config_layout)
        main_layout.addWidget(self.config_group)
        
        # 状态显示
        self.status_group = QGroupBox(translate("status.realtime"))
        status_layout = QHBoxLayout()
        self.a_status = QLabel(translate("status.channel_a").format(0, self.max_strength['A']))
        self.b_status = QLabel(translate("status.channel_b").format(0, self.max_strength['B']))
        self.battery_label = QLabel(translate("status.battery").format("--"))
        self.rssi_label = QLabel(translate("status.signal_unknown"))
        status_layout.addWidget(self.a_status)
        status_layout.addWidget(self.b_status)
        status_layout.addWidget(self.battery_label)
        status_layout.addWidget(self.rssi_label)
        self.status_group.setLayout(status_layout)
        main_layout.addWidget(self.status_group)
        
        # 控制按钮
        self.control_group = QGroupBox(translate("control.manual"))
        control_layout = QHBoxLayout()
        self.test_a_btn = QPushButton(translate("control.test_a"))
        self.test_b_btn = QPushButton(translate("control.test_b"))
        self.clear_a_btn = QPushButton(translate("control.clear_a"))
        self.clear_b_btn = QPushButton(translate("control.clear_b"))
        
        # 初始禁用所有控制按钮
        self.test_a_btn.setEnabled(False)
        self.test_b_btn.setEnabled(False)
        self.clear_a_btn.setEnabled(False)
        self.clear_b_btn.setEnabled(False)
        
        control_layout.addWidget(self.test_a_btn)
        control_layout.addWidget(self.test_b_btn)
        control_layout.addWidget(self.clear_a_btn)
        control_layout.addWidget(self.clear_b_btn)
        self.control_group.setLayout(control_layout)
        main_layout.addWidget(self.control_group)
        
        # 波形显示区域
        wave_layout = QHBoxLayout()
        
        # A通道波形显示
        self.plot_widget_a = pg.PlotWidget()
        self.plot_widget_a.setBackground(None)  # 设置背景透明
        self.plot_widget_a.setTitle(translate("status.wave_title_a"))
        self.plot_widget_a.setLabel('left', translate("status.wave_y_label"))
        self.plot_widget_a.setLabel('bottom', translate("status.wave_x_label"))
        self.plot_widget_a.showGrid(x=True, y=True, alpha=0.3)  # 设置网格透明度
        self.plot_widget_a.setMouseEnabled(x=False, y=False)
        self.plot_widget_a.setMenuEnabled(False)
        view_box_a = self.plot_widget_a.getViewBox()
        view_box_a.setMouseMode(pg.ViewBox.RectMode)
        view_box_a.setMouseEnabled(x=False, y=False)
        view_box_a.enableAutoRange(enable=False)
        
        # 设置轴线颜色和透明度
        axis_pen = pg.mkPen(color='#ffffff', width=1)
        axis_text_pen = pg.mkPen(color='#ffffff')
        self.plot_widget_a.getAxis('bottom').setPen(axis_pen)
        self.plot_widget_a.getAxis('left').setPen(axis_pen)
        self.plot_widget_a.getAxis('bottom').setTextPen(axis_text_pen)
        self.plot_widget_a.getAxis('left').setTextPen(axis_text_pen)
        
        # B通道波形显示
        self.plot_widget_b = pg.PlotWidget()
        self.plot_widget_b.setBackground(None)  # 设置背景透明
        self.plot_widget_b.setTitle(translate("status.wave_title_b"))
        self.plot_widget_b.setLabel('left', translate("status.wave_y_label"))
        self.plot_widget_b.setLabel('bottom', translate("status.wave_x_label"))
        self.plot_widget_b.showGrid(x=True, y=True, alpha=0.3)  # 设置网格透明度
        self.plot_widget_b.setMouseEnabled(x=False, y=False)
        self.plot_widget_b.setMenuEnabled(False)
        view_box_b = self.plot_widget_b.getViewBox()
        view_box_b.setMouseMode(pg.ViewBox.RectMode)
        view_box_b.setMouseEnabled(x=False, y=False)
        view_box_b.enableAutoRange(enable=False)
        
        # 设置轴线颜色和透明度
        self.plot_widget_b.getAxis('bottom').setPen(axis_pen)
        self.plot_widget_b.getAxis('left').setPen(axis_pen)
        self.plot_widget_b.getAxis('bottom').setTextPen(axis_text_pen)
        self.plot_widget_b.getAxis('left').setTextPen(axis_text_pen)
        
        # 保存初始显示范围
        self.expected_y_range = (0, max(self.max_strength['A'], self.max_strength['B']))
        self.expected_x_range = (-100, 0)  # 显示最近100个数据点
        self.plot_widget_a.setYRange(*self.expected_y_range)
        self.plot_widget_a.setXRange(*self.expected_x_range)
        self.plot_widget_b.setYRange(*self.expected_y_range)
        self.plot_widget_b.setXRange(*self.expected_x_range)
        
        # 创建两条曲线
        self.curve_a = self.plot_widget_a.plot(pen=pg.mkPen(color=(255, 0, 0, 200), width=2), name='A通道')  # 红色，半透明
        self.curve_b = self.plot_widget_b.plot(pen=pg.mkPen(color=(0, 0, 255, 200), width=2), name='B通道')  # 蓝色，半透明
        
        # 添加到布局
        wave_layout.addWidget(self.plot_widget_a)
        wave_layout.addWidget(self.plot_widget_b)
        main_layout.addLayout(wave_layout, 1)  # 1表示拉伸因子
        
        # 创建范围监控定时器
        self.range_monitor = pg.QtCore.QTimer()
        self.range_monitor.timeout.connect(self.check_plot_range)
        self.range_monitor.start(50)  # 每50ms检查一次
        
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def change_language(self, lang_code):
        """切换界面语言
        
        Args:
            lang_code: 目标语言代码
        """
        logging.debug(f"开始切换语言到: {lang_code}")
        global CURRENT_LANG
        if load_language(lang_code):
            logging.debug("语言包加载成功")
            CURRENT_LANG = lang_code
            self.update_ui_texts()
            # 更新日志窗口的文本
            if self.log_window:
                self.log_window.update_texts()
            self.save_config()
            logging.debug("UI文本更新完成，配置已保存")
            self.signals.language_changed.emit(translate("language_name"))
        else:
            logging.error(f"切换语言失败: {lang_code}")
            
    def update_ui_texts(self):
        """更新界面上的所有文本标签，以反映当前选择的语言
        
        此方法在语言改变时被调用，用于更新所有UI元素的文本内容
        """
        try:
            # 更新窗口标题
            self.setWindowTitle(translate("app_title"))
            self.title_label.setText(translate("main_title"))
            
            # 更新按钮文本
            self.personalization_btn.setText(translate("personalization.button"))
            self.log_window_btn.setText(translate("log.show"))
            
            # 更新分组框标题
            self.lang_group.setTitle(translate("language.setting"))
            self.device_group.setTitle(translate("device.management"))
            self.server_group.setTitle(translate("server.config"))
            self.config_group.setTitle(translate("strength.config"))
            self.status_group.setTitle(translate("status.realtime"))
            self.control_group.setTitle(translate("control.manual"))
            
            # 更新设备管理组件
            self.scan_btn.setText(translate("device.scan"))
            self.connect_btn.setText(translate("device.connect"))
            self.device_label.setText(translate("device.status"))
            
            # 更新服务器配置组件
            self.server_address_label.setText(translate("server.address"))
            self.save_server_btn.setText(translate("server.save"))
            self.connect_server_btn.setText(translate("server.connect"))
            
            # 更新强度配置组件
            self.channel_a_limit_label.setText(translate("strength.channel_a_limit"))
            self.channel_b_limit_label.setText(translate("strength.channel_b_limit"))
            self.save_btn.setText(translate("strength.save"))
            
            # 更新状态显示
            self.a_status.setText(translate("status.channel_a").format(0, self.max_strength['A']))
            self.b_status.setText(translate("status.channel_b").format(0, self.max_strength['B']))
            self.battery_label.setText(translate("status.battery").format("--"))
            self.rssi_label.setText(translate("status.signal_unknown"))
            
            # 更新控制按钮
            self.test_a_btn.setText(translate("control.test_a"))
            self.test_b_btn.setText(translate("control.test_b"))
            self.clear_a_btn.setText(translate("control.clear_a"))
            self.clear_b_btn.setText(translate("control.clear_b"))
            
            # 更新波形图标题和标签
            self.plot_widget_a.setTitle(translate("status.wave_title_a"))
            self.plot_widget_a.setLabel('left', translate("status.wave_y_label"))
            self.plot_widget_a.setLabel('bottom', translate("status.wave_x_label"))
            
            self.plot_widget_b.setTitle(translate("status.wave_title_b"))
            self.plot_widget_b.setLabel('left', translate("status.wave_y_label"))
            self.plot_widget_b.setLabel('bottom', translate("status.wave_x_label"))
            
        except Exception as e:
            logging.error(f"更新UI文本时发生错误: {str(e)}")
            # 在这里可以添加用户提示或其他错误处理逻辑

    def check_plot_range(self):
        """检查并维护波形图的显示范围
        
        确保波形图的显示范围保持在预期的范围内，包括：
        1. Y轴范围：从0到当前最大强度值
        2. X轴范围：显示最近100个数据点
        """
        try:
            # 更新Y轴范围
            current_max = max(self.max_strength['A'], self.max_strength['B'])
            if self.expected_y_range[1] != current_max:
                self.expected_y_range = (0, current_max)
                self.plot_widget_a.setYRange(*self.expected_y_range)
                self.plot_widget_b.setYRange(*self.expected_y_range)
            
            # 检查并重置当前范围
            for plot_widget in [self.plot_widget_a, self.plot_widget_b]:
                current_y_range = plot_widget.getViewBox().viewRange()[1]
                current_x_range = plot_widget.getViewBox().viewRange()[0]
                
                # 如果当前范围与预期范围不匹配，重置为预期范围
                if (current_y_range != self.expected_y_range or 
                    current_x_range != self.expected_x_range):
                    plot_widget.setYRange(*self.expected_y_range)
                    plot_widget.setXRange(*self.expected_x_range)
                    
        except Exception as e:
            logging.error(f"检查波形范围时发生错误: {str(e)}")

class PersonalizationDialog(QDialog):
    """个性化设置对话框
    
    提供界面个性化设置功能，包括：
    1. 强调色选择（使用颜色选择器）
    2. 背景图片设置
    3. 实时预览效果
    """
    
    def __init__(self, parent=None, accent_color=None, background_image=None):
        super().__init__(parent)
        self.accent_color = accent_color or "#007bff"  # 默认蓝色
        self.background_image = background_image or ""
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle(translate("personalization.title"))
        self.setFixedSize(400, 300)
        
        layout = QVBoxLayout()
        
        # 强调色设置组
        color_group = QGroupBox(translate("personalization.accent_color"))
        color_layout = QHBoxLayout()
        
        # 颜色显示标签
        self.color_preview = QLabel()
        self.color_preview.setFixedSize(50, 25)
        self.update_color_preview()
        
        # RGB输入框
        rgb_layout = QHBoxLayout()
        self.r_input = QLineEdit()
        self.g_input = QLineEdit()
        self.b_input = QLineEdit()
        for input_box in [self.r_input, self.g_input, self.b_input]:
            input_box.setFixedWidth(40)
            input_box.setValidator(QIntValidator(0, 255))
            input_box.textChanged.connect(self.on_rgb_changed)
            rgb_layout.addWidget(input_box)
        
        # 设置当前RGB值
        color = QColor(self.accent_color)
        self.r_input.setText(str(color.red()))
        self.g_input.setText(str(color.green()))
        self.b_input.setText(str(color.blue()))
        
        # 颜色选择按钮
        self.color_btn = QPushButton(translate("personalization.choose_color"))
        self.color_btn.clicked.connect(self.choose_color)
        
        color_layout.addWidget(self.color_preview)
        color_layout.addLayout(rgb_layout)
        color_layout.addWidget(self.color_btn)
        color_group.setLayout(color_layout)
        
        # 背景图片设置组
        bg_group = QGroupBox(translate("personalization.background"))
        bg_layout = QHBoxLayout()
        
        self.bg_path = QLineEdit()
        self.bg_path.setText(self.background_image)
        self.bg_path.setReadOnly(True)
        
        self.bg_btn = QPushButton(translate("personalization.choose_image"))
        self.bg_btn.clicked.connect(self.choose_background)
        
        bg_layout.addWidget(self.bg_path)
        bg_layout.addWidget(self.bg_btn)
        bg_group.setLayout(bg_layout)
        
        # 确定和取消按钮
        button_layout = QHBoxLayout()
        self.ok_btn = QPushButton(translate("dialog.ok"))
        self.cancel_btn = QPushButton(translate("dialog.cancel"))
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addWidget(color_group)
        layout.addWidget(bg_group)
        layout.addStretch()
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
    def update_color_preview(self):
        """更新颜色预览"""
        self.color_preview.setStyleSheet(
            f"background-color: {self.accent_color}; border: 1px solid #cccccc;"
        )
        
    def on_rgb_changed(self):
        """RGB值改变时更新颜色"""
        try:
            r = int(self.r_input.text() or 0)
            g = int(self.g_input.text() or 0)
            b = int(self.b_input.text() or 0)
            self.accent_color = f"#{r:02x}{g:02x}{b:02x}"
            self.update_color_preview()
        except ValueError:
            pass
            
    def choose_color(self):
        """打开颜色选择对话框"""
        color = QColorDialog.getColor(QColor(self.accent_color), self)
        if color.isValid():
            self.accent_color = color.name()
            self.r_input.setText(str(color.red()))
            self.g_input.setText(str(color.green()))
            self.b_input.setText(str(color.blue()))
            self.update_color_preview()
            
    def choose_background(self):
        """选择背景图片"""
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            translate("personalization.choose_image"),
            "",
            "Images (*.png *.bmp *.jpg *.jpeg)"
        )
        if file_name:
            self.background_image = file_name
            self.bg_path.setText(file_name)
            
    def get_settings(self):
        """获取设置值"""
        return {
            'accent_color': self.accent_color,
            'background_image': self.background_image
        }

if __name__ == "__main__":
    # 设置日志格式
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    logging.info("程序启动")
    
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # 检查并创建语言包目录
    if not os.path.exists(LANG_PATH):
        try:
            os.makedirs(LANG_PATH)
            logging.info(f"成功创建语言包目录: {LANG_PATH}")
        except Exception as e:
            logging.error(f"创建语言包目录失败: {str(e)}")
    else:
        logging.info(f"语言包目录已存在: {LANG_PATH}")
    
    window = MainWindow()
    window.show()
    
    with loop:
        loop.run_forever()
