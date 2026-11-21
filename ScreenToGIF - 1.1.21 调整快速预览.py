#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Screen to GIF - 屏幕区域录制转GIF工具
增强版：支持录制后播放和编辑功能 + 文件大小控制 + 优化布局 + GIF导入编辑
版本: 1.1.21 - 优化快速预览区域拉伸行为
"""

import sys
import os
import json
import time
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from threading import Thread, Event
from dataclasses import dataclass, asdict
from typing import Optional, Tuple, List
import traceback

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import (
    Qt, QRect, QPoint, QSize, Signal, QTimer, QThread, 
    QRectF, QEasingCurve, QPropertyAnimation, QUrl, QMimeData
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QIcon, 
    QFont, QPalette, QLinearGradient, QCursor, QScreen,
    QFontMetrics, QAction, QActionGroup, QImage, QDesktopServices,
    QClipboard, QKeySequence, QTextCursor
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSpinBox, QDoubleSpinBox, QCheckBox,
    QGroupBox, QSlider, QFileDialog, QMessageBox, QFrame,
    QProgressBar, QSizePolicy, QGridLayout, QScrollArea,
    QTabWidget, QSplitter, QLineEdit, QComboBox, QDialog,
    QTextEdit, QDialogButtonBox, QListWidget, QListWidgetItem,
    QToolBar, QStatusBar, QMenu, QMenuBar, QRadioButton, QButtonGroup,
    QFormLayout, QToolBox, QInputDialog, QWidgetAction, QPlainTextEdit,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QAbstractItemView
)

# ==================== 项目信息元数据 ====================
class ProjectInfo:
    """项目信息元数据（集中管理所有项目相关信息）"""
    VERSION = "1.1.21"
    BUILD_DATE = "2026-03-11"
    AUTHOR = "杜玛"
    LICENSE = "GNU Affero General Public License v3.0"
    COPYRIGHT = "© 永久 杜玛"
    URL = "https://github.com/duma520"
    MAINTAINER_EMAIL = "不提供"
    NAME = "屏幕录制转GIF工具"


# ==================== 配置管理类 ====================
@dataclass
class AppConfig:
    """应用程序配置数据类"""
    output_directory: str = ""
    fps: int = 10
    scale_percent: int = 100
    quality: int = 80
    auto_start: bool = False
    show_preview: bool = True
    frame_skip: int = 0
    colors: int = 256
    window_x: int = 100
    window_y: int = 100
    window_width: int = 1200
    window_height: int = 800
    splitter_sizes: list = None
    last_selection: dict = None
    enable_size_control: bool = False
    target_size_kb: int = 1024
    size_control_mode: str = "auto"
    min_scale_percent: int = 30
    min_colors: int = 32
    auto_switch_tab: bool = True
    enable_file_manager_preview: bool = True
    enable_history_preview: bool = True
    auto_play_preview: bool = True
    
    def __post_init__(self):
        self._ensure_output_directory()
        if self.splitter_sizes is None:
            self.splitter_sizes = [350, 650]
    
    def _ensure_output_directory(self):
        program_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        default_output = os.path.join(program_dir, "ScreenToGIF_Recordings")
        
        if not self.output_directory:
            self.output_directory = default_output
        else:
            try:
                rel_path = os.path.relpath(self.output_directory, program_dir)
                if rel_path.startswith('..') or os.path.isabs(rel_path):
                    self.output_directory = default_output
            except:
                self.output_directory = default_output
    
    def save_to_file(self, filepath: str):
        try:
            self._ensure_output_directory()
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置文件失败: {e}")
    
    @classmethod
    def load_from_file(cls, filepath: str) -> 'AppConfig':
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                config = cls(**data)
                config._ensure_output_directory()
                return config
        except Exception as e:
            print(f"加载配置文件失败: {e}")
        return cls()


# ==================== 日志管理器 ====================
class LogManager:
    _instance = None
    _log_widgets = []
    _log_buffer = []
    _max_buffer_size = 1000
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._log_widgets = []
        self._log_buffer = []
    
    def register_widget(self, widget):
        if widget not in self._log_widgets:
            self._log_widgets.append(widget)
            for msg in self._log_buffer:
                self._append_to_widget(widget, msg)
    
    def unregister_widget(self, widget):
        if widget in self._log_widgets:
            self._log_widgets.remove(widget)
    
    def _append_to_widget(self, widget, message):
        try:
            widget.appendPlainText(message)
            scrollbar = widget.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        except Exception as e:
            print(f"写入日志控件失败: {e}")
    
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        
        self._log_buffer.append(log_entry)
        if len(self._log_buffer) > self._max_buffer_size:
            self._log_buffer.pop(0)
        
        print(log_entry)
        
        for widget in self._log_widgets:
            self._append_to_widget(widget, log_entry)
    
    def info(self, message):
        self.log(message, "INFO")
    
    def warning(self, message):
        self.log(message, "WARN")
    
    def error(self, message):
        self.log(message, "ERROR")
    
    def success(self, message):
        self.log(message, "SUCCESS")
    
    def clear(self):
        self._log_buffer.clear()
        for widget in self._log_widgets:
            widget.clear()


log_manager = LogManager()


# ==================== GIF预览控件 ====================
class GIFPreviewWidget(QWidget):
    """GIF快速预览控件 - 预览区域可伸缩"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_frames = []
        self.current_index = 0
        self.play_timer = QTimer()
        self.is_playing = False
        self.play_fps = 10
        self.auto_play = True
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # 标题栏
        title_widget = QWidget()
        title_widget.setStyleSheet("background-color: #e9ecef; border-radius: 4px;")
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(8, 4, 8, 4)
        
        title_label = QLabel("🎬 快速预览")
        title_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        title_layout.addWidget(title_label)
        
        title_layout.addStretch()
        
        self.preview_status_label = QLabel("未选择文件")
        self.preview_status_label.setStyleSheet("color: #6c757d; font-size: 10px;")
        title_layout.addWidget(self.preview_status_label)
        
        layout.addWidget(title_widget)
        
        # 预览区域 - 这是需要伸缩的核心区域
        preview_frame = QFrame()
        preview_frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border-radius: 6px;
            }
        """)
        # 设置预览区域可以拉伸
        preview_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        
        # 预览标签 - 用于显示GIF图片
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_label.setStyleSheet("background-color: transparent; color: #888;")
        self.preview_label.setText("点击文件查看预览")
        
        # 使用滚动区域包装预览标签，以便图片太大时可以滚动
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidget(self.preview_label)
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setAlignment(Qt.AlignCenter)
        self.preview_scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        preview_layout.addWidget(self.preview_scroll)
        
        layout.addWidget(preview_frame, 1)  # 拉伸因子为1，使预览区域可伸缩
        
        # 控制栏 - 固定高度
        control_bar = QWidget()
        control_bar.setStyleSheet("background-color: #f8f9fa; border-radius: 4px;")
        control_layout = QHBoxLayout(control_bar)
        control_layout.setContentsMargins(8, 4, 8, 4)
        control_layout.setSpacing(8)
        
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(30, 25)
        self.play_btn.setEnabled(False)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        control_layout.addWidget(self.play_btn)
        
        self.stop_btn = QPushButton("⏹")
        self.stop_btn.setFixedSize(30, 25)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        control_layout.addWidget(self.stop_btn)
        
        self.preview_slider = QSlider(Qt.Horizontal)
        self.preview_slider.setEnabled(False)
        self.preview_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.preview_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #dee2e6;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #0078d4;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background: #0078d4;
                border-radius: 2px;
            }
        """)
        control_layout.addWidget(self.preview_slider, 1)
        
        self.frame_counter = QLabel("0/0")
        self.frame_counter.setMinimumWidth(50)
        self.frame_counter.setStyleSheet("font-size: 10px; font-family: monospace;")
        control_layout.addWidget(self.frame_counter)
        
        layout.addWidget(control_bar)
        
        # 连接信号
        self.play_btn.clicked.connect(self.toggle_play)
        self.stop_btn.clicked.connect(self.stop_preview)
        self.preview_slider.valueChanged.connect(self.on_slider_changed)
        self.play_timer.timeout.connect(self.on_play_timeout)
    
    def set_auto_play(self, auto_play):
        self.auto_play = auto_play
    
    def load_gif(self, file_path):
        try:
            frames, fps = GIFLoader.load_gif(file_path)
            self.current_frames = frames
            self.play_fps = fps if fps > 0 else 10
            self.current_index = 0
            
            if self.is_playing:
                self.play_timer.stop()
                self.is_playing = False
                self.play_btn.setText("▶")
            
            if frames:
                self.preview_status_label.setText(f"{len(frames)}帧, {fps}fps")
                self.play_btn.setEnabled(True)
                self.stop_btn.setEnabled(True)
                self.preview_slider.setEnabled(True)
                self.preview_slider.setMaximum(len(frames) - 1)
                self._update_preview_frame()
                
                if self.auto_play:
                    QTimer.singleShot(100, self._start_auto_play)
                else:
                    self.is_playing = False
                    self.play_btn.setText("▶")
            else:
                self._clear_preview()
                
        except Exception as e:
            log_manager.error(f"预览加载失败: {e}")
            self._clear_preview()
            self.preview_status_label.setText("加载失败")
    
    def _start_auto_play(self):
        if self.current_frames and not self.is_playing and self.auto_play:
            interval = int(1000 / self.play_fps)
            self.play_timer.start(interval)
            self.is_playing = True
            self.play_btn.setText("⏸")
    
    def _update_preview_frame(self):
        if not self.current_frames or self.current_index >= len(self.current_frames):
            return
        try:
            frame = self.current_frames[self.current_index]
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = frame_rgb.shape[:2]
            
            # 获取滚动区域的视口大小
            viewport_size = self.preview_scroll.viewport().size()
            available_w = viewport_size.width() - 20
            available_h = viewport_size.height() - 20
            
            if available_w > 0 and available_h > 0:
                if w > available_w or h > available_h:
                    scale = min(available_w / w, available_h / h)
                    new_w = int(w * scale)
                    new_h = int(h * scale)
                else:
                    new_w, new_h = w, h
                
                if new_w > 0 and new_h > 0:
                    frame_resized = cv2.resize(frame_rgb, (new_w, new_h))
                    bytes_line = 3 * new_w
                    qimg = QImage(frame_resized.data, new_w, new_h, bytes_line, QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(qimg)
                    self.preview_label.setPixmap(pixmap)
                    self.preview_label.setFixedSize(new_w, new_h)
            
            self.frame_counter.setText(f"{self.current_index + 1}/{len(self.current_frames)}")
            self.preview_slider.blockSignals(True)
            self.preview_slider.setValue(self.current_index)
            self.preview_slider.blockSignals(False)
        except Exception as e:
            print(f"预览帧更新失败: {e}")
    
    def _clear_preview(self):
        self.current_frames = []
        self.current_index = 0
        self.is_playing = False
        self.play_btn.setText("▶")
        self.play_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.preview_slider.setEnabled(False)
        self.preview_slider.setMaximum(0)
        self.frame_counter.setText("0/0")
        self.preview_label.clear()
        self.preview_label.setText("无预览")
        self.preview_label.setFixedSize(200, 100)
        self.play_timer.stop()
    
    def toggle_play(self):
        if not self.current_frames:
            return
        if self.is_playing:
            self.play_timer.stop()
            self.is_playing = False
            self.play_btn.setText("▶")
        else:
            interval = int(1000 / self.play_fps)
            self.play_timer.start(interval)
            self.is_playing = True
            self.play_btn.setText("⏸")
    
    def stop_preview(self):
        self.play_timer.stop()
        self.is_playing = False
        self.play_btn.setText("▶")
        self.current_index = 0
        self._update_preview_frame()
    
    def on_play_timeout(self):
        if self.current_frames and self.is_playing:
            self.current_index = (self.current_index + 1) % len(self.current_frames)
            self._update_preview_frame()
    
    def on_slider_changed(self, value):
        if not self.is_playing and self.current_frames and 0 <= value < len(self.current_frames):
            self.current_index = value
            self._update_preview_frame()
    
    def clear(self):
        self._clear_preview()
        self.preview_status_label.setText("未选择文件")
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_frames:
            self._update_preview_frame()
    
    def closeEvent(self, event):
        self.play_timer.stop()
        event.accept()


# ==================== 文件管理器 ====================
class FileManagerWidget(QWidget):
    file_selected = Signal(str)
    file_double_clicked = Signal(str)
    file_deleted = Signal(str)
    
    def __init__(self, directory, parent=None):
        super().__init__(parent)
        self.directory = directory
        self.current_path = directory
        self.setup_ui()
        self.refresh()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                padding: 5px 10px;
                border-radius: 4px;
                font-family: monospace;
                font-size: 11px;
            }
        """)
        toolbar.addWidget(self.path_label, 1)
        
        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.setFixedSize(80, 28)
        self.refresh_btn.setObjectName("info_button")
        self.refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self.refresh_btn)
        
        self.open_dir_btn = QPushButton("📂 打开")
        self.open_dir_btn.setFixedSize(80, 28)
        self.open_dir_btn.setObjectName("info_button")
        self.open_dir_btn.clicked.connect(self.open_current_directory)
        toolbar.addWidget(self.open_dir_btn)
        
        layout.addLayout(toolbar)
        
        # 文件树 - 固定高度，不伸缩
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["名称", "大小", "修改时间"])
        self.file_tree.setIndentation(20)
        self.file_tree.setAlternatingRowColors(True)
        self.file_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.file_tree.itemClicked.connect(self.on_item_clicked)
        self.file_tree.customContextMenuRequested.connect(self.show_context_menu)
        # 设置固定高度策略，不随窗口拉伸
        self.file_tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        
        header = self.file_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        
        self.file_tree.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QTreeWidget::item:hover {
                background-color: #e3f2fd;
            }
            QTreeWidget::item:selected {
                background-color: #0078d4;
                color: white;
            }
        """)
        
        layout.addWidget(self.file_tree)
        
        # 底部信息栏
        info_bar = QHBoxLayout()
        self.file_count_label = QLabel("文件数: 0")
        self.file_count_label.setStyleSheet("color: #666; font-size: 11px;")
        info_bar.addWidget(self.file_count_label)
        info_bar.addStretch()
        
        self.total_size_label = QLabel("总大小: 0 KB")
        self.total_size_label.setStyleSheet("color: #666; font-size: 11px;")
        info_bar.addWidget(self.total_size_label)
        
        layout.addLayout(info_bar)
    
    def set_directory(self, directory):
        self.directory = directory
        self.current_path = directory
        self.refresh()
    
    def refresh(self):
        self.file_tree.clear()
        
        if not os.path.exists(self.directory):
            os.makedirs(self.directory, exist_ok=True)
        
        display_path = self.current_path
        if len(display_path) > 60:
            display_path = "..." + display_path[-57:]
        self.path_label.setText(f"📁 {display_path}")
        
        total_size = 0
        file_count = 0
        
        try:
            if self.current_path != self.directory:
                parent_item = QTreeWidgetItem(["📁 ..", "", ""])
                parent_item.setData(0, Qt.UserRole, "__parent__")
                parent_item.setForeground(0, QColor(0, 120, 215))
                self.file_tree.addTopLevelItem(parent_item)
            
            items = []
            for name in os.listdir(self.current_path):
                full_path = os.path.join(self.current_path, name)
                
                try:
                    stat = os.stat(full_path)
                    size = stat.st_size
                    mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                except:
                    size = 0
                    mtime = "未知"
                
                if os.path.isdir(full_path):
                    size_str = "文件夹"
                    icon = "📁"
                    items.append((name, full_path, size_str, mtime, True))
                else:
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    else:
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                    
                    ext = os.path.splitext(name)[1].lower()
                    if ext == '.gif':
                        icon = "🎬"
                    elif ext in ['.png', '.jpg', '.jpeg', '.bmp']:
                        icon = "🖼️"
                    else:
                        icon = "📄"
                    
                    items.append((name, full_path, size_str, mtime, False))
                    total_size += size
                    file_count += 1
            
            items.sort(key=lambda x: (not x[4], x[0].lower()))
            
            for name, full_path, size_str, mtime, is_dir in items:
                display_name = name if len(name) <= 50 else name[:47] + "..."
                item = QTreeWidgetItem([f"{icon} {display_name}", size_str, mtime])
                item.setData(0, Qt.UserRole, full_path)
                if is_dir:
                    item.setForeground(0, QColor(0, 100, 0))
                self.file_tree.addTopLevelItem(item)
            
            self.file_count_label.setText(f"文件数: {file_count}")
            if total_size < 1024 * 1024:
                self.total_size_label.setText(f"总大小: {total_size / 1024:.1f} KB")
            else:
                self.total_size_label.setText(f"总大小: {total_size / (1024 * 1024):.1f} MB")
                
        except Exception as e:
            log_manager.error(f"刷新文件列表失败: {e}")
    
    def open_current_directory(self):
        if os.path.exists(self.current_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.current_path))
    
    def on_item_clicked(self, item, column):
        full_path = item.data(0, Qt.UserRole)
        if not full_path or full_path == "__parent__":
            return
        
        if not os.path.isdir(full_path) and full_path.lower().endswith('.gif'):
            self.file_selected.emit(full_path)
    
    def on_item_double_clicked(self, item, column):
        full_path = item.data(0, Qt.UserRole)
        if not full_path:
            return
        
        if full_path == "__parent__":
            self.current_path = os.path.dirname(self.current_path)
            self.refresh()
            return
        
        if os.path.isdir(full_path):
            self.current_path = full_path
            self.refresh()
        else:
            if full_path.lower().endswith('.gif'):
                self.file_double_clicked.emit(full_path)
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(full_path))
    
    def show_context_menu(self, position):
        item = self.file_tree.itemAt(position)
        if not item:
            return
        
        full_path = item.data(0, Qt.UserRole)
        if not full_path or full_path == "__parent__":
            return
        
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                padding: 5px;
                min-width: 160px;
            }
            QMenu::item {
                padding: 6px 25px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #0078d4;
                color: white;
            }
            QMenu::separator {
                height: 1px;
                background-color: #dee2e6;
                margin: 5px 0;
            }
        """)
        
        is_dir = os.path.isdir(full_path)
        
        if is_dir:
            open_action = QAction("📂 打开文件夹", self)
            open_action.triggered.connect(lambda: self._open_in_explorer(full_path))
            menu.addAction(open_action)
            
            menu.addSeparator()
            
            delete_action = QAction("🗑 删除文件夹", self)
            delete_action.triggered.connect(lambda: self._delete_item(full_path, item))
            menu.addAction(delete_action)
        else:
            open_action = QAction("▶ 打开/预览", self)
            open_action.triggered.connect(lambda: self._open_file(full_path))
            menu.addAction(open_action)
            
            open_location_action = QAction("📂 打开文件位置", self)
            open_location_action.triggered.connect(lambda: self._open_in_explorer(os.path.dirname(full_path)))
            menu.addAction(open_location_action)
            
            menu.addSeparator()
            
            if full_path.lower().endswith('.gif'):
                edit_action = QAction("✎ 编辑GIF", self)
                edit_action.triggered.connect(lambda: self.file_double_clicked.emit(full_path))
                menu.addAction(edit_action)
                
                copy_path_action = QAction("📋 复制文件路径", self)
                copy_path_action.triggered.connect(lambda: self._copy_path(full_path))
                menu.addAction(copy_path_action)
                
                menu.addSeparator()
            
            rename_action = QAction("✏️ 重命名", self)
            rename_action.triggered.connect(lambda: self._rename_item(full_path, item))
            menu.addAction(rename_action)
            
            delete_action = QAction("🗑 删除", self)
            delete_action.triggered.connect(lambda: self._delete_item(full_path, item))
            menu.addAction(delete_action)
            
            menu.addSeparator()
            
            batch_menu = menu.addMenu("📦 批量操作")
            
            select_all_action = QAction("全选", self)
            select_all_action.triggered.connect(self._select_all_files)
            batch_menu.addAction(select_all_action)
            
            batch_delete_action = QAction("删除选中项", self)
            batch_delete_action.triggered.connect(self._delete_selected_items)
            batch_menu.addAction(batch_delete_action)
        
        menu.exec(self.file_tree.viewport().mapToGlobal(position))
    
    def _open_file(self, path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    
    def _open_in_explorer(self, path):
        if os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    
    def _copy_path(self, path):
        clipboard = QApplication.clipboard()
        clipboard.setText(path)
        log_manager.info(f"已复制路径: {path}")
        QMessageBox.information(self, "提示", "文件路径已复制到剪贴板")
    
    def _rename_item(self, path, item):
        old_name = os.path.basename(path)
        new_name, ok = QInputDialog.getText(self, "重命名", "请输入新名称:", text=old_name)
        
        if ok and new_name and new_name != old_name:
            new_path = os.path.join(os.path.dirname(path), new_name)
            try:
                os.rename(path, new_path)
                log_manager.info(f"重命名: {old_name} -> {new_name}")
                self.refresh()
            except Exception as e:
                log_manager.error(f"重命名失败: {e}")
                QMessageBox.critical(self, "错误", f"重命名失败:\n{str(e)}")
    
    def _delete_item(self, path, item):
        name = os.path.basename(path)
        is_dir = os.path.isdir(path)
        
        msg = f"确定删除 {'文件夹' if is_dir else '文件'} '{name}' 吗？\n此操作不可恢复！"
        reply = QMessageBox.question(self, "确认删除", msg, 
                                      QMessageBox.Yes | QMessageBox.No,
                                      QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            try:
                if is_dir:
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                log_manager.info(f"已删除: {name}")
                self.refresh()
                self.file_deleted.emit(path)
            except Exception as e:
                log_manager.error(f"删除失败: {e}")
                QMessageBox.critical(self, "错误", f"删除失败:\n{str(e)}")
    
    def _select_all_files(self):
        self.file_tree.clearSelection()
        for i in range(self.file_tree.topLevelItemCount()):
            item = self.file_tree.topLevelItem(i)
            full_path = item.data(0, Qt.UserRole)
            if full_path and full_path != "__parent__":
                if not os.path.isdir(full_path):
                    item.setSelected(True)
    
    def _delete_selected_items(self):
        selected_items = self.file_tree.selectedItems()
        if not selected_items:
            return
        
        file_count = sum(1 for item in selected_items 
                        if item.data(0, Qt.UserRole) and 
                        item.data(0, Qt.UserRole) != "__parent__" and
                        not os.path.isdir(item.data(0, Qt.UserRole)))
        
        if file_count == 0:
            return
        
        reply = QMessageBox.question(self, "确认删除", 
                                      f"确定删除选中的 {file_count} 个文件吗？\n此操作不可恢复！",
                                      QMessageBox.Yes | QMessageBox.No,
                                      QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            deleted = 0
            for item in selected_items:
                full_path = item.data(0, Qt.UserRole)
                if full_path and full_path != "__parent__" and not os.path.isdir(full_path):
                    try:
                        os.remove(full_path)
                        deleted += 1
                    except Exception as e:
                        log_manager.error(f"删除失败: {full_path} - {e}")
            
            log_manager.info(f"批量删除完成: 已删除 {deleted} 个文件")
            self.refresh()
    
    def get_current_directory(self):
        return self.current_path


# ==================== GIF文件加载器 ====================
class GIFLoader:
    @staticmethod
    def load_gif(file_path: str) -> Tuple[List[np.ndarray], int]:
        try:
            gif = Image.open(file_path)
            frames = []
            fps = 10
            
            try:
                duration = gif.info.get('duration', 100)
                fps = int(1000 / duration) if duration > 0 else 10
            except:
                fps = 10
            
            while True:
                if gif.mode != 'RGB':
                    frame_rgb = gif.convert('RGB')
                else:
                    frame_rgb = gif.copy()
                
                frame_np = np.array(frame_rgb)
                frame_bgr = cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR)
                frames.append(frame_bgr)
                gif.seek(gif.tell() + 1)
                
        except EOFError:
            pass
        except Exception as e:
            raise Exception(f"加载GIF失败: {str(e)}")
        
        if not frames:
            raise Exception("GIF文件没有有效的帧")
        
        return frames, fps
    
    @staticmethod
    def load_from_clipboard() -> Optional[Tuple[List[np.ndarray], int]]:
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        
        if mime_data.hasImage():
            qimage = clipboard.image()
            if not qimage.isNull():
                width = qimage.width()
                height = qimage.height()
                
                if qimage.format() == QImage.Format_RGB32:
                    ptr = qimage.constBits()
                    ptr.setsize(height * width * 4)
                    arr = np.array(ptr).reshape(height, width, 4)
                    frame_bgr = arr[:, :, :3].copy()
                else:
                    qimage_rgb = qimage.convertToFormat(QImage.Format_RGB888)
                    ptr = qimage_rgb.constBits()
                    ptr.setsize(height * width * 3)
                    arr = np.array(ptr).reshape(height, width, 3)
                    frame_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                
                return [frame_bgr], 10
        
        if mime_data.hasUrls():
            urls = mime_data.urls()
            for url in urls:
                file_path = url.toLocalFile()
                if file_path and file_path.lower().endswith('.gif'):
                    return GIFLoader.load_gif(file_path)
        
        return None


# ==================== 文件大小估算器 ====================
class GIFSizeEstimator:
    COMPRESSION_FACTORS = {
        'high_motion': 0.25,
        'medium_motion': 0.18,
        'low_motion': 0.12,
    }
    
    @staticmethod
    def estimate_size(frame_count, width, height, fps, colors, quality, motion_factor=0.18):
        if frame_count == 0:
            return 0
        
        raw_frame_size = width * height * 3
        colors_factor = (colors / 256) ** 0.6
        quality_factor = quality / 100
        fps_factor = min(1.2, 30 / max(1, fps)) * 0.3 + 0.7
        
        compression_ratio = motion_factor * colors_factor * quality_factor * fps_factor
        estimated_bytes = frame_count * raw_frame_size * compression_ratio
        estimated_bytes += 1024
        estimated_bytes += frame_count * 128
        
        if colors < 256:
            estimated_bytes += colors * 3
        
        estimated_kb = estimated_bytes / 1024
        return max(10, int(estimated_kb))
    
    @staticmethod
    def find_optimal_params(frame_count, width, height, target_kb, current_config, 
                           min_scale=30, min_colors=32, mode="auto"):
        param_options = {
            'colors': [256, 224, 192, 160, 128, 96, 80, 64, 56, 48, 40, 32],
            'scale': [100, 90, 80, 70, 65, 60, 55, 50, 45, 40, 38, 35, 33, 30],
            'quality': [100, 95, 90, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30, 25, 20],
            'fps': [30, 25, 20, 18, 15, 12, 10, 8, 6, 5, 4, 3, 2, 1]
        }
        
        if mode == "quality":
            param_priority = ['fps', 'colors', 'quality', 'scale']
        elif mode == "size":
            param_priority = ['scale', 'colors', 'fps', 'quality']
        else:
            param_priority = ['colors', 'fps', 'scale', 'quality']
        
        best_params = {
            'fps': current_config.get('fps', 10),
            'scale': current_config.get('scale', 100),
            'quality': current_config.get('quality', 80),
            'colors': current_config.get('colors', 256)
        }
        
        scaled_width = int(width * best_params['scale'] / 100)
        scaled_height = int(height * best_params['scale'] / 100)
        current_size = GIFSizeEstimator.estimate_size(
            frame_count, scaled_width, scaled_height,
            best_params['fps'], best_params['colors'], best_params['quality']
        )
        
        log_manager.info(f"========== 开始文件大小优化 ==========")
        log_manager.info(f"帧数: {frame_count}, 原始尺寸: {width}x{height}")
        log_manager.info(f"目标大小: {target_kb}KB, 优化模式: {mode}")
        log_manager.info(f"当前配置: FPS={best_params['fps']}, 缩放={best_params['scale']}%, "
                        f"颜色={best_params['colors']}, 质量={best_params['quality']}%")
        log_manager.info(f"当前估计: {current_size}KB")
        
        reached_target = current_size <= target_kb
        
        if current_size <= target_kb:
            log_manager.info("当前大小已满足目标，尝试提高画质...")
            for param_name in param_priority:
                current_val = best_params[param_name]
                options = param_options.get(param_name, [])
                if not options:
                    continue
                try:
                    idx = options.index(current_val)
                    for i in range(idx - 1, -1, -1):
                        test_val = options[i]
                        if param_name == 'scale' and test_val > 100:
                            continue
                        if param_name == 'colors' and test_val > 256:
                            continue
                        if param_name == 'quality' and test_val > 100:
                            continue
                        if param_name == 'fps' and test_val > 30:
                            continue
                            
                        test_params = best_params.copy()
                        test_params[param_name] = test_val
                        test_width = int(width * test_params['scale'] / 100)
                        test_height = int(height * test_params['scale'] / 100)
                        test_size = GIFSizeEstimator.estimate_size(
                            frame_count, test_width, test_height,
                            test_params['fps'], test_params['colors'], test_params['quality']
                        )
                        if test_size <= target_kb:
                            best_params[param_name] = test_val
                            current_size = test_size
                            log_manager.info(f"提高 {param_name}: {test_val} (原:{current_val}), 新大小: {test_size}KB")
                            break
                except ValueError:
                    continue
        else:
            log_manager.info("当前大小超过目标，开始压缩...")
            for param_name in param_priority:
                current_val = best_params[param_name]
                options = param_options.get(param_name, [])
                if not options:
                    continue
                
                min_val = 1
                if param_name == 'scale':
                    min_val = min_scale
                elif param_name == 'colors':
                    min_val = min_colors
                elif param_name == 'quality':
                    min_val = 20
                elif param_name == 'fps':
                    min_val = 1
                
                try:
                    idx = options.index(current_val)
                    for i in range(idx + 1, len(options)):
                        test_val = options[i]
                        if test_val < min_val:
                            continue
                        test_params = best_params.copy()
                        test_params[param_name] = test_val
                        test_width = int(width * test_params['scale'] / 100)
                        test_height = int(height * test_params['scale'] / 100)
                        test_size = GIFSizeEstimator.estimate_size(
                            frame_count, test_width, test_height,
                            test_params['fps'], test_params['colors'], test_params['quality']
                        )
                        if test_size <= target_kb:
                            best_params[param_name] = test_val
                            current_size = test_size
                            log_manager.info(f"降低 {param_name}: {test_val} (原:{current_val}), 新大小: {test_size}KB")
                            break
                except ValueError:
                    continue
                
                curr_width = int(width * best_params['scale'] / 100)
                curr_height = int(height * best_params['scale'] / 100)
                current_size = GIFSizeEstimator.estimate_size(
                    frame_count, curr_width, curr_height,
                    best_params['fps'], best_params['colors'], best_params['quality']
                )
                
                if current_size <= target_kb:
                    log_manager.info(f"已达到目标大小: {current_size}KB <= {target_kb}KB")
                    break
        
        final_width = int(width * best_params['scale'] / 100)
        final_height = int(height * best_params['scale'] / 100)
        final_size = GIFSizeEstimator.estimate_size(
            frame_count, final_width, final_height,
            best_params['fps'], best_params['colors'], best_params['quality']
        )
        
        reached_target = final_size <= target_kb
        
        log_manager.info(f"========== 优化结果 ==========")
        log_manager.info(f"最终配置: FPS={best_params['fps']}, 缩放={best_params['scale']}%, "
                        f"颜色={best_params['colors']}, 质量={best_params['quality']}%")
        log_manager.info(f"最终尺寸: {final_width}x{final_height}")
        log_manager.info(f"最终估计: {final_size}KB, 目标: {target_kb}KB")
        log_manager.info(f"目标达成: {'是' if reached_target else '否'}")
        
        return best_params, final_size, reached_target


# ==================== 帧编辑器对话框 ====================
class FrameEditorDialog(QDialog):
    def __init__(self, frames, parent=None):
        super().__init__(parent)
        self.frames = frames.copy()
        self.current_frames = frames.copy()
        self.current_index = 0
        self.play_timer = QTimer()
        self.is_playing = False
        self.play_fps = 10
        self.zoom_level = 0
        self.clipboard_frames = []
        self.status_label = QLabel()
        
        self.setWindowTitle("帧编辑器")
        self.setMinimumSize(1200, 700)
        self.setModal(True)
        
        self._setup_ui()
        self._setup_signals()
        self._setup_keyboard_shortcuts()
        self._setup_context_menu()
        self._update_preview()
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        top_toolbar = self._create_top_toolbar()
        main_layout.addWidget(top_toolbar)
        
        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.setHandleWidth(3)
        
        left_panel = self._create_frame_list_panel()
        content_splitter.addWidget(left_panel)
        
        center_panel = self._create_preview_panel()
        content_splitter.addWidget(center_panel)
        
        right_panel = self._create_property_panel()
        content_splitter.addWidget(right_panel)
        
        content_splitter.setSizes([280, 550, 220])
        
        main_layout.addWidget(content_splitter, 1)
        
        bottom_bar = self._create_bottom_bar()
        main_layout.addWidget(bottom_bar)
        
        self._load_frames_to_list()
    
    def _create_top_toolbar(self):
        toolbar = QWidget()
        toolbar.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border-radius: 8px;
                padding: 5px;
            }
        """)
        layout = QHBoxLayout(toolbar)
        layout.setSpacing(15)
        layout.setContentsMargins(10, 5, 10, 5)
        
        play_group = QWidget()
        play_layout = QHBoxLayout(play_group)
        play_layout.setSpacing(8)
        play_layout.setContentsMargins(0, 0, 0, 0)
        
        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.setCheckable(True)
        self.play_btn.setFixedSize(80, 32)
        self.play_btn.setStyleSheet("""
            QPushButton { background-color: #28a745; color: white; font-weight: bold; }
            QPushButton:checked { background-color: #dc3545; }
            QPushButton:hover { background-color: #218838; }
            QPushButton:checked:hover { background-color: #c82333; }
        """)
        play_layout.addWidget(self.play_btn)
        
        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setFixedSize(80, 32)
        self.stop_btn.setStyleSheet("background-color: #6c757d; color: white;")
        play_layout.addWidget(self.stop_btn)
        
        layout.addWidget(play_group)
        
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setFixedWidth(2)
        sep1.setStyleSheet("background-color: #dee2e6;")
        layout.addWidget(sep1)
        
        nav_group = QWidget()
        nav_layout = QHBoxLayout(nav_group)
        nav_layout.setSpacing(3)
        
        self.first_btn = QPushButton("⏮⏮")
        self.first_btn.setFixedSize(40, 32)
        self.first_btn.setToolTip("第一帧 (Home)")
        nav_layout.addWidget(self.first_btn)
        
        self.prev_10_btn = QPushButton("◀◀")
        self.prev_10_btn.setFixedSize(40, 32)
        self.prev_10_btn.setToolTip("向前10帧")
        nav_layout.addWidget(self.prev_10_btn)
        
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setFixedSize(40, 32)
        self.prev_btn.setToolTip("上一帧 (←)")
        nav_layout.addWidget(self.prev_btn)
        
        self.next_btn = QPushButton("▶")
        self.next_btn.setFixedSize(40, 32)
        self.next_btn.setToolTip("下一帧 (→)")
        nav_layout.addWidget(self.next_btn)
        
        self.next_10_btn = QPushButton("▶▶")
        self.next_10_btn.setFixedSize(40, 32)
        self.next_10_btn.setToolTip("向后10帧")
        nav_layout.addWidget(self.next_10_btn)
        
        self.last_btn = QPushButton("⏭⏭")
        self.last_btn.setFixedSize(40, 32)
        self.last_btn.setToolTip("最后一帧 (End)")
        nav_layout.addWidget(self.last_btn)
        
        layout.addWidget(nav_group)
        
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setFixedWidth(2)
        sep2.setStyleSheet("background-color: #dee2e6;")
        layout.addWidget(sep2)
        
        action_group = QWidget()
        action_layout = QHBoxLayout(action_group)
        action_layout.setSpacing(5)
        
        self.delete_btn = QPushButton("🗑 删除")
        self.delete_btn.setFixedSize(80, 32)
        self.delete_btn.setStyleSheet("background-color: #dc3545; color: white;")
        action_layout.addWidget(self.delete_btn)
        
        self.delete_selected_btn = QPushButton("🗑🗑 批量删除")
        self.delete_selected_btn.setFixedSize(100, 32)
        self.delete_selected_btn.setStyleSheet("background-color: #dc3545; color: white;")
        self.delete_selected_btn.setToolTip("删除所有选中的帧")
        action_layout.addWidget(self.delete_selected_btn)
        
        self.duplicate_btn = QPushButton("📋 复制")
        self.duplicate_btn.setFixedSize(80, 32)
        self.duplicate_btn.setStyleSheet("background-color: #17a2b8; color: white;")
        action_layout.addWidget(self.duplicate_btn)
        
        self.insert_btn = QPushButton("➕ 插入")
        self.insert_btn.setFixedSize(80, 32)
        self.insert_btn.setStyleSheet("background-color: #ffc107; color: black;")
        action_layout.addWidget(self.insert_btn)
        
        layout.addWidget(action_group)
        
        layout.addStretch()
        
        info_group = QWidget()
        info_layout = QHBoxLayout(info_group)
        info_layout.setSpacing(15)
        
        self.frame_info_label = QLabel()
        self.frame_info_label.setStyleSheet("""
            QLabel {
                background-color: #e9ecef;
                padding: 5px 12px;
                border-radius: 5px;
                font-family: monospace;
                font-size: 13px;
            }
        """)
        info_layout.addWidget(self.frame_info_label)
        
        self.file_size_label = QLabel()
        self.file_size_label.setStyleSheet("""
            QLabel {
                background-color: #e9ecef;
                padding: 5px 12px;
                border-radius: 5px;
                font-family: monospace;
                font-size: 13px;
            }
        """)
        info_layout.addWidget(self.file_size_label)
        
        layout.addWidget(info_group)
        
        return toolbar
    
    def _create_frame_list_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)
        
        title_widget = QWidget()
        title_widget.setStyleSheet("background-color: #e9ecef; border-radius: 5px;")
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(10, 8, 10, 8)
        
        title_label = QLabel("📷 帧列表")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title_label)
        
        title_layout.addStretch()
        
        self.frame_count_label = QLabel("0 帧")
        self.frame_count_label.setStyleSheet("color: #6c757d;")
        title_layout.addWidget(self.frame_count_label)
        
        layout.addWidget(title_widget)
        
        self.frame_list = QListWidget()
        self.frame_list.setViewMode(QListWidget.ListMode)
        self.frame_list.setIconSize(QSize(80, 60))
        self.frame_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.frame_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.frame_list.setAlternatingRowColors(True)
        self.frame_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 2px;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:hover {
                background-color: #e3f2fd;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
                color: white;
            }
        """)
        layout.addWidget(self.frame_list)
        
        select_bar = QWidget()
        select_bar.setStyleSheet("background-color: #f8f9fa; border-radius: 5px;")
        select_layout = QHBoxLayout(select_bar)
        select_layout.setContentsMargins(10, 8, 10, 8)
        
        self.select_all_btn = QPushButton("全选 (Ctrl+A)")
        self.select_all_btn.setFixedSize(100, 28)
        select_layout.addWidget(self.select_all_btn)
        
        self.deselect_all_btn = QPushButton("取消")
        self.deselect_all_btn.setFixedSize(60, 28)
        select_layout.addWidget(self.deselect_all_btn)
        
        self.invert_selection_btn = QPushButton("反选")
        self.invert_selection_btn.setFixedSize(60, 28)
        select_layout.addWidget(self.invert_selection_btn)
        
        select_layout.addStretch()
        
        self.selected_count_label = QLabel("已选中: 0")
        self.selected_count_label.setStyleSheet("color: #0078d4; font-weight: bold;")
        select_layout.addWidget(self.selected_count_label)
        
        layout.addWidget(select_bar)
        
        return panel
    
    def _create_preview_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)
        
        preview_toolbar = QWidget()
        preview_toolbar.setStyleSheet("background-color: #e9ecef; border-radius: 5px;")
        toolbar_layout = QHBoxLayout(preview_toolbar)
        toolbar_layout.setContentsMargins(10, 5, 10, 5)
        
        toolbar_layout.addWidget(QLabel("🔍 预览:"))
        
        self.zoom_in_btn = QPushButton("放大")
        self.zoom_in_btn.setFixedSize(60, 28)
        toolbar_layout.addWidget(self.zoom_in_btn)
        
        self.zoom_out_btn = QPushButton("缩小")
        self.zoom_out_btn.setFixedSize(60, 28)
        toolbar_layout.addWidget(self.zoom_out_btn)
        
        self.zoom_fit_btn = QPushButton("适应窗口")
        self.zoom_fit_btn.setFixedSize(80, 28)
        self.zoom_fit_btn.setStyleSheet("background-color: #0078d4; color: white;")
        toolbar_layout.addWidget(self.zoom_fit_btn)
        
        self.zoom_100_btn = QPushButton("100%")
        self.zoom_100_btn.setFixedSize(60, 28)
        toolbar_layout.addWidget(self.zoom_100_btn)
        
        toolbar_layout.addStretch()
        
        toolbar_layout.addWidget(QLabel("播放速度:"))
        self.play_fps_spin = QSpinBox()
        self.play_fps_spin.setRange(1, 30)
        self.play_fps_spin.setValue(10)
        self.play_fps_spin.setSuffix(" fps")
        self.play_fps_spin.setFixedWidth(80)
        toolbar_layout.addWidget(self.play_fps_spin)
        
        layout.addWidget(preview_toolbar)
        
        preview_frame = QFrame()
        preview_frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border-radius: 8px;
            }
        """)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(400, 300)
        self.preview_label.setStyleSheet("background-color: transparent;")
        
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidget(self.preview_label)
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setAlignment(Qt.AlignCenter)
        self.preview_scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        preview_layout.addWidget(self.preview_scroll)
        
        layout.addWidget(preview_frame)
        
        progress_bar = QWidget()
        progress_layout = QHBoxLayout(progress_bar)
        progress_layout.setContentsMargins(0, 5, 0, 0)
        
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #dee2e6;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #0078d4;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::sub-page:horizontal {
                background: #0078d4;
                border-radius: 3px;
            }
        """)
        progress_layout.addWidget(self.frame_slider)
        
        self.frame_counter = QLabel("0 / 0")
        self.frame_counter.setMinimumWidth(80)
        self.frame_counter.setAlignment(Qt.AlignRight)
        self.frame_counter.setStyleSheet("""
            QLabel {
                font-family: monospace;
                font-size: 14px;
                font-weight: bold;
                padding: 5px;
            }
        """)
        progress_layout.addWidget(self.frame_counter)
        
        layout.addWidget(progress_bar)
        
        return panel
    
    def _create_property_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        
        info_group = QGroupBox("当前帧信息")
        info_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        info_layout = QFormLayout(info_group)
        info_layout.setSpacing(8)
        
        self.current_frame_num = QLabel("-")
        self.current_frame_num.setStyleSheet("font-family: monospace; font-size: 16px; font-weight: bold; color: #0078d4;")
        info_layout.addRow("帧序号:", self.current_frame_num)
        
        self.frame_size_label = QLabel("-")
        info_layout.addRow("分辨率:", self.frame_size_label)
        
        layout.addWidget(info_group)
        
        batch_group = QGroupBox("批量操作")
        batch_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        batch_layout = QVBoxLayout(batch_group)
        batch_layout.setSpacing(8)
        
        move_widget = QWidget()
        move_layout = QHBoxLayout(move_widget)
        move_layout.setSpacing(8)
        
        self.move_up_btn = QPushButton("↑ 上移")
        self.move_up_btn.setFixedHeight(35)
        move_layout.addWidget(self.move_up_btn)
        
        self.move_down_btn = QPushButton("↓ 下移")
        self.move_down_btn.setFixedHeight(35)
        move_layout.addWidget(self.move_down_btn)
        
        batch_layout.addWidget(move_widget)
        
        batch_move_widget = QWidget()
        batch_move_layout = QHBoxLayout(batch_move_widget)
        batch_move_layout.setSpacing(8)
        
        self.batch_move_up_btn = QPushButton("↑↑ 批量上移")
        self.batch_move_up_btn.setFixedHeight(35)
        self.batch_move_up_btn.setToolTip("将所有选中的帧向上移动一位")
        batch_move_layout.addWidget(self.batch_move_up_btn)
        
        self.batch_move_down_btn = QPushButton("↓↓ 批量下移")
        self.batch_move_down_btn.setFixedHeight(35)
        self.batch_move_down_btn.setToolTip("将所有选中的帧向下移动一位")
        batch_move_layout.addWidget(self.batch_move_down_btn)
        
        batch_layout.addWidget(batch_move_widget)
        
        self.reverse_btn = QPushButton("🔄 反转顺序")
        self.reverse_btn.setFixedHeight(35)
        batch_layout.addWidget(self.reverse_btn)
        
        self.extract_btn = QPushButton("💾 导出当前帧")
        self.extract_btn.setFixedHeight(35)
        batch_layout.addWidget(self.extract_btn)
        
        self.extract_all_btn = QPushButton("📁 导出所有帧")
        self.extract_all_btn.setFixedHeight(35)
        self.extract_all_btn.setToolTip("将所有帧导出为图片序列")
        batch_layout.addWidget(self.extract_all_btn)
        
        layout.addWidget(batch_group)
        
        clipboard_group = QGroupBox("剪贴板操作")
        clipboard_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        clipboard_layout = QVBoxLayout(clipboard_group)
        
        self.copy_btn = QPushButton("📋 复制选中帧")
        self.copy_btn.setFixedHeight(35)
        self.copy_btn.setToolTip("复制选中的帧到剪贴板")
        clipboard_layout.addWidget(self.copy_btn)
        
        self.cut_btn = QPushButton("✂️ 剪切选中帧")
        self.cut_btn.setFixedHeight(35)
        self.cut_btn.setToolTip("剪切选中的帧到剪贴板")
        clipboard_layout.addWidget(self.cut_btn)
        
        self.paste_btn = QPushButton("📌 粘贴帧")
        self.paste_btn.setFixedHeight(35)
        self.paste_btn.setToolTip("从剪贴板粘贴帧到当前位置之后")
        self.paste_btn.setEnabled(False)
        clipboard_layout.addWidget(self.paste_btn)
        
        layout.addWidget(clipboard_group)
        
        stats_group = QGroupBox("统计信息")
        stats_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        stats_layout = QFormLayout(stats_group)
        stats_layout.setSpacing(8)
        
        self.total_frames_stat = QLabel("0")
        self.total_frames_stat.setStyleSheet("font-weight: bold; color: #28a745;")
        stats_layout.addRow("总帧数:", self.total_frames_stat)
        
        self.selected_stat = QLabel("0")
        self.selected_stat.setStyleSheet("font-weight: bold; color: #0078d4;")
        stats_layout.addRow("已选中:", self.selected_stat)
        
        layout.addWidget(stats_group)
        
        action_group = QGroupBox("操作")
        action_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        action_layout = QVBoxLayout(action_group)
        action_layout.setSpacing(8)
        
        self.reset_btn = QPushButton("↺ 重置所有编辑")
        self.reset_btn.setFixedHeight(40)
        self.reset_btn.setStyleSheet("background-color: #ffc107; color: black; font-weight: bold;")
        action_layout.addWidget(self.reset_btn)
        
        layout.addWidget(action_group)
        
        layout.addStretch()
        
        return panel
    
    def _create_bottom_bar(self):
        bottom_bar = QWidget()
        bottom_bar.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        layout = QHBoxLayout(bottom_bar)
        layout.setContentsMargins(15, 8, 15, 8)
        
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #28a745; font-size: 11px; padding: 5px; min-width: 200px;")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        tip_label = QLabel("💡 提示: 右键点击帧列表 | 方向键←→切换帧 | Ctrl+A全选 | Del删除选中 | Ctrl+C/V复制粘贴")
        tip_label.setStyleSheet("color: #6c757d; font-size: 11px;")
        layout.addWidget(tip_label)
        
        layout.addStretch()
        
        self.ok_btn = QPushButton("✓ 应用修改")
        self.ok_btn.setFixedSize(120, 36)
        self.ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        layout.addWidget(self.ok_btn)
        
        self.cancel_btn = QPushButton("✗ 取消")
        self.cancel_btn.setFixedSize(100, 36)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        layout.addWidget(self.cancel_btn)
        
        return bottom_bar
    
    def _setup_signals(self):
        self.play_btn.toggled.connect(self._on_play_toggled)
        self.stop_btn.clicked.connect(self._on_stop)
        self.play_fps_spin.valueChanged.connect(self._on_play_fps_changed)
        
        self.first_btn.clicked.connect(lambda: self._go_to_frame(0))
        self.last_btn.clicked.connect(lambda: self._go_to_frame(-1))
        self.prev_btn.clicked.connect(self._on_prev_frame)
        self.next_btn.clicked.connect(self._on_next_frame)
        self.prev_10_btn.clicked.connect(self._on_prev_10_frames)
        self.next_10_btn.clicked.connect(self._on_next_10_frames)
        
        self.delete_btn.clicked.connect(self._on_delete_current)
        self.delete_selected_btn.clicked.connect(self._on_delete_selected)
        self.duplicate_btn.clicked.connect(self._on_duplicate_frame)
        self.insert_btn.clicked.connect(self._on_insert_frame)
        self.move_up_btn.clicked.connect(self._on_move_up)
        self.move_down_btn.clicked.connect(self._on_move_down)
        self.batch_move_up_btn.clicked.connect(self._on_batch_move_up)
        self.batch_move_down_btn.clicked.connect(self._on_batch_move_down)
        self.reverse_btn.clicked.connect(self._on_reverse_frames)
        self.extract_btn.clicked.connect(self._on_extract_frame)
        self.extract_all_btn.clicked.connect(self._on_extract_all_frames)
        self.reset_btn.clicked.connect(self._on_reset)
        
        self.copy_btn.clicked.connect(self._on_copy_frames)
        self.cut_btn.clicked.connect(self._on_cut_frames)
        self.paste_btn.clicked.connect(self._on_paste_frames)
        
        self.select_all_btn.clicked.connect(self._on_select_all)
        self.deselect_all_btn.clicked.connect(self._on_deselect_all)
        self.invert_selection_btn.clicked.connect(self._on_invert_selection)
        
        self.zoom_in_btn.clicked.connect(self._on_zoom_in)
        self.zoom_out_btn.clicked.connect(self._on_zoom_out)
        self.zoom_fit_btn.clicked.connect(self._on_zoom_fit)
        self.zoom_100_btn.clicked.connect(self._on_zoom_100)
        
        self.frame_slider.valueChanged.connect(self._on_slider_changed)
        self.frame_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.frame_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.frame_list.customContextMenuRequested.connect(self._show_context_menu)
        
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        
        self.play_timer.timeout.connect(self._on_play_timeout)
    
    def _setup_keyboard_shortcuts(self):
        self.prev_shortcut = QAction(self)
        self.prev_shortcut.setShortcut(QKeySequence(Qt.Key_Left))
        self.prev_shortcut.triggered.connect(self._on_prev_frame)
        self.addAction(self.prev_shortcut)
        
        self.next_shortcut = QAction(self)
        self.next_shortcut.setShortcut(QKeySequence(Qt.Key_Right))
        self.next_shortcut.triggered.connect(self._on_next_frame)
        self.addAction(self.next_shortcut)
        
        self.home_shortcut = QAction(self)
        self.home_shortcut.setShortcut(QKeySequence(Qt.Key_Home))
        self.home_shortcut.triggered.connect(lambda: self._go_to_frame(0))
        self.addAction(self.home_shortcut)
        
        self.end_shortcut = QAction(self)
        self.end_shortcut.setShortcut(QKeySequence(Qt.Key_End))
        self.end_shortcut.triggered.connect(lambda: self._go_to_frame(-1))
        self.addAction(self.end_shortcut)
        
        self.del_shortcut = QAction(self)
        self.del_shortcut.setShortcut(QKeySequence(Qt.Key_Delete))
        self.del_shortcut.triggered.connect(self._on_delete_selected)
        self.addAction(self.del_shortcut)
        
        self.select_all_shortcut = QAction(self)
        self.select_all_shortcut.setShortcut(QKeySequence.SelectAll)
        self.select_all_shortcut.triggered.connect(self._on_select_all)
        self.addAction(self.select_all_shortcut)
        
        self.copy_shortcut = QAction(self)
        self.copy_shortcut.setShortcut(QKeySequence.Copy)
        self.copy_shortcut.triggered.connect(self._on_copy_frames)
        self.addAction(self.copy_shortcut)
        
        self.cut_shortcut = QAction(self)
        self.cut_shortcut.setShortcut(QKeySequence.Cut)
        self.cut_shortcut.triggered.connect(self._on_cut_frames)
        self.addAction(self.cut_shortcut)
        
        self.paste_shortcut = QAction(self)
        self.paste_shortcut.setShortcut(QKeySequence.Paste)
        self.paste_shortcut.triggered.connect(self._on_paste_frames)
        self.addAction(self.paste_shortcut)
        
        self.space_shortcut = QAction(self)
        self.space_shortcut.setShortcut(QKeySequence(Qt.Key_Space))
        self.space_shortcut.triggered.connect(self._on_toggle_play)
        self.addAction(self.space_shortcut)
    
    def _on_toggle_play(self):
        self.play_btn.toggle()
    
    def _on_prev_10_frames(self):
        new_index = max(0, self.current_index - 10)
        self._go_to_frame(new_index)
    
    def _on_next_10_frames(self):
        new_index = min(len(self.current_frames) - 1, self.current_index + 10)
        self._go_to_frame(new_index)
    
    def _on_batch_move_up(self):
        selected_items = self.frame_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "警告", "请先选择要移动的帧")
            return
        
        indices = sorted([item.data(Qt.UserRole) for item in selected_items])
        if indices[0] == 0:
            QMessageBox.information(self, "提示", "选中的帧已在顶部，无法上移")
            return
        
        for idx in indices:
            if idx > 0:
                (self.current_frames[idx], self.current_frames[idx - 1]) = (
                    self.current_frames[idx - 1], self.current_frames[idx]
                )
        
        old_indices = [idx - 1 for idx in indices if idx > 0]
        self._load_frames_to_list()
        for i in range(self.frame_list.count()):
            item = self.frame_list.item(i)
            if item.data(Qt.UserRole) in old_indices:
                item.setSelected(True)
        
        if self.current_index in indices:
            self.current_index -= 1
        elif self.current_index - 1 in indices:
            self.current_index += 1
        
        self._update_preview()
        self._update_status(f"已将 {len(indices)} 个选中帧上移")
    
    def _on_batch_move_down(self):
        selected_items = self.frame_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "警告", "请先选择要移动的帧")
            return
        
        indices = sorted([item.data(Qt.UserRole) for item in selected_items], reverse=True)
        if indices[0] >= len(self.current_frames) - 1:
            QMessageBox.information(self, "提示", "选中的帧已在底部，无法下移")
            return
        
        for idx in indices:
            if idx < len(self.current_frames) - 1:
                (self.current_frames[idx], self.current_frames[idx + 1]) = (
                    self.current_frames[idx + 1], self.current_frames[idx]
                )
        
        old_indices = [idx + 1 for idx in indices if idx < len(self.current_frames) - 1]
        self._load_frames_to_list()
        for i in range(self.frame_list.count()):
            item = self.frame_list.item(i)
            if item.data(Qt.UserRole) in old_indices:
                item.setSelected(True)
        
        if self.current_index in indices:
            self.current_index += 1
        elif self.current_index + 1 in indices:
            self.current_index -= 1
        
        self._update_preview()
        self._update_status(f"已将 {len(indices)} 个选中帧下移")
    
    def _on_copy_frames(self):
        selected_items = self.frame_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "警告", "请先选择要复制的帧")
            return
        
        indices = sorted([item.data(Qt.UserRole) for item in selected_items])
        self.clipboard_frames = [self.current_frames[idx].copy() for idx in indices]
        self.paste_btn.setEnabled(True)
        self._update_status(f"已复制 {len(self.clipboard_frames)} 帧到剪贴板")
    
    def _on_cut_frames(self):
        selected_items = self.frame_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "警告", "请先选择要剪切的帧")
            return
        
        if len(selected_items) >= len(self.current_frames):
            QMessageBox.warning(self, "警告", "不能剪切所有帧")
            return
        
        reply = QMessageBox.question(self, "确认剪切", f"确定剪切选中的 {len(selected_items)} 帧？",
                                      QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            indices = sorted([item.data(Qt.UserRole) for item in selected_items], reverse=True)
            self.clipboard_frames = []
            for idx in indices:
                self.clipboard_frames.insert(0, self.current_frames[idx].copy())
                del self.current_frames[idx]
            
            self.paste_btn.setEnabled(True)
            if self.current_index >= len(self.current_frames):
                self.current_index = len(self.current_frames) - 1
            self._load_frames_to_list()
            self._update_preview()
            self._update_status(f"已剪切 {len(self.clipboard_frames)} 帧到剪贴板")
    
    def _on_paste_frames(self):
        if not self.clipboard_frames:
            QMessageBox.warning(self, "警告", "剪贴板中没有帧")
            return
        
        paste_pos = self.current_index + 1
        for i, frame in enumerate(self.clipboard_frames):
            self.current_frames.insert(paste_pos + i, frame.copy())
        
        self._load_frames_to_list()
        self.current_index = paste_pos + len(self.clipboard_frames) - 1
        self._update_preview()
        self._update_status(f"已粘贴 {len(self.clipboard_frames)} 帧")
    
    def _on_extract_all_frames(self):
        if not self.current_frames:
            QMessageBox.warning(self, "警告", "没有可导出的帧")
            return
        
        folder = QFileDialog.getExistingDirectory(self, "选择导出文件夹")
        if not folder:
            return
        
        try:
            total = len(self.current_frames)
            for i, frame in enumerate(self.current_frames):
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                file_path = os.path.join(folder, f"frame_{i+1:04d}.png")
                Image.fromarray(frame_rgb).save(file_path)
                self._update_status(f"导出中... {i+1}/{total}")
                QApplication.processEvents()
            
            QMessageBox.information(self, "成功", f"已导出 {total} 帧到:\n{folder}")
            self._update_status(f"已导出 {total} 帧")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {str(e)}")
    
    def _setup_context_menu(self):
        self.context_menu = QMenu(self)
        self.context_menu.setStyleSheet("""
            QMenu {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                padding: 5px;
                min-width: 180px;
            }
            QMenu::item {
                padding: 8px 30px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #0078d4;
                color: white;
            }
            QMenu::separator {
                height: 1px;
                background-color: #dee2e6;
                margin: 5px 0;
            }
        """)
        
        delete_action = QAction("🗑 删除选中帧", self)
        delete_action.triggered.connect(self._on_delete_selected)
        self.context_menu.addAction(delete_action)
        
        duplicate_action = QAction("📋 复制选中帧", self)
        duplicate_action.triggered.connect(self._on_duplicate_selected)
        self.context_menu.addAction(duplicate_action)
        
        self.context_menu.addSeparator()
        
        copy_action = QAction("📋 复制到剪贴板", self)
        copy_action.triggered.connect(self._on_copy_frames)
        self.context_menu.addAction(copy_action)
        
        cut_action = QAction("✂️ 剪切到剪贴板", self)
        cut_action.triggered.connect(self._on_cut_frames)
        self.context_menu.addAction(cut_action)
        
        paste_action = QAction("📌 粘贴", self)
        paste_action.triggered.connect(self._on_paste_frames)
        self.context_menu.addAction(paste_action)
        
        self.context_menu.addSeparator()
        
        move_up_action = QAction("↑ 上移选中帧", self)
        move_up_action.triggered.connect(self._on_batch_move_up)
        self.context_menu.addAction(move_up_action)
        
        move_down_action = QAction("↓ 下移选中帧", self)
        move_down_action.triggered.connect(self._on_batch_move_down)
        self.context_menu.addAction(move_down_action)
        
        self.context_menu.addSeparator()
        
        select_all_action = QAction("☑ 全选 (Ctrl+A)", self)
        select_all_action.triggered.connect(self._on_select_all)
        self.context_menu.addAction(select_all_action)
        
        invert_action = QAction("🔄 反选", self)
        invert_action.triggered.connect(self._on_invert_selection)
        self.context_menu.addAction(invert_action)
        
        self.context_menu.addSeparator()
        
        extract_action = QAction("💾 导出当前帧为图片", self)
        extract_action.triggered.connect(self._on_extract_frame)
        self.context_menu.addAction(extract_action)
        
        extract_all_action = QAction("📁 导出所有帧", self)
        extract_all_action.triggered.connect(self._on_extract_all_frames)
        self.context_menu.addAction(extract_all_action)
        
        self.context_menu.addSeparator()
        
        reverse_action = QAction("🔄 反转所有帧顺序", self)
        reverse_action.triggered.connect(self._on_reverse_frames)
        self.context_menu.addAction(reverse_action)
        
        insert_blank_action = QAction("➕ 插入空白帧", self)
        insert_blank_action.triggered.connect(self._on_insert_frame)
        self.context_menu.addAction(insert_blank_action)
    
    def _show_context_menu(self, position):
        self.context_menu.exec(self.frame_list.viewport().mapToGlobal(position))
    
    def _load_frames_to_list(self):
        self.frame_list.clear()
        for i, frame in enumerate(self.current_frames):
            try:
                h, w = frame.shape[:2]
                thumb_w = 80
                thumb_h = int(h * thumb_w / w)
                if thumb_h > 60:
                    thumb_h = 60
                    thumb_w = int(w * thumb_h / h)
                frame_resized = cv2.resize(frame, (thumb_w, thumb_h))
                frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
                bytes_line = 3 * thumb_w
                qimg = QImage(frame_rgb.data, thumb_w, thumb_h, bytes_line, QImage.Format_RGB888)
                
                item = QListWidgetItem()
                item.setIcon(QIcon(QPixmap.fromImage(qimg)))
                item.setText(f"帧 {i+1}  |  {w}×{h}")
                item.setData(Qt.UserRole, i)
                self.frame_list.addItem(item)
            except Exception as e:
                item = QListWidgetItem()
                item.setText(f"帧 {i+1}")
                item.setData(Qt.UserRole, i)
                self.frame_list.addItem(item)
                print(f"创建缩略图失败: {e}")
        self._update_stats()
    
    def _update_stats(self):
        total = len(self.current_frames)
        selected = len(self.frame_list.selectedItems())
        
        self.frame_count_label.setText(f"{total} 帧")
        self.total_frames_stat.setText(str(total))
        self.selected_stat.setText(str(selected))
        self.selected_count_label.setText(f"已选中: {selected}")
        
        self.frame_slider.setMaximum(max(0, total - 1))
        
        if self.current_frames and self.current_index < len(self.current_frames):
            self.current_frame_num.setText(f"{self.current_index + 1} / {total}")
            h, w = self.current_frames[self.current_index].shape[:2]
            self.frame_size_label.setText(f"{w} × {h}")
            
            self.frame_info_label.setText(f"📄 帧: {self.current_index + 1}/{total}")
            
            try:
                estimated_kb = GIFSizeEstimator.estimate_size(
                    total, w, h, self.play_fps_spin.value(), 256, 80
                )
                if estimated_kb < 1024:
                    size_text = f"{estimated_kb} KB"
                else:
                    size_text = f"{estimated_kb/1024:.1f} MB"
                self.file_size_label.setText(f"💾 预估: {size_text}")
            except:
                self.file_size_label.setText(f"💾 尺寸: {w}×{h}")
    
    def _update_preview(self):
        if not self.current_frames or self.current_index >= len(self.current_frames):
            return
        try:
            frame = self.current_frames[self.current_index]
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = frame_rgb.shape[:2]
            qimg = QImage(frame_rgb.data, w, h, 3 * w, QImage.Format_RGB888)
            self.original_pixmap = QPixmap.fromImage(qimg)
            
            self._update_scaled_preview()
            
            self.frame_slider.blockSignals(True)
            self.frame_slider.setValue(self.current_index)
            self.frame_slider.blockSignals(False)
            self.frame_counter.setText(f"{self.current_index + 1} / {len(self.current_frames)}")
            
            self.current_frame_num.setText(f"{self.current_index + 1} / {len(self.current_frames)}")
            self.frame_size_label.setText(f"{w} × {h}")
            
            total = len(self.current_frames)
            self.frame_info_label.setText(f"📄 帧: {self.current_index + 1}/{total}")
            
            try:
                estimated_kb = GIFSizeEstimator.estimate_size(
                    total, w, h, self.play_fps_spin.value(), 256, 80
                )
                if estimated_kb < 1024:
                    size_text = f"{estimated_kb} KB"
                else:
                    size_text = f"{estimated_kb/1024:.1f} MB"
                self.file_size_label.setText(f"💾 预估: {size_text}")
            except:
                self.file_size_label.setText(f"💾 尺寸: {w}×{h}")
            
            for i in range(self.frame_list.count()):
                item = self.frame_list.item(i)
                if item.data(Qt.UserRole) == self.current_index:
                    item.setSelected(True)
                    self.frame_list.scrollToItem(item)
                elif len(self.frame_list.selectedItems()) <= 1:
                    item.setSelected(False)
        except Exception as e:
            print(f"更新预览出错: {e}")
    
    def _update_scaled_preview(self):
        if not hasattr(self, 'original_pixmap') or self.original_pixmap.isNull():
            return
        
        viewport_size = self.preview_scroll.viewport().size()
        
        if self.zoom_level == 0:
            scaled = self.original_pixmap.scaled(
                viewport_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            scaled = self.original_pixmap.scaled(
                self.original_pixmap.size() * self.zoom_level,
                Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        self.preview_label.setPixmap(scaled)
        self.preview_label.resize(scaled.size())
    
    def _update_status(self, message):
        if hasattr(self, 'status_label') and self.status_label:
            self.status_label.setText(message)
            QTimer.singleShot(3000, lambda: self.status_label.setText("就绪") if self.status_label and self.status_label.text() == message else None)
    
    def _go_to_frame(self, target):
        if not self.current_frames:
            return
        if target == 0:
            self.current_index = 0
        elif target == -1:
            self.current_index = len(self.current_frames) - 1
        else:
            self.current_index = max(0, min(target, len(self.current_frames) - 1))
        self._update_preview()
    
    def _on_prev_frame(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._update_preview()
    
    def _on_next_frame(self):
        if self.current_index < len(self.current_frames) - 1:
            self.current_index += 1
            self._update_preview()
    
    def _on_play_toggled(self, checked):
        if checked:
            self.is_playing = True
            self.play_btn.setText("⏸ 暂停")
            interval = int(1000 / self.play_fps_spin.value())
            self.play_timer.start(interval)
        else:
            self.is_playing = False
            self.play_btn.setText("▶ 播放")
            self.play_timer.stop()
    
    def _on_play_fps_changed(self, value):
        if self.is_playing:
            self.play_btn.setChecked(False)
            self.play_btn.setChecked(True)
    
    def _on_stop(self):
        self.play_btn.setChecked(False)
        self.current_index = 0
        self._update_preview()
    
    def _on_play_timeout(self):
        if self.current_frames:
            self.current_index = (self.current_index + 1) % len(self.current_frames)
            self._update_preview()
    
    def _on_delete_current(self):
        if len(self.current_frames) <= 1:
            QMessageBox.warning(self, "警告", "至少保留一帧")
            return
        
        reply = QMessageBox.question(self, "确认删除", f"确定删除第 {self.current_index + 1} 帧？",
                                      QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            del self.current_frames[self.current_index]
            if self.current_index >= len(self.current_frames):
                self.current_index = len(self.current_frames) - 1
            self._load_frames_to_list()
            self._update_preview()
            self._update_status(f"已删除第 {self.current_index + 1} 帧")
    
    def _on_delete_selected(self):
        selected_items = self.frame_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "警告", "请先选择要删除的帧")
            return
        
        if len(selected_items) >= len(self.current_frames):
            QMessageBox.warning(self, "警告", "不能删除所有帧")
            return
        
        reply = QMessageBox.question(self, "确认删除", f"确定删除选中的 {len(selected_items)} 帧？",
                                      QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            indices = sorted([item.data(Qt.UserRole) for item in selected_items], reverse=True)
            for idx in indices:
                if idx < len(self.current_frames):
                    del self.current_frames[idx]
            
            if self.current_index >= len(self.current_frames):
                self.current_index = len(self.current_frames) - 1
            self._load_frames_to_list()
            self._update_preview()
            self._update_status(f"已删除 {len(indices)} 帧")
    
    def _on_move_up(self):
        if self.current_index > 0:
            (self.current_frames[self.current_index], 
             self.current_frames[self.current_index - 1]) = (
                self.current_frames[self.current_index - 1],
                self.current_frames[self.current_index]
            )
            self.current_index -= 1
            self._load_frames_to_list()
            self._update_preview()
    
    def _on_move_down(self):
        if self.current_index < len(self.current_frames) - 1:
            (self.current_frames[self.current_index], 
             self.current_frames[self.current_index + 1]) = (
                self.current_frames[self.current_index + 1],
                self.current_frames[self.current_index]
            )
            self.current_index += 1
            self._load_frames_to_list()
            self._update_preview()
    
    def _on_duplicate_frame(self):
        if not self.current_frames:
            return
        
        frame_copy = self.current_frames[self.current_index].copy()
        self.current_frames.insert(self.current_index + 1, frame_copy)
        self._load_frames_to_list()
        self.current_index = min(self.current_index + 1, len(self.current_frames) - 1)
        self._update_preview()
        self._update_status(f"已复制第 {self.current_index} 帧")
    
    def _on_duplicate_selected(self):
        selected_items = self.frame_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "警告", "请先选择要复制的帧")
            return
        
        indices = sorted([item.data(Qt.UserRole) for item in selected_items])
        for idx in reversed(indices):
            frame_copy = self.current_frames[idx].copy()
            self.current_frames.insert(idx + 1, frame_copy)
        
        self._load_frames_to_list()
        self._update_preview()
        self._update_status(f"已复制 {len(indices)} 帧")
    
    def _on_insert_frame(self):
        if not self.current_frames:
            return
        
        h, w = self.current_frames[0].shape[:2]
        blank_frame = np.full((h, w, 3), 128, dtype=np.uint8)
        
        self.current_frames.insert(self.current_index + 1, blank_frame)
        self._load_frames_to_list()
        self.current_index = min(self.current_index + 1, len(self.current_frames) - 1)
        self._update_preview()
        self._update_status(f"已在第 {self.current_index} 帧后插入空白帧")
    
    def _on_reverse_frames(self):
        self.current_frames.reverse()
        self.current_index = len(self.current_frames) - 1 - self.current_index
        self._load_frames_to_list()
        self._update_preview()
        self._update_status("已反转所有帧顺序")
    
    def _on_extract_frame(self):
        if not self.current_frames:
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存图片", "", "PNG图片 (*.png);;JPEG图片 (*.jpg)"
        )
        if file_path:
            frame = self.current_frames[self.current_index]
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            Image.fromarray(frame_rgb).save(file_path)
            QMessageBox.information(self, "成功", f"已保存帧 {self.current_index + 1}")
    
    def _on_select_all(self):
        self.frame_list.selectAll()
    
    def _on_deselect_all(self):
        self.frame_list.clearSelection()
    
    def _on_invert_selection(self):
        for i in range(self.frame_list.count()):
            item = self.frame_list.item(i)
            item.setSelected(not item.isSelected())
    
    def _on_zoom_in(self):
        if self.zoom_level == 0:
            self.zoom_level = 1.0
        self.zoom_level = min(self.zoom_level * 1.25, 3.0)
        self._update_scaled_preview()
    
    def _on_zoom_out(self):
        if self.zoom_level == 0:
            self.zoom_level = 1.0
        self.zoom_level = max(self.zoom_level / 1.25, 0.25)
        self._update_scaled_preview()
    
    def _on_zoom_fit(self):
        self.zoom_level = 0
        self._update_scaled_preview()
    
    def _on_zoom_100(self):
        self.zoom_level = 1.0
        self._update_scaled_preview()
    
    def _on_reset(self):
        if QMessageBox.question(self, "确认", "放弃所有编辑？", 
                                 QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.current_frames = self.frames.copy()
            self.current_index = 0
            self.zoom_level = 0
            self.clipboard_frames = []
            self.paste_btn.setEnabled(False)
            self._load_frames_to_list()
            self._update_preview()
            self._update_status("已重置所有编辑")
    
    def _on_slider_changed(self, value):
        if 0 <= value < len(self.current_frames):
            self.current_index = value
            self._update_preview()
    
    def _on_selection_changed(self):
        selected = len(self.frame_list.selectedItems())
        self.selected_stat.setText(str(selected))
        self.selected_count_label.setText(f"已选中: {selected}")
    
    def _on_item_double_clicked(self, item):
        idx = item.data(Qt.UserRole)
        if 0 <= idx < len(self.current_frames):
            self.current_index = idx
            self._update_preview()
    
    def get_edited_frames(self):
        return self.current_frames
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.zoom_level == 0:
            self._update_scaled_preview()
    
    def closeEvent(self, event):
        self.play_timer.stop()
        event.accept()


# ==================== 播放器窗口 ====================
class GIFPlayerWindow(QMainWindow):
    def __init__(self, frames, fps=10, parent=None):
        super().__init__(parent)
        self.frames = frames
        self.fps = fps
        self.current_index = 0
        self.play_timer = QTimer()
        self.is_playing = False
        
        self.setWindowTitle("GIF播放器")
        self.setMinimumSize(640, 540)
        
        self._setup_ui()
        self._setup_signals()
        self._update_preview()
    
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
        preview_frame = QFrame()
        preview_frame.setStyleSheet("QFrame { background-color: #2d2d2d; border-radius: 5px; }")
        preview_layout = QVBoxLayout(preview_frame)
        
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(500, 400)
        
        scroll = QScrollArea()
        scroll.setWidget(self.preview_label)
        scroll.setWidgetResizable(True)
        preview_layout.addWidget(scroll)
        
        layout.addWidget(preview_frame)
        
        control_bar = QWidget()
        control_layout = QHBoxLayout(control_bar)
        control_layout.setSpacing(10)
        
        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.setCheckable(True)
        self.play_btn.setFixedWidth(80)
        control_layout.addWidget(self.play_btn)
        
        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setFixedWidth(80)
        control_layout.addWidget(self.stop_btn)
        
        control_layout.addStretch()
        
        control_layout.addWidget(QLabel("速度:"))
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "1.0x", "1.5x", "2.0x"])
        self.speed_combo.setCurrentIndex(1)
        self.speed_combo.setFixedWidth(70)
        control_layout.addWidget(self.speed_combo)
        
        layout.addWidget(control_bar)
        
        progress_bar = QWidget()
        progress_layout = QHBoxLayout(progress_bar)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        
        progress_layout.addWidget(QLabel("帧:"))
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(max(0, len(self.frames) - 1))
        progress_layout.addWidget(self.frame_slider)
        
        self.frame_label = QLabel(f"0/{len(self.frames)}")
        self.frame_label.setMinimumWidth(60)
        progress_layout.addWidget(self.frame_label)
        
        layout.addWidget(progress_bar)
        
        info_bar = QWidget()
        info_layout = QHBoxLayout(info_bar)
        info_layout.setContentsMargins(0, 5, 0, 0)
        info_layout.addStretch()
        self.info_label = QLabel(f"总帧数: {len(self.frames)}  |  FPS: {self.fps}")
        info_layout.addWidget(self.info_label)
        layout.addWidget(info_bar)
    
    def _setup_signals(self):
        self.play_btn.toggled.connect(self._on_play_toggled)
        self.stop_btn.clicked.connect(self._on_stop)
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        self.frame_slider.valueChanged.connect(self._on_slider_changed)
        self.play_timer.timeout.connect(self._on_play_timeout)
    
    def _update_preview(self):
        if not self.frames or self.current_index >= len(self.frames):
            return
        try:
            frame = self.frames[self.current_index]
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            else:
                frame_rgb = frame
            h, w = frame_rgb.shape[:2]
            qimg = QImage(frame_rgb.data, w, h, 3 * w, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)
            
            label_size = self.preview_label.size()
            if label_size.width() > 0 and label_size.height() > 0:
                scaled = pixmap.scaled(label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.preview_label.setPixmap(scaled)
            
            self.frame_slider.blockSignals(True)
            self.frame_slider.setValue(self.current_index)
            self.frame_slider.blockSignals(False)
            self.frame_label.setText(f"{self.current_index + 1}/{len(self.frames)}")
        except Exception as e:
            print(f"预览更新出错: {e}")
    
    def _on_play_toggled(self, checked):
        if checked:
            self.is_playing = True
            self.play_btn.setText("⏸ 暂停")
            speed = float(self.speed_combo.currentText().replace('x', ''))
            interval = int(1000 / (self.fps * speed))
            self.play_timer.start(interval)
        else:
            self.is_playing = False
            self.play_btn.setText("▶ 播放")
            self.play_timer.stop()
    
    def _on_stop(self):
        self.play_btn.setChecked(False)
        self.current_index = 0
        self._update_preview()
    
    def _on_play_timeout(self):
        if self.frames:
            self.current_index = (self.current_index + 1) % len(self.frames)
            self._update_preview()
    
    def _on_speed_changed(self, idx):
        if self.is_playing:
            self.play_btn.setChecked(False)
            self.play_btn.setChecked(True)
    
    def _on_slider_changed(self, value):
        if 0 <= value < len(self.frames):
            self.current_index = value
            self._update_preview()
    
    def closeEvent(self, event):
        self.play_timer.stop()
        event.accept()


# ==================== GIF编码线程 ====================
class GIFEncodingThread(QThread):
    progress_updated = Signal(int)
    status_updated = Signal(str)
    encoding_finished = Signal(str)
    encoding_error = Signal(str)
    size_estimate_updated = Signal(int, int)
    actual_size_signal = Signal(int, int)
    
    def __init__(self, frames, output_path, fps, scale_percent, quality, colors, 
                 enable_size_control=False, target_size_kb=1024, size_control_mode="auto",
                 min_scale=30, min_colors=32):
        super().__init__()
        self.frames = frames
        self.output_path = output_path
        self.fps = fps
        self.scale_percent = scale_percent
        self.quality = quality
        self.colors = colors
        self.enable_size_control = enable_size_control
        self.target_size_kb = target_size_kb
        self.size_control_mode = size_control_mode
        self.min_scale = min_scale
        self.min_colors = min_colors
        self.is_running = True
        
    def run(self):
        try:
            if not self.frames:
                self.encoding_error.emit("没有捕获到任何帧")
                return
            
            sample_frame = self.frames[0]
            original_h, original_w = sample_frame.shape[:2]
            
            actual_fps = self.fps
            actual_scale = self.scale_percent
            actual_quality = self.quality
            actual_colors = self.colors
            reached_target = False
            
            if self.enable_size_control:
                self.status_updated.emit("正在分析文件大小...")
                log_manager.info("开始文件大小优化分析")
                
                current_config = {
                    'fps': actual_fps,
                    'scale': actual_scale,
                    'quality': actual_quality,
                    'colors': actual_colors
                }
                
                best_params, estimated, reached_target = GIFSizeEstimator.find_optimal_params(
                    len(self.frames), original_w, original_h,
                    self.target_size_kb, current_config,
                    min_scale=self.min_scale,
                    min_colors=self.min_colors,
                    mode=self.size_control_mode
                )
                
                actual_fps = best_params.get('fps', actual_fps)
                actual_scale = best_params.get('scale', actual_scale)
                actual_quality = best_params.get('quality', actual_quality)
                actual_colors = best_params.get('colors', actual_colors)
                
                self.size_estimate_updated.emit(estimated, self.target_size_kb)
                self.status_updated.emit(
                    f"文件大小优化: 目标 {self.target_size_kb}KB, "
                    f"估计 {estimated}KB (FPS:{actual_fps}, "
                    f"缩放:{actual_scale}%, 颜色:{actual_colors}, 质量:{actual_quality}%)"
                )
            
            self.status_updated.emit("正在处理图像...")
            log_manager.info(f"开始处理 {len(self.frames)} 帧图像")
            processed = []
            total = len(self.frames)
            
            for i, frame in enumerate(self.frames):
                if not self.is_running:
                    return
                try:
                    if actual_scale != 100:
                        w = int(frame.shape[1] * actual_scale / 100)
                        h = int(frame.shape[0] * actual_scale / 100)
                        w = max(1, w)
                        h = max(1, h)
                        frame = cv2.resize(frame, (w, h))
                    if len(frame.shape) == 3 and frame.shape[2] == 3:
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    else:
                        frame_rgb = frame
                    if not frame_rgb.flags['C_CONTIGUOUS']:
                        frame_rgb = np.ascontiguousarray(frame_rgb)
                    processed.append(frame_rgb)
                except Exception as e:
                    log_manager.error(f"处理帧 {i} 出错: {e}")
                    continue
                progress = int((i + 1) / total * 40)
                self.progress_updated.emit(progress)
            
            if not processed:
                self.encoding_error.emit("没有有效帧")
                return
            
            self.status_updated.emit("正在生成GIF...")
            log_manager.info("正在生成GIF文件")
            pil_frames = []
            for frame in processed:
                try:
                    pil_frames.append(Image.fromarray(frame))
                except Exception as e:
                    log_manager.error(f"PIL转换出错: {e}")
                    continue
            
            if not pil_frames:
                self.encoding_error.emit("无法创建PIL图像")
                return
            
            duration = int(1000 / actual_fps)
            
            if actual_colors < 256:
                self.status_updated.emit("正在优化颜色...")
                log_manager.info(f"正在优化颜色到 {actual_colors} 色")
                paletted = []
                for i, frame in enumerate(pil_frames):
                    if not self.is_running:
                        return
                    try:
                        paletted.append(frame.convert('P', palette=Image.ADAPTIVE, colors=actual_colors))
                    except:
                        paletted.append(frame)
                    progress = 40 + int((i + 1) / len(pil_frames) * 40)
                    self.progress_updated.emit(progress)
                pil_frames = paletted
            
            try:
                save_kwargs = {
                    'save_all': True,
                    'append_images': pil_frames[1:],
                    'duration': duration,
                    'loop': 0,
                    'optimize': True
                }
                
                if actual_quality < 100:
                    save_kwargs['quality'] = actual_quality
                
                pil_frames[0].save(self.output_path, **save_kwargs)
                
                actual_size_bytes = os.path.getsize(self.output_path)
                actual_size_kb = actual_size_bytes / 1024
                
                self.progress_updated.emit(100)
                
                log_manager.success(f"GIF生成完成: {self.output_path}")
                log_manager.info(f"实际大小: {actual_size_kb:.2f} KB ({actual_size_kb/1024:.2f} MB)")
                log_manager.info(f"目标大小: {self.target_size_kb} KB")
                log_manager.info(f"达成率: {(actual_size_kb/self.target_size_kb*100):.1f}%")
                log_manager.info(f"最终参数: FPS={actual_fps}, 缩放={actual_scale}%, "
                                f"颜色={actual_colors}, 质量={actual_quality}%")
                
                self.actual_size_signal.emit(int(actual_size_kb), self.target_size_kb)
                
                if self.enable_size_control:
                    if actual_size_kb <= self.target_size_kb:
                        self.status_updated.emit(f"✓ 完成！实际大小: {actual_size_kb:.1f}KB ≤ 目标 {self.target_size_kb}KB")
                        log_manager.success(f"实际大小 {actual_size_kb:.1f}KB 符合目标要求")
                    else:
                        self.status_updated.emit(f"⚠ 完成！实际大小: {actual_size_kb:.1f}KB > 目标 {self.target_size_kb}KB (超出{(actual_size_kb/self.target_size_kb*100-100):.0f}%)")
                        log_manager.warning(f"实际大小超出目标 {(actual_size_kb/self.target_size_kb*100-100):.0f}%")
                else:
                    self.status_updated.emit(f"完成！大小: {actual_size_kb:.1f}KB")
                    
                self.encoding_finished.emit(self.output_path)
            except Exception as e:
                log_manager.error(f"保存GIF失败: {str(e)}")
                self.encoding_error.emit(f"保存失败: {str(e)}")
        except Exception as e:
            log_manager.error(f"编码失败: {str(e)}")
            self.encoding_error.emit(f"编码失败: {str(e)}")
            traceback.print_exc()
    
    def stop(self):
        self.is_running = False


# ==================== 屏幕捕获线程 ====================
class ScreenCaptureThread(QThread):
    frame_captured = Signal(np.ndarray)
    capture_finished = Signal()
    capture_error = Signal(str)
    status_updated = Signal(str)
    
    def __init__(self, capture_rect):
        super().__init__()
        self.capture_rect = capture_rect
        self.is_running = False
        self.paused = False
        self.frames = []
        self.capture_event = Event()
        self.last_capture_time = 0
        self.target_fps = 15
        
    def run(self):
        try:
            self.is_running = True
            self.capture_event.set()
            screen = QApplication.primaryScreen()
            if not screen:
                self.capture_error.emit("无法获取屏幕")
                return
            frame_interval = 1.0 / self.target_fps
            
            while self.is_running:
                if self.paused:
                    self.msleep(100)
                    continue
                if not self.capture_event.is_set():
                    break
                try:
                    current_time = time.time()
                    if current_time - self.last_capture_time < frame_interval:
                        self.msleep(1)
                        continue
                    
                    pixmap = screen.grabWindow(0, 
                                                self.capture_rect.x(),
                                                self.capture_rect.y(),
                                                self.capture_rect.width(),
                                                self.capture_rect.height())
                    qimage = pixmap.toImage()
                    if qimage.isNull():
                        self.msleep(10)
                        continue
                    
                    w, h = qimage.width(), qimage.height()
                    if w <= 0 or h <= 0:
                        self.msleep(10)
                        continue
                    
                    if qimage.format() in (QImage.Format_ARGB32, QImage.Format_RGB32):
                        arr = np.array(qimage.constBits(), copy=True).reshape(h, w, 4)
                        frame = arr[:, :, :3].copy()
                    elif qimage.format() == QImage.Format_RGB888:
                        arr = np.array(qimage.constBits(), copy=True).reshape(h, w, 3)
                        frame = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                    elif qimage.format() == QImage.Format_RGBA8888:
                        arr = np.array(qimage.constBits(), copy=True).reshape(h, w, 4)
                        frame = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
                    else:
                        qimage_rgb = qimage.convertToFormat(QImage.Format_RGB888)
                        arr = np.array(qimage_rgb.constBits(), copy=True).reshape(h, w, 3)
                        frame = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                    
                    frame = np.ascontiguousarray(frame)
                    self.frames.append(frame)
                    self.frame_captured.emit(frame)
                    self.last_capture_time = current_time
                except Exception as e:
                    print(f"捕获单帧出错: {e}")
                    self.msleep(10)
        except Exception as e:
            self.capture_error.emit(f"捕获失败: {str(e)}")
        finally:
            self.capture_finished.emit()
    
    def stop(self):
        self.is_running = False
        self.capture_event.clear()
    
    def pause(self):
        self.paused = True
    
    def resume(self):
        self.paused = False
    
    def get_frames(self):
        return self.frames.copy()
    
    def clear_frames(self):
        self.frames.clear()
    
    def set_target_fps(self, fps):
        self.target_fps = max(1, min(fps, 30))


# ==================== 区域选择窗口 ====================
class RegionSelectionWindow(QWidget):
    region_selected = Signal(QRect)
    
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
        self.screen_geometry = self._get_virtual_desktop_geometry()
        self.setGeometry(self.screen_geometry)
        
        self.start_point = None
        self.end_point = None
        self.is_selecting = False
        self.setCursor(QCursor(Qt.CrossCursor))
        
        self.mask_color = QColor(0, 0, 0, 100)
        self.selection_color = QColor(0, 120, 215, 50)
        self.border_color = QColor(0, 120, 215)
        self.show_instructions = True
        
    def _get_virtual_desktop_geometry(self) -> QRect:
        geometry = QRect()
        for screen in QApplication.screens():
            geometry = geometry.united(screen.geometry())
        return geometry
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), self.mask_color)
        
        if self.start_point and self.end_point:
            rect = QRect(self.start_point, self.end_point).normalized()
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(rect, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(QPen(self.border_color, 2))
            painter.setBrush(QBrush(self.selection_color))
            painter.drawRect(rect)
            
            if rect.width() > 50 and rect.height() > 30:
                info = f"{rect.width()} × {rect.height()}"
                painter.setPen(QPen(Qt.white))
                painter.setFont(QFont("Microsoft YaHei", 9))
                painter.drawText(rect.topLeft() + QPoint(5, -5), info)
        
        if self.show_instructions and not self.is_selecting:
            painter.setPen(QPen(Qt.white))
            painter.setFont(QFont("Microsoft YaHei", 12))
            instructions = "拖动鼠标选择录制区域 | 按 ESC 取消"
            text_rect = painter.fontMetrics().boundingRect(instructions)
            text_rect.moveCenter(self.rect().center())
            painter.drawText(text_rect, instructions)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_point = event.position().toPoint()
            self.end_point = self.start_point
            self.is_selecting = True
            self.show_instructions = False
            self.update()
    
    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.end_point = event.position().toPoint()
            self.update()
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_selecting:
            self.end_point = event.position().toPoint()
            self.is_selecting = False
            rect = QRect(self.start_point, self.end_point).normalized()
            if rect.width() > 10 and rect.height() > 10:
                self.region_selected.emit(rect)
            self.close()
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
    
    def showEvent(self, event):
        super().showEvent(event)
        self.show_instructions = True
        self.start_point = None
        self.end_point = None
        self.is_selecting = False
        self.update()


# ==================== 主窗口类 ====================
class ScreenToGIFMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        program_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.config_file = os.path.join(program_dir, "screentogif_config.json")
        self.config = AppConfig.load_from_file(self.config_file)
        self._ensure_output_directory()
        
        self.selection_window = None
        self.capture_thread = None
        self.encode_thread = None
        self.capture_rect = None
        self.captured_frames = []
        self.preview_timer = QTimer()
        self.preview_index = 0
        self.is_recording = False
        self.player_window = None
        self.editor_dialog = None
        self.log_widget = None
        self.main_splitter = None
        self.file_manager_preview = None
        self.history_preview = None
        
        self._setup_ui()
        self._load_config()
        self._check_icon()
        self._setup_signals()
        
        if self.log_widget:
            log_manager.register_widget(self.log_widget)
        log_manager.info(f"程序启动 - {ProjectInfo.NAME} {ProjectInfo.VERSION}")
        
        if hasattr(self.config, 'window_x') and hasattr(self.config, 'window_y'):
            self.move(self.config.window_x, self.config.window_y)
        if hasattr(self.config, 'window_width') and hasattr(self.config, 'window_height'):
            self.resize(self.config.window_width, self.config.window_height)
        
        if hasattr(self.config, 'splitter_sizes') and self.config.splitter_sizes and self.main_splitter:
            self.main_splitter.setSizes(self.config.splitter_sizes)
    
    def _ensure_output_directory(self):
        program_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        default_output = os.path.join(program_dir, "ScreenToGIF_Recordings")
        if not self.config.output_directory:
            self.config.output_directory = default_output
        else:
            try:
                rel_path = os.path.relpath(self.config.output_directory, program_dir)
                if rel_path.startswith('..') or os.path.isabs(rel_path):
                    self.config.output_directory = default_output
            except:
                self.config.output_directory = default_output
        os.makedirs(self.config.output_directory, exist_ok=True)
    
    def _setup_ui(self):
        self.setWindowTitle(f"{ProjectInfo.NAME} {ProjectInfo.VERSION}")
        self.setMinimumSize(900, 650)
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        self._create_menu_bar()
        
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setHandleWidth(4)
        self.main_splitter.setChildrenCollapsible(False)
        
        left_panel = QWidget()
        left_panel.setMinimumWidth(280)
        left_panel.setMaximumWidth(500)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(10)
        left_layout.setContentsMargins(0, 0, 5, 0)
        
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ddd;
                border-radius: 6px;
                background-color: white;
            }
            QTabBar::tab {
                padding: 6px 12px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                background-color: #f0f0f0;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #0078d4;
                color: white;
            }
            QTabBar::tab:hover:!selected {
                background-color: #e0e0e0;
            }
        """)
        
        # === 标签页1：录制与进度 ===
        tab_record = QWidget()
        record_layout = QVBoxLayout(tab_record)
        record_layout.setSpacing(10)
        record_layout.setContentsMargins(5, 5, 5, 5)
        
        control_group = QGroupBox("🎮 录制控制")
        control_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        control_layout = QVBoxLayout(control_group)
        control_layout.setSpacing(8)
        
        self.select_region_btn = QPushButton("🎯 选择录制区域")
        self.select_region_btn.setMinimumHeight(40)
        self.select_region_btn.setObjectName("primary_button")
        control_layout.addWidget(self.select_region_btn)
        
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.start_capture_btn = QPushButton("▶ 开始录制")
        self.start_capture_btn.setMinimumHeight(35)
        self.start_capture_btn.setEnabled(False)
        self.start_capture_btn.setObjectName("success_button")
        btn_row.addWidget(self.start_capture_btn)
        
        self.stop_capture_btn = QPushButton("⏹ 停止录制")
        self.stop_capture_btn.setMinimumHeight(35)
        self.stop_capture_btn.setEnabled(False)
        self.stop_capture_btn.setObjectName("danger_button")
        btn_row.addWidget(self.stop_capture_btn)
        control_layout.addLayout(btn_row)
        
        info_frame = QFrame()
        info_frame.setStyleSheet("QFrame { background-color: #f0f0f0; border-radius: 5px; }")
        info_layout = QHBoxLayout(info_frame)
        info_layout.setContentsMargins(8, 4, 8, 4)
        self.region_info_label = QLabel("未选择区域")
        self.region_info_label.setAlignment(Qt.AlignCenter)
        info_layout.addWidget(self.region_info_label)
        control_layout.addWidget(info_frame)
        
        record_layout.addWidget(control_group)
        
        post_group = QGroupBox("🎬 编辑操作")
        post_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        post_layout = QGridLayout(post_group)
        post_layout.setSpacing(8)
        
        self.play_btn = QPushButton("▶ 播放预览")
        self.play_btn.setEnabled(False)
        self.play_btn.setObjectName("info_button")
        post_layout.addWidget(self.play_btn, 0, 0)
        
        self.edit_btn = QPushButton("✎ 编辑帧")
        self.edit_btn.setEnabled(False)
        self.edit_btn.setObjectName("warning_button")
        post_layout.addWidget(self.edit_btn, 0, 1)
        
        self.generate_gif_btn = QPushButton("🎨 导出GIF")
        self.generate_gif_btn.setEnabled(False)
        self.generate_gif_btn.setMinimumHeight(38)
        self.generate_gif_btn.setObjectName("primary_button")
        post_layout.addWidget(self.generate_gif_btn, 1, 0, 1, 2)
        
        record_layout.addWidget(post_group)
        
        progress_group = QGroupBox("📊 处理进度")
        progress_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        progress_group_layout = QVBoxLayout(progress_group)
        
        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setMinimumHeight(28)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("background-color: #e9ecef; border-radius: 3px; padding: 4px;")
        progress_group_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(True)
        progress_group_layout.addWidget(self.progress_bar)
        
        record_layout.addWidget(progress_group)
        
        # 运行日志区域 - 可伸缩
        log_group = QGroupBox("📋 运行日志")
        log_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        log_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        log_layout = QVBoxLayout(log_group)
        
        log_toolbar = QHBoxLayout()
        self.clear_log_btn = QPushButton("清空日志")
        self.clear_log_btn.setFixedWidth(80)
        self.clear_log_btn.setObjectName("info_button")
        self.clear_log_btn.clicked.connect(self._clear_log)
        log_toolbar.addWidget(self.clear_log_btn)
        log_toolbar.addStretch()
        log_layout.addLayout(log_toolbar)
        
        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setMaximumBlockCount(500)
        self.log_widget.setFont(QFont("Consolas", 9))
        self.log_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.log_widget.setStyleSheet("""
            QPlainTextEdit {
                font-family: monospace;
                font-size: 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
        """)
        log_layout.addWidget(self.log_widget, 1)
        
        record_layout.addWidget(log_group, 1)
        record_layout.addStretch()
        
        # === 标签页2：编码设置 ===
        tab_settings = QWidget()
        settings_layout = QVBoxLayout(tab_settings)
        settings_layout.setSpacing(10)
        settings_layout.setContentsMargins(5, 5, 5, 5)
        
        encoding_group = QGroupBox("⚙️ 编码参数")
        encoding_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        encoding_form = QFormLayout(encoding_group)
        encoding_form.setSpacing(8)
        encoding_form.setLabelAlignment(Qt.AlignRight)
        
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 30)
        self.fps_spin.setValue(self.config.fps)
        self.fps_spin.setSuffix(" fps")
        encoding_form.addRow("帧率:", self.fps_spin)
        
        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(10, 200)
        self.scale_spin.setValue(self.config.scale_percent)
        self.scale_spin.setSuffix(" %")
        encoding_form.addRow("缩放比例:", self.scale_spin)
        
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(self.config.quality)
        self.quality_spin.setSuffix(" %")
        encoding_form.addRow("GIF质量:", self.quality_spin)
        
        self.colors_spin = QSpinBox()
        self.colors_spin.setRange(2, 256)
        self.colors_spin.setValue(self.config.colors)
        self.colors_spin.setSuffix(" 色")
        encoding_form.addRow("颜色数:", self.colors_spin)
        
        settings_layout.addWidget(encoding_group)
        
        options_group = QGroupBox("📝 其他选项")
        options_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        options_layout = QVBoxLayout(options_group)
        
        self.auto_start_check = QCheckBox("选择区域后自动开始录制")
        self.auto_start_check.setChecked(self.config.auto_start)
        options_layout.addWidget(self.auto_start_check)
        
        self.show_preview_check = QCheckBox("显示实时预览")
        self.show_preview_check.setChecked(self.config.show_preview)
        options_layout.addWidget(self.show_preview_check)
        
        self.auto_switch_tab_check = QCheckBox("文件管理器双击GIF后自动切换到录制标签页")
        self.auto_switch_tab_check.setChecked(self.config.auto_switch_tab)
        options_layout.addWidget(self.auto_switch_tab_check)
        
        self.enable_file_manager_preview_check = QCheckBox("启用文件管理器快速预览")
        self.enable_file_manager_preview_check.setChecked(self.config.enable_file_manager_preview)
        self.enable_file_manager_preview_check.stateChanged.connect(self._on_file_manager_preview_toggled)
        options_layout.addWidget(self.enable_file_manager_preview_check)
        
        self.enable_history_preview_check = QCheckBox("启用历史记录快速预览")
        self.enable_history_preview_check.setChecked(self.config.enable_history_preview)
        self.enable_history_preview_check.stateChanged.connect(self._on_history_preview_toggled)
        options_layout.addWidget(self.enable_history_preview_check)
        
        self.auto_play_preview_check = QCheckBox("快速预览自动播放")
        self.auto_play_preview_check.setChecked(self.config.auto_play_preview)
        self.auto_play_preview_check.stateChanged.connect(self._on_auto_play_preview_toggled)
        options_layout.addWidget(self.auto_play_preview_check)
        
        settings_layout.addWidget(options_group)
        settings_layout.addStretch()
        
        # === 标签页3：输出设置 ===
        tab_output = QWidget()
        output_layout = QVBoxLayout(tab_output)
        output_layout.setSpacing(10)
        output_layout.setContentsMargins(5, 5, 5, 5)
        
        output_dir_group = QGroupBox("💾 输出目录")
        output_dir_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        output_dir_layout = QVBoxLayout(output_dir_group)
        
        self.output_dir_label = QLabel(self.config.output_directory)
        self.output_dir_label.setWordWrap(True)
        self.output_dir_label.setStyleSheet("background-color: #f0f0f0; padding: 6px; border-radius: 3px;")
        output_dir_layout.addWidget(self.output_dir_label)
        
        self.open_output_dir_btn = QPushButton("📂 打开输出文件夹")
        self.open_output_dir_btn.setObjectName("info_button")
        output_dir_layout.addWidget(self.open_output_dir_btn)
        
        output_layout.addWidget(output_dir_group)
        
        size_group = QGroupBox("📦 文件大小控制")
        size_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        size_layout = QVBoxLayout(size_group)
        
        self.enable_size_control_check = QCheckBox("启用文件大小控制")
        self.enable_size_control_check.setChecked(self.config.enable_size_control)
        size_layout.addWidget(self.enable_size_control_check)
        
        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("目标大小:"))
        self.target_size_spin = QSpinBox()
        self.target_size_spin.setRange(50, 10240)
        self.target_size_spin.setValue(self.config.target_size_kb)
        self.target_size_spin.setSuffix(" KB")
        self.target_size_spin.setEnabled(self.config.enable_size_control)
        target_row.addWidget(self.target_size_spin)
        target_row.addStretch()
        size_layout.addLayout(target_row)
        
        quality_protect_label = QLabel("🛡️ 画质保护: 最小缩放30% | 最小颜色32色")
        quality_protect_label.setStyleSheet("color: #28a745; font-size: 10px; padding: 2px;")
        size_layout.addWidget(quality_protect_label)
        
        quick_row = QHBoxLayout()
        quick_row.setSpacing(5)
        
        self.size_500k_btn = QPushButton("500KB")
        self.size_500k_btn.setFixedWidth(60)
        self.size_500k_btn.clicked.connect(lambda: self.target_size_spin.setValue(500))
        self.size_500k_btn.setEnabled(self.config.enable_size_control)
        quick_row.addWidget(self.size_500k_btn)
        
        self.size_1m_btn = QPushButton("1MB")
        self.size_1m_btn.setFixedWidth(60)
        self.size_1m_btn.clicked.connect(lambda: self.target_size_spin.setValue(1024))
        self.size_1m_btn.setEnabled(self.config.enable_size_control)
        quick_row.addWidget(self.size_1m_btn)
        
        self.size_2m_btn = QPushButton("2MB")
        self.size_2m_btn.setFixedWidth(60)
        self.size_2m_btn.clicked.connect(lambda: self.target_size_spin.setValue(2048))
        self.size_2m_btn.setEnabled(self.config.enable_size_control)
        quick_row.addWidget(self.size_2m_btn)
        
        self.size_5m_btn = QPushButton("5MB")
        self.size_5m_btn.setFixedWidth(60)
        self.size_5m_btn.clicked.connect(lambda: self.target_size_spin.setValue(5120))
        self.size_5m_btn.setEnabled(self.config.enable_size_control)
        quick_row.addWidget(self.size_5m_btn)
        
        quick_row.addStretch()
        size_layout.addLayout(quick_row)
        
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("优化模式:"))
        self.size_mode_combo = QComboBox()
        self.size_mode_combo.addItems(["自动平衡", "优先画质", "优先体积"])
        self.size_mode_combo.setCurrentIndex(0)
        self.size_mode_combo.setEnabled(self.config.enable_size_control)
        mode_row.addWidget(self.size_mode_combo)
        mode_row.addStretch()
        size_layout.addLayout(mode_row)
        
        self.size_estimate_label = QLabel("预估大小: --")
        self.size_estimate_label.setStyleSheet("color: #666; padding: 4px; background-color: #f8f9fa; border-radius: 3px;")
        size_layout.addWidget(self.size_estimate_label)
        
        output_layout.addWidget(size_group)
        output_layout.addStretch()
        
        # === 标签页4：文件管理 ===
        tab_file_manager = QWidget()
        file_manager_layout = QVBoxLayout(tab_file_manager)
        file_manager_layout.setSpacing(10)
        file_manager_layout.setContentsMargins(5, 5, 5, 5)
        
        file_ops_group = QGroupBox("📁 文件操作")
        file_ops_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        file_ops_layout = QVBoxLayout(file_ops_group)
        
        file_btn_row = QHBoxLayout()
        file_btn_row.setSpacing(8)
        
        self.open_gif_btn = QPushButton("📂 打开GIF")
        self.open_gif_btn.setMinimumHeight(35)
        self.open_gif_btn.setObjectName("info_button")
        file_btn_row.addWidget(self.open_gif_btn)
        
        self.paste_gif_btn = QPushButton("📋 从剪贴板导入")
        self.paste_gif_btn.setMinimumHeight(35)
        self.paste_gif_btn.setObjectName("info_button")
        file_btn_row.addWidget(self.paste_gif_btn)
        
        file_ops_layout.addLayout(file_btn_row)
        
        self.file_info_label = QLabel("当前: 录制模式")
        self.file_info_label.setStyleSheet("color: #666; font-size: 11px; padding: 4px; background-color: #f0f0f0; border-radius: 4px;")
        self.file_info_label.setAlignment(Qt.AlignCenter)
        file_ops_layout.addWidget(self.file_info_label)
        
        file_manager_layout.addWidget(file_ops_group)
        
        file_mgr_group = QGroupBox("🗂️ 文件管理器")
        file_mgr_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        file_mgr_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        file_mgr_layout = QVBoxLayout(file_mgr_group)
        
        self.file_manager = FileManagerWidget(self.config.output_directory, self)
        self.file_manager.file_selected.connect(self._on_file_manager_file_selected)
        self.file_manager.file_double_clicked.connect(self._on_file_manager_file_double_clicked)
        self.file_manager.file_deleted.connect(self._on_file_deleted)
        
        # 文件管理器列表不伸缩，固定高度
        file_mgr_layout.addWidget(self.file_manager)
        
        file_manager_layout.addWidget(file_mgr_group)
        
        # 文件管理器快速预览区域 - 这个区域要伸缩
        self.file_manager_preview = GIFPreviewWidget()
        self.file_manager_preview.setVisible(self.config.enable_file_manager_preview)
        file_manager_layout.addWidget(self.file_manager_preview, 1)  # 拉伸因子为1
        
        file_manager_layout.addStretch()
        
        # === 标签页5：历史记录 ===
        tab_history = QWidget()
        history_layout = QVBoxLayout(tab_history)
        history_layout.setSpacing(10)
        history_layout.setContentsMargins(5, 5, 5, 5)
        
        history_group = QGroupBox("📜 最近录制/编辑")
        history_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        history_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        history_group_layout = QVBoxLayout(history_group)
        
        self.history_list = QListWidget()
        self.history_list.setMinimumHeight(150)
        self.history_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        self.history_list.setStyleSheet("QListWidget::item { padding: 6px; }")
        self.history_list.itemClicked.connect(self._on_history_item_clicked)
        self.history_list.itemDoubleClicked.connect(self._on_history_item_double_clicked)
        # 历史列表不伸缩，固定高度
        history_group_layout.addWidget(self.history_list)
        
        history_layout.addWidget(history_group)
        
        # 历史记录快速预览区域 - 这个区域要伸缩
        self.history_preview = GIFPreviewWidget()
        self.history_preview.setVisible(self.config.enable_history_preview)
        history_layout.addWidget(self.history_preview, 1)  # 拉伸因子为1
        
        history_btn_layout = QHBoxLayout()
        self.clear_history_btn = QPushButton("🗑 清空历史记录")
        self.clear_history_btn.setObjectName("danger_button")
        self.clear_history_btn.clicked.connect(self._clear_history)
        history_btn_layout.addWidget(self.clear_history_btn)
        history_btn_layout.addStretch()
        history_layout.addLayout(history_btn_layout)
        
        history_layout.addStretch()
        
        self.tab_widget.addTab(tab_record, "🎥 录制")
        self.tab_widget.addTab(tab_settings, "⚙️ 编码")
        self.tab_widget.addTab(tab_output, "📦 输出")
        self.tab_widget.addTab(tab_file_manager, "📁 文件管理")
        self.tab_widget.addTab(tab_history, "📜 历史")
        
        left_layout.addWidget(self.tab_widget)
        self.main_splitter.addWidget(left_panel)
        
        # ===== 右侧预览区域 =====
        right_panel = QWidget()
        right_panel.setMinimumWidth(400)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(8)
        right_layout.setContentsMargins(5, 0, 0, 0)
        
        preview_group = QGroupBox("🖼️ 实时预览")
        preview_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        preview_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(300)
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_label.setStyleSheet("border: 2px solid #ddd; background-color: #2d2d2d; color: white;")
        self.preview_label.setText("等待开始录制或打开GIF...")
        
        preview_scroll = QScrollArea()
        preview_scroll.setWidget(self.preview_label)
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(preview_scroll)
        
        right_layout.addWidget(preview_group, 1)
        
        self.frames_info_label = QLabel("📊 当前帧数: 0")
        self.frames_info_label.setAlignment(Qt.AlignRight)
        self.frames_info_label.setStyleSheet("padding: 4px;")
        right_layout.addWidget(self.frames_info_label)
        
        self.main_splitter.addWidget(right_panel)
        self.main_splitter.setSizes([350, 650])
        
        main_layout.addWidget(self.main_splitter)
        
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("就绪")
        
        self._apply_styles()
        self._refresh_history()
    
    def _on_auto_play_preview_toggled(self, checked):
        self.config.auto_play_preview = checked
        if self.file_manager_preview:
            self.file_manager_preview.set_auto_play(checked)
        if self.history_preview:
            self.history_preview.set_auto_play(checked)
        self._save_config()
    
    def _on_file_manager_preview_toggled(self, checked):
        self.config.enable_file_manager_preview = checked
        if self.file_manager_preview:
            self.file_manager_preview.setVisible(checked)
            if not checked:
                self.file_manager_preview.clear()
        self._save_config()
    
    def _on_history_preview_toggled(self, checked):
        self.config.enable_history_preview = checked
        if self.history_preview:
            self.history_preview.setVisible(checked)
            if not checked:
                self.history_preview.clear()
        self._save_config()
    
    def _on_file_manager_file_selected(self, file_path):
        if self.config.enable_file_manager_preview and self.file_manager_preview:
            self.file_manager_preview.load_gif(file_path)
    
    def _on_file_manager_file_double_clicked(self, file_path):
        try:
            log_manager.info(f"从文件管理器加载: {os.path.basename(file_path)}")
            frames, fps = GIFLoader.load_gif(file_path)
            self.fps_spin.setValue(fps)
            self._load_frames(frames, f"编辑模式: {os.path.basename(file_path)}")
            
            if self.auto_switch_tab_check.isChecked():
                self.tab_widget.setCurrentIndex(0)
                log_manager.info("已自动切换到录制标签页")
            else:
                log_manager.info("保持在当前标签页（用户已禁用自动切换）")
                
        except Exception as e:
            log_manager.error(f"无法加载GIF文件: {str(e)}")
            QMessageBox.critical(self, "错误", f"无法加载GIF文件:\n{str(e)}")
    
    def _on_history_item_clicked(self, item):
        if not self.config.enable_history_preview:
            return
        path = item.data(Qt.UserRole)
        if path and os.path.exists(path) and path.lower().endswith('.gif'):
            self.history_preview.load_gif(path)
    
    def _on_history_item_double_clicked(self, item):
        path = item.data(Qt.UserRole)
        if path and os.path.exists(path):
            try:
                log_manager.info(f"从历史记录加载: {os.path.basename(path)}")
                frames, fps = GIFLoader.load_gif(path)
                self.fps_spin.setValue(fps)
                self._load_frames(frames, f"编辑模式: {os.path.basename(path)}")
                if self.auto_switch_tab_check.isChecked():
                    self.tab_widget.setCurrentIndex(0)
            except Exception as e:
                log_manager.error(f"无法加载GIF: {str(e)}")
                QMessageBox.critical(self, "错误", f"无法加载GIF:\n{str(e)}")
    
    def _clear_log(self):
        if self.log_widget:
            self.log_widget.clear()
            log_manager.info("日志已清空")
    
    def _clear_history(self):
        reply = QMessageBox.question(self, "确认", "确定清空历史记录吗？\n这只是清除显示列表，不会删除文件。",
                                      QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.history_list.clear()
            if self.history_preview:
                self.history_preview.clear()
            log_manager.info("历史记录已清空")
    
    def _on_file_deleted(self, file_path):
        self._refresh_history()
        if self.file_manager_preview:
            self.file_manager_preview.clear()
    
    def _on_size_control_toggled(self, checked):
        self.target_size_spin.setEnabled(checked)
        self.size_mode_combo.setEnabled(checked)
        self.size_500k_btn.setEnabled(checked)
        self.size_1m_btn.setEnabled(checked)
        self.size_2m_btn.setEnabled(checked)
        self.size_5m_btn.setEnabled(checked)
        
        if checked and self.captured_frames:
            self._update_size_estimate()
        else:
            self.size_estimate_label.setText("预估大小: --")
    
    def _update_size_estimate(self):
        if not self.captured_frames:
            return
        try:
            sample = self.captured_frames[0]
            h, w = sample.shape[:2]
            scaled_w = int(w * self.scale_spin.value() / 100)
            scaled_h = int(h * self.scale_spin.value() / 100)
            
            estimated = GIFSizeEstimator.estimate_size(
                len(self.captured_frames), scaled_w, scaled_h,
                self.fps_spin.value(), self.colors_spin.value(), self.quality_spin.value()
            )
            
            if estimated < 1024:
                size_text = f"{estimated} KB"
            else:
                size_text = f"{estimated / 1024:.1f} MB"
            
            if self.enable_size_control_check.isChecked():
                target = self.target_size_spin.value()
                if estimated > target:
                    self.size_estimate_label.setText(f"⚠️ 预估: {size_text} (超过目标 {target}KB)")
                    self.size_estimate_label.setStyleSheet("color: #dc3545; padding: 4px; background-color: #f8f9fa; border-radius: 3px;")
                else:
                    self.size_estimate_label.setText(f"✓ 预估: {size_text} (目标 {target}KB)")
                    self.size_estimate_label.setStyleSheet("color: #28a745; padding: 4px; background-color: #f8f9fa; border-radius: 3px;")
            else:
                self.size_estimate_label.setText(f"预估: {size_text}")
                self.size_estimate_label.setStyleSheet("color: #666; padding: 4px; background-color: #f8f9fa; border-radius: 3px;")
        except Exception as e:
            print(f"预估失败: {e}")
    
    def _create_menu_bar(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("文件")
        
        open_gif_action = QAction("打开GIF文件", self)
        open_gif_action.triggered.connect(self._on_open_gif)
        open_gif_action.setShortcut("Ctrl+O")
        file_menu.addAction(open_gif_action)
        
        paste_action = QAction("从剪贴板导入", self)
        paste_action.triggered.connect(self._on_paste_gif)
        paste_action.setShortcut("Ctrl+V")
        file_menu.addAction(paste_action)
        
        file_menu.addSeparator()
        
        open_folder = QAction("打开输出文件夹", self)
        open_folder.triggered.connect(self._on_open_output_folder)
        file_menu.addAction(open_folder)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        edit_menu = menubar.addMenu("编辑")
        
        clear_action = QAction("清除所有帧", self)
        clear_action.triggered.connect(self._on_clear_frames)
        edit_menu.addAction(clear_action)
        
        edit_menu.addSeparator()
        
        edit_frames_action = QAction("编辑帧", self)
        edit_frames_action.triggered.connect(self._on_edit_frames)
        edit_frames_action.setEnabled(False)
        edit_menu.addAction(edit_frames_action)
        self.edit_frames_action = edit_frames_action
        
        view_menu = menubar.addMenu("视图")
        top_action = QAction("窗口置顶", self)
        top_action.setCheckable(True)
        top_action.triggered.connect(self._on_toggle_always_on_top)
        view_menu.addAction(top_action)
        
        help_menu = menubar.addMenu("帮助")
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)
    
    def _apply_styles(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f5f5; }
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 1px solid #ddd;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
            }
            QPushButton {
                border: none;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton#primary_button {
                background-color: #0078d4;
                color: white;
            }
            QPushButton#primary_button:hover { background-color: #005a9e; }
            QPushButton#success_button {
                background-color: #28a745;
                color: white;
            }
            QPushButton#success_button:hover { background-color: #218838; }
            QPushButton#danger_button {
                background-color: #dc3545;
                color: white;
            }
            QPushButton#danger_button:hover { background-color: #c82333; }
            QPushButton#info_button {
                background-color: #17a2b8;
                color: white;
            }
            QPushButton#info_button:hover { background-color: #138496; }
            QPushButton#warning_button {
                background-color: #ffc107;
                color: black;
            }
            QPushButton#warning_button:hover { background-color: #e0a800; }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QSpinBox, QComboBox {
                padding: 4px;
                border: 1px solid #ddd;
                border-radius: 3px;
                min-height: 22px;
            }
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 4px;
                text-align: center;
                height: 22px;
            }
            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 3px;
            }
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #e6f2ff;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
                color: white;
            }
            QSplitter::handle {
                background-color: #ddd;
                width: 4px;
            }
            QSplitter::handle:hover {
                background-color: #0078d4;
            }
        """)
    
    def _setup_signals(self):
        self.open_gif_btn.clicked.connect(self._on_open_gif)
        self.paste_gif_btn.clicked.connect(self._on_paste_gif)
        self.select_region_btn.clicked.connect(self._on_select_region)
        self.start_capture_btn.clicked.connect(self._on_start_capture)
        self.stop_capture_btn.clicked.connect(self._on_stop_capture)
        self.open_output_dir_btn.clicked.connect(self._on_open_output_folder)
        self.generate_gif_btn.clicked.connect(self._on_generate_gif)
        self.play_btn.clicked.connect(self._on_play_recording)
        self.edit_btn.clicked.connect(self._on_edit_frames)
        
        self.fps_spin.valueChanged.connect(self._on_setting_changed)
        self.scale_spin.valueChanged.connect(self._on_setting_changed)
        self.quality_spin.valueChanged.connect(self._on_setting_changed)
        self.colors_spin.valueChanged.connect(self._on_setting_changed)
        self.auto_start_check.stateChanged.connect(self._save_config)
        self.show_preview_check.stateChanged.connect(self._save_config)
        self.auto_switch_tab_check.stateChanged.connect(self._save_config)
        self.enable_size_control_check.toggled.connect(self._on_size_control_toggled)
        self.enable_size_control_check.stateChanged.connect(self._on_setting_changed)
        self.target_size_spin.valueChanged.connect(self._on_setting_changed)
        self.size_mode_combo.currentIndexChanged.connect(self._on_setting_changed)
        
        self.preview_timer.timeout.connect(self._update_preview)
    
    def _on_setting_changed(self):
        self._save_config()
        if self.captured_frames and self.enable_size_control_check.isChecked():
            self._update_size_estimate()
    
    def _check_icon(self):
        icon_path = os.path.join(os.path.dirname(sys.argv[0]), "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.setWindowIcon(QIcon(icon_path))
            except:
                pass
    
    def _load_config(self):
        try:
            os.makedirs(self.config.output_directory, exist_ok=True)
            self.output_dir_label.setText(self.config.output_directory)
            if hasattr(self, 'file_manager'):
                self.file_manager.set_directory(self.config.output_directory)
            if self.config.last_selection:
                rect = QRect(
                    self.config.last_selection.get('x', 0),
                    self.config.last_selection.get('y', 0),
                    self.config.last_selection.get('width', 0),
                    self.config.last_selection.get('height', 0)
                )
                if rect.width() > 0 and rect.height() > 0:
                    self.capture_rect = rect
                    self.region_info_label.setText(f"区域: {rect.width()} × {rect.height()}")
                    self.start_capture_btn.setEnabled(True)
            
            if hasattr(self.config, 'auto_switch_tab'):
                self.auto_switch_tab_check.setChecked(self.config.auto_switch_tab)
            if hasattr(self.config, 'enable_file_manager_preview'):
                self.enable_file_manager_preview_check.setChecked(self.config.enable_file_manager_preview)
            if hasattr(self.config, 'enable_history_preview'):
                self.enable_history_preview_check.setChecked(self.config.enable_history_preview)
            if hasattr(self.config, 'auto_play_preview'):
                self.auto_play_preview_check.setChecked(self.config.auto_play_preview)
                
        except Exception as e:
            print(f"加载配置失败: {e}")
    
    def _save_config(self):
        try:
            self.config.fps = self.fps_spin.value()
            self.config.scale_percent = self.scale_spin.value()
            self.config.quality = self.quality_spin.value()
            self.config.colors = self.colors_spin.value()
            self.config.auto_start = self.auto_start_check.isChecked()
            self.config.show_preview = self.show_preview_check.isChecked()
            self.config.enable_size_control = self.enable_size_control_check.isChecked()
            self.config.target_size_kb = self.target_size_spin.value()
            self.config.auto_switch_tab = self.auto_switch_tab_check.isChecked()
            self.config.enable_file_manager_preview = self.enable_file_manager_preview_check.isChecked()
            self.config.enable_history_preview = self.enable_history_preview_check.isChecked()
            self.config.auto_play_preview = self.auto_play_preview_check.isChecked()
            
            mode_map = {0: "auto", 1: "quality", 2: "size"}
            self.config.size_control_mode = mode_map.get(self.size_mode_combo.currentIndex(), "auto")
            
            self.config.window_x = self.x()
            self.config.window_y = self.y()
            self.config.window_width = self.width()
            self.config.window_height = self.height()
            
            if self.main_splitter:
                self.config.splitter_sizes = self.main_splitter.sizes()
            
            if self.capture_rect:
                self.config.last_selection = {
                    'x': self.capture_rect.x(),
                    'y': self.capture_rect.y(),
                    'width': self.capture_rect.width(),
                    'height': self.capture_rect.height()
                }
            
            self._ensure_output_directory()
            self.config.save_to_file(self.config_file)
        except Exception as e:
            print(f"保存配置失败: {e}")
    
    def _refresh_history(self):
        self.history_list.clear()
        try:
            output_dir = self.config.output_directory
            if os.path.exists(output_dir):
                gif_files = []
                for f in os.listdir(output_dir):
                    if f.lower().endswith('.gif'):
                        path = os.path.join(output_dir, f)
                        gif_files.append((os.path.getmtime(path), f, path))
                gif_files.sort(reverse=True)
                for mtime, filename, path in gif_files[:20]:
                    size = os.path.getsize(path) / 1024
                    size_str = f"{size:.1f}KB" if size < 1024 else f"{size/1024:.1f}MB"
                    dt = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                    item = QListWidgetItem(f"🎬 {filename}  ({dt}, {size_str})")
                    item.setData(Qt.UserRole, path)
                    self.history_list.addItem(item)
        except Exception as e:
            print(f"刷新历史失败: {e}")
    
    def _load_frames(self, frames, source_name):
        if not frames:
            QMessageBox.warning(self, "警告", "没有有效的帧数据")
            return
        
        self.captured_frames = frames
        self.preview_index = 0
        self.is_recording = False
        
        self.generate_gif_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.edit_btn.setEnabled(True)
        if hasattr(self, 'edit_frames_action'):
            self.edit_frames_action.setEnabled(True)
        
        self.frames_info_label.setText(f"📊 当前帧数: {len(self.captured_frames)}")
        self.file_info_label.setText(f"当前: {source_name}")
        self.file_info_label.setStyleSheet("color: #28a745; font-size: 11px; padding: 4px; background-color: #f0f0f0; border-radius: 4px;")
        
        self._update_preview()
        
        if self.enable_size_control_check.isChecked():
            self._update_size_estimate()
        
        log_manager.info(f"已加载 {len(self.captured_frames)} 帧 - {source_name}")
        self._update_status(f"已加载 {len(self.captured_frames)} 帧 - {source_name}")
    
    def _on_open_gif(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开GIF文件", "", "GIF文件 (*.gif);;所有文件 (*.*)"
        )
        if not file_path:
            return
        
        try:
            log_manager.info(f"正在打开GIF文件: {file_path}")
            frames, fps = GIFLoader.load_gif(file_path)
            self.fps_spin.setValue(fps)
            self._load_frames(frames, f"编辑模式: {os.path.basename(file_path)}")
            log_manager.success(f"成功加载GIF: {os.path.basename(file_path)} ({len(frames)}帧, {fps}fps)")
            self._update_status(f"成功加载GIF: {os.path.basename(file_path)} ({len(frames)}帧, {fps}fps)")
        except Exception as e:
            log_manager.error(f"无法加载GIF文件: {str(e)}")
            QMessageBox.critical(self, "错误", f"无法加载GIF文件:\n{str(e)}")
    
    def _on_paste_gif(self):
        try:
            log_manager.info("从剪贴板导入GIF")
            result = GIFLoader.load_from_clipboard()
            if result:
                frames, fps = result
                self.fps_spin.setValue(fps)
                self._load_frames(frames, "编辑模式: 剪贴板导入")
                log_manager.success(f"从剪贴板导入成功 ({len(frames)}帧)")
                self._update_status(f"从剪贴板导入成功 ({len(frames)}帧)")
            else:
                log_manager.warning("剪贴板中没有有效的GIF或图片数据")
                QMessageBox.information(self, "提示", "剪贴板中没有有效的GIF或图片数据")
        except Exception as e:
            log_manager.error(f"从剪贴板导入失败: {str(e)}")
            QMessageBox.critical(self, "错误", f"从剪贴板导入失败:\n{str(e)}")
    
    def _on_select_region(self):
        self.selection_window = RegionSelectionWindow()
        self.selection_window.region_selected.connect(self._on_region_selected)
        self.selection_window.show()
        self.showMinimized()
    
    def _on_region_selected(self, rect):
        self.capture_rect = rect
        self.region_info_label.setText(f"区域: {rect.width()} × {rect.height()}")
        log_manager.info(f"选择录制区域: {rect.width()} × {rect.height()}")
        self._save_config()
        self.start_capture_btn.setEnabled(True)
        self.showNormal()
        self.activateWindow()
        if self.auto_start_check.isChecked():
            log_manager.info("自动开始录制")
            self._on_start_capture()
    
    def _on_start_capture(self):
        if not self.capture_rect:
            QMessageBox.warning(self, "警告", "请先选择录制区域")
            return
        
        self.captured_frames = []
        self.preview_index = 0
        self.progress_bar.setValue(0)
        self.is_recording = True
        
        self.select_region_btn.setEnabled(False)
        self.start_capture_btn.setEnabled(False)
        self.stop_capture_btn.setEnabled(True)
        self.generate_gif_btn.setEnabled(False)
        self.play_btn.setEnabled(False)
        self.edit_btn.setEnabled(False)
        self.open_gif_btn.setEnabled(False)
        self.paste_gif_btn.setEnabled(False)
        if hasattr(self, 'edit_frames_action'):
            self.edit_frames_action.setEnabled(False)
        
        self.file_info_label.setText("当前: 录制模式")
        self.file_info_label.setStyleSheet("color: #666; font-size: 11px; padding: 4px; background-color: #f0f0f0; border-radius: 4px;")
        
        self.capture_thread = ScreenCaptureThread(self.capture_rect)
        self.capture_thread.set_target_fps(self.fps_spin.value())
        self.capture_thread.frame_captured.connect(self._on_frame_captured)
        self.capture_thread.capture_finished.connect(self._on_capture_finished)
        self.capture_thread.capture_error.connect(self._on_capture_error)
        self.capture_thread.start()
        
        log_manager.info(f"开始录制 - 区域: {self.capture_rect.width()}×{self.capture_rect.height()}, FPS: {self.fps_spin.value()}")
        self._update_status("正在录制...")
        if self.show_preview_check.isChecked():
            self.preview_timer.start(100)
    
    def _on_stop_capture(self):
        self.is_recording = False
        if self.capture_thread:
            self.capture_thread.stop()
            self.capture_thread.wait(1000)
            self.capture_thread = None
        self.preview_timer.stop()
        
        self.select_region_btn.setEnabled(True)
        self.start_capture_btn.setEnabled(True)
        self.stop_capture_btn.setEnabled(False)
        self.open_gif_btn.setEnabled(True)
        self.paste_gif_btn.setEnabled(True)
        
        if self.captured_frames:
            self.generate_gif_btn.setEnabled(True)
            self.play_btn.setEnabled(True)
            self.edit_btn.setEnabled(True)
            if hasattr(self, 'edit_frames_action'):
                self.edit_frames_action.setEnabled(True)
            self.frames_info_label.setText(f"📊 当前帧数: {len(self.captured_frames)}")
            log_manager.info(f"录制完成，共 {len(self.captured_frames)} 帧")
            self._update_status(f"录制完成，共 {len(self.captured_frames)} 帧")
            if self.enable_size_control_check.isChecked():
                self._update_size_estimate()
        else:
            log_manager.warning("录制未捕获到任何帧")
            self._update_status("未捕获到任何帧")
    
    def _on_frame_captured(self, frame):
        if self.is_recording:
            self.captured_frames.append(frame)
            self.frames_info_label.setText(f"📊 当前帧数: {len(self.captured_frames)}")
    
    def _on_capture_finished(self):
        pass
    
    def _on_capture_error(self, error_msg):
        log_manager.error(f"捕获出错: {error_msg}")
        QMessageBox.critical(self, "错误", f"捕获出错: {error_msg}")
        self._on_stop_capture()
    
    def _update_preview(self):
        if not self.captured_frames:
            return
        
        if self.is_recording and not self.show_preview_check.isChecked():
            return
            
        try:
            if self.preview_index >= len(self.captured_frames):
                self.preview_index = 0
            frame = self.captured_frames[self.preview_index]
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            else:
                frame_rgb = frame
            h, w = frame_rgb.shape[:2]
            qimg = QImage(frame_rgb.data, w, h, 3 * w, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)
            label_size = self.preview_label.size()
            if label_size.width() > 0 and label_size.height() > 0:
                scaled = pixmap.scaled(label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.preview_label.setPixmap(scaled)
            self.preview_index += 1
        except Exception as e:
            print(f"预览更新出错: {e}")
    
    def _on_play_recording(self):
        if not self.captured_frames:
            QMessageBox.warning(self, "警告", "没有可播放的帧")
            return
        if self.player_window and self.player_window.isVisible():
            self.player_window.close()
        log_manager.info(f"播放预览 - {len(self.captured_frames)}帧")
        self.player_window = GIFPlayerWindow(self.captured_frames.copy(), self.fps_spin.value(), self)
        self.player_window.show()
    
    def _on_edit_frames(self):
        if not self.captured_frames:
            QMessageBox.warning(self, "警告", "没有可编辑的帧")
            return
        log_manager.info("打开帧编辑器")
        self.editor_dialog = FrameEditorDialog(self.captured_frames, self)
        if self.editor_dialog.exec() == QDialog.Accepted:
            edited = self.editor_dialog.get_edited_frames()
            if len(edited) != len(self.captured_frames):
                self.captured_frames = edited
                self.frames_info_label.setText(f"📊 当前帧数: {len(self.captured_frames)} (已编辑)")
                log_manager.info(f"编辑完成，当前 {len(self.captured_frames)} 帧")
                self._update_status(f"编辑完成，当前 {len(self.captured_frames)} 帧")
                self.preview_index = 0
                self._update_preview()
                if self.enable_size_control_check.isChecked():
                    self._update_size_estimate()
    
    def _on_clear_frames(self):
        if self.captured_frames:
            reply = QMessageBox.question(self, "确认", "清除所有帧？", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                log_manager.info("清除所有帧")
                self.captured_frames = []
                self.frames_info_label.setText("📊 当前帧数: 0")
                self.preview_label.clear()
                self.preview_label.setText("等待开始录制或打开GIF...")
                self.generate_gif_btn.setEnabled(False)
                self.play_btn.setEnabled(False)
                self.edit_btn.setEnabled(False)
                if hasattr(self, 'edit_frames_action'):
                    self.edit_frames_action.setEnabled(False)
                self._update_status("已清除所有帧")
                self.size_estimate_label.setText("预估大小: --")
                self.file_info_label.setText("当前: 录制模式")
                self.file_info_label.setStyleSheet("color: #666; font-size: 11px; padding: 4px; background-color: #f0f0f0; border-radius: 4px;")
    
    def _on_generate_gif(self):
        if not self.captured_frames:
            QMessageBox.warning(self, "警告", "没有可用的帧")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"output_{timestamp}.gif"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存GIF", os.path.join(self.config.output_directory, default_name), "GIF文件 (*.gif)"
        )
        if not file_path:
            return
        
        mode_map = {0: "auto", 1: "quality", 2: "size"}
        size_mode = mode_map.get(self.size_mode_combo.currentIndex(), "auto")
        
        self.generate_gif_btn.setEnabled(False)
        self.select_region_btn.setEnabled(False)
        self.start_capture_btn.setEnabled(False)
        self.play_btn.setEnabled(False)
        self.edit_btn.setEnabled(False)
        self.open_gif_btn.setEnabled(False)
        self.paste_gif_btn.setEnabled(False)
        
        log_manager.info(f"开始导出GIF: {os.path.basename(file_path)}")
        log_manager.info(f"参数: FPS={self.fps_spin.value()}, 缩放={self.scale_spin.value()}%, "
                        f"颜色={self.colors_spin.value()}, 质量={self.quality_spin.value()}%")
        
        self.encode_thread = GIFEncodingThread(
            self.captured_frames.copy(), file_path,
            self.fps_spin.value(), self.scale_spin.value(),
            self.quality_spin.value(), self.colors_spin.value(),
            self.enable_size_control_check.isChecked(),
            self.target_size_spin.value(), size_mode,
            min_scale=self.config.min_scale_percent,
            min_colors=self.config.min_colors
        )
        
        self.encode_thread.progress_updated.connect(self.progress_bar.setValue)
        self.encode_thread.status_updated.connect(self._update_status)
        self.encode_thread.encoding_finished.connect(self._on_encoding_finished)
        self.encode_thread.encoding_error.connect(self._on_encoding_error)
        self.encode_thread.size_estimate_updated.connect(self._on_size_estimate_updated)
        self.encode_thread.actual_size_signal.connect(self._on_actual_size)
        self.encode_thread.start()
        
        self._update_status("正在生成GIF...")
    
    def _on_actual_size(self, actual_kb, target_kb):
        if actual_kb <= target_kb:
            self._update_status(f"✓ 实际大小: {actual_kb}KB ≤ 目标 {target_kb}KB")
        else:
            self._update_status(f"⚠ 实际大小: {actual_kb}KB > 目标 {target_kb}KB")
    
    def _on_size_estimate_updated(self, estimated, target):
        if estimated <= target:
            self._update_status(f"优化: 估计 {estimated}KB ≤ 目标 {target}KB")
        else:
            self._update_status(f"优化: 估计 {estimated}KB > 目标 {target}KB，将尽可能压缩")
    
    def _on_encoding_finished(self, file_path):
        self.progress_bar.setValue(100)
        actual = os.path.getsize(file_path) / 1024
        size_str = f"{actual:.1f}KB" if actual < 1024 else f"{actual/1024:.1f}MB"
        log_manager.success(f"GIF导出完成: {os.path.basename(file_path)} ({size_str})")
        self._update_status(f"完成: {os.path.basename(file_path)} ({size_str})")
        
        self.generate_gif_btn.setEnabled(True)
        self.select_region_btn.setEnabled(True)
        self.start_capture_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.edit_btn.setEnabled(True)
        self.open_gif_btn.setEnabled(True)
        self.paste_gif_btn.setEnabled(True)
        
        self._refresh_history()
        if hasattr(self, 'file_manager'):
            self.file_manager.refresh()
        
        reply = QMessageBox.question(self, "完成", f"GIF已保存\n大小: {size_str}\n\n打开所在文件夹？",
                                      QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self._open_file_location(file_path)
    
    def _on_encoding_error(self, error_msg):
        log_manager.error(f"GIF生成失败: {error_msg}")
        QMessageBox.critical(self, "错误", f"生成失败:\n{error_msg}")
        self.generate_gif_btn.setEnabled(True)
        self.select_region_btn.setEnabled(True)
        self.start_capture_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.edit_btn.setEnabled(True)
        self.open_gif_btn.setEnabled(True)
        self.paste_gif_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self._update_status("生成失败")
    
    def _on_open_output_folder(self):
        try:
            if os.path.exists(self.config.output_directory):
                log_manager.info(f"打开输出文件夹: {self.config.output_directory}")
                QDesktopServices.openUrl(QUrl.fromLocalFile(self.config.output_directory))
            else:
                QMessageBox.warning(self, "警告", "输出文件夹不存在")
        except Exception as e:
            log_manager.error(f"无法打开文件夹: {e}")
            QMessageBox.critical(self, "错误", f"无法打开文件夹: {e}")
    
    def _on_toggle_always_on_top(self, checked):
        if checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()
    
    def _on_about(self):
        QMessageBox.about(self, "关于", 
            f"<h2>{ProjectInfo.NAME}</h2>"
            f"<p>版本: {ProjectInfo.VERSION}</p>"
            f"<p>构建: {ProjectInfo.BUILD_DATE}</p>"
            f"<p>屏幕区域录制转GIF工具</p>"
            f"<ul><li>选择任意屏幕区域</li><li>可调节帧率/缩放/颜色</li>"
            f"<li>文件大小控制（画质保护）</li><li>播放和编辑功能</li>"
            f"<li><b>打开/导入GIF进行编辑</b></li>"
            f"<li><b>帧编辑器完整功能</b></li>"
            f"<li><b>内置文件管理器</b></li>"
            f"<li><b>文件管理器快速预览</b></li>"
            f"<li><b>历史记录快速预览</b></li>"
            f"<li><b>快速预览自动播放</b></li>"
            f"<li><b>预览区域自动拉伸</b></li></ul>"
            f"<p>输出目录: {self.config.output_directory}</p>"
            f"<hr><p>{ProjectInfo.COPYRIGHT}</p>")
    
    def _open_file_location(self, file_path):
        try:
            if sys.platform == 'win32':
                os.startfile(os.path.dirname(file_path))
            elif sys.platform == 'darwin':
                os.system(f'open "{os.path.dirname(file_path)}"')
            else:
                os.system(f'xdg-open "{os.path.dirname(file_path)}"')
        except Exception as e:
            QMessageBox.information(self, "提示", f"无法打开文件夹: {e}")
    
    def _update_status(self, message):
        self.status_label.setText(message)
        self.status_bar.showMessage(message)
    
    def closeEvent(self, event):
        log_manager.info("程序退出")
        if self.capture_thread and self.capture_thread.isRunning():
            self.capture_thread.stop()
            self.capture_thread.wait(2000)
        if self.encode_thread and self.encode_thread.isRunning():
            self.encode_thread.stop()
            self.encode_thread.wait(2000)
        if self.player_window and self.player_window.isVisible():
            self.player_window.close()
        if self.editor_dialog and self.editor_dialog.isVisible():
            self.editor_dialog.close()
        if self.file_manager_preview:
            self.file_manager_preview.close()
        if self.history_preview:
            self.history_preview.close()
        if self.log_widget:
            log_manager.unregister_widget(self.log_widget)
        self._save_config()
        event.accept()


def main():
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("ScreenToGIF")
        app.setOrganizationName("ScreenToGIF")
        app.setFont(QFont("Microsoft YaHei", 9))
        
        window = ScreenToGIFMainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"程序启动失败: {e}")
        traceback.print_exc()
        input("按回车键退出...")

if __name__ == "__main__":
    main()