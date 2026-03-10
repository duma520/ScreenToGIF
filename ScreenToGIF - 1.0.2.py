#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Screen to GIF - 屏幕区域录制转GIF工具
增强版：支持录制后播放和编辑功能
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
    QRectF, QEasingCurve, QPropertyAnimation, QUrl
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QIcon, 
    QFont, QPalette, QLinearGradient, QCursor, QScreen,
    QFontMetrics, QAction, QActionGroup, QImage, QDesktopServices
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSpinBox, QDoubleSpinBox, QCheckBox,
    QGroupBox, QSlider, QFileDialog, QMessageBox, QFrame,
    QProgressBar, QSizePolicy, QGridLayout, QScrollArea,
    QTabWidget, QSplitter, QLineEdit, QComboBox, QDialog,
    QTextEdit, QDialogButtonBox, QListWidget, QListWidgetItem,
    QToolBar, QStatusBar, QMenu, QMenuBar
)

# ==================== 配置管理类 ====================
@dataclass
class AppConfig:
    """应用程序配置数据类"""
    # 输出目录改为程序所在目录下的子目录
    output_directory: str = ""  # 将在初始化时设置
    fps: int = 10
    scale_percent: int = 100
    quality: int = 80
    auto_start: bool = False
    show_preview: bool = True
    frame_skip: int = 0
    colors: int = 256
    window_x: int = 100
    window_y: int = 100
    window_width: int = 900
    window_height: int = 700
    last_selection: dict = None
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.output_directory:
            # 设置为程序所在目录下的子目录
            program_dir = os.path.dirname(sys.argv[0])
            self.output_directory = os.path.join(program_dir, "ScreenToGIF_Recordings")
    
    def save_to_file(self, filepath: str):
        """保存配置到文件"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置文件失败: {e}")
    
    @classmethod
    def load_from_file(cls, filepath: str) -> 'AppConfig':
        """从文件加载配置"""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return cls(**data)
        except Exception as e:
            print(f"加载配置文件失败: {e}")
        return cls()

# ==================== 帧编辑器对话框 ====================
class FrameEditorDialog(QDialog):
    """帧编辑器对话框 - 支持删除帧和调整顺序"""
    
    def __init__(self, frames, parent=None):
        super().__init__(parent)
        self.frames = frames.copy()  # 原始帧
        self.current_frames = frames.copy()  # 编辑后的帧
        self.current_index = 0
        self.play_timer = QTimer()
        self.is_playing = False
        
        self.setWindowTitle("帧编辑器")
        self.setMinimumSize(900, 600)
        self.setModal(True)
        
        self._setup_ui()
        self._setup_signals()
        self._update_preview()
    
    def _setup_ui(self):
        """设置用户界面"""
        main_layout = QVBoxLayout(self)
        
        # 工具栏
        toolbar = QToolBar()
        toolbar.setStyleSheet("QToolBar { spacing: 5px; }")
        
        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.setCheckable(True)
        self.play_btn.setMaximumWidth(100)
        toolbar.addWidget(self.play_btn)
        
        toolbar.addSeparator()
        
        self.delete_btn = QPushButton("🗑 删除当前帧")
        self.delete_btn.setMaximumWidth(120)
        toolbar.addWidget(self.delete_btn)
        
        self.delete_range_btn = QPushButton("🗑 删除选定范围")
        self.delete_range_btn.setMaximumWidth(140)
        toolbar.addWidget(self.delete_range_btn)
        
        toolbar.addSeparator()
        
        self.move_up_btn = QPushButton("↑ 上移")
        self.move_up_btn.setMaximumWidth(80)
        toolbar.addWidget(self.move_up_btn)
        
        self.move_down_btn = QPushButton("↓ 下移")
        self.move_down_btn.setMaximumWidth(80)
        toolbar.addWidget(self.move_down_btn)
        
        toolbar.addSeparator()
        
        self.crop_btn = QPushButton("✂ 裁剪帧")
        self.crop_btn.setMaximumWidth(80)
        toolbar.addWidget(self.crop_btn)
        
        self.reset_btn = QPushButton("↺ 重置")
        self.reset_btn.setMaximumWidth(80)
        toolbar.addWidget(self.reset_btn)
        
        main_layout.addWidget(toolbar)
        
        # 信息栏
        info_layout = QHBoxLayout()
        self.frame_info_label = QLabel("帧信息")
        info_layout.addWidget(self.frame_info_label)
        info_layout.addStretch()
        
        self.range_label = QLabel("选择范围: 无")
        info_layout.addWidget(self.range_label)
        
        main_layout.addLayout(info_layout)
        
        # 主内容区域 - 分割视图
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧：帧列表（缩略图）
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        left_layout.addWidget(QLabel("帧列表 (点击选择):"))
        
        self.frame_list = QListWidget()
        self.frame_list.setViewMode(QListWidget.IconMode)
        self.frame_list.setIconSize(QSize(160, 120))
        self.frame_list.setResizeMode(QListWidget.Adjust)
        self.frame_list.setSelectionMode(QListWidget.ExtendedSelection)
        left_layout.addWidget(self.frame_list)
        
        # 帧控制按钮
        frame_control_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setMaximumWidth(60)
        frame_control_layout.addWidget(self.select_all_btn)
        
        self.deselect_all_btn = QPushButton("取消全选")
        self.deselect_all_btn.setMaximumWidth(80)
        frame_control_layout.addWidget(self.deselect_all_btn)
        
        frame_control_layout.addStretch()
        left_layout.addLayout(frame_control_layout)
        
        splitter.addWidget(left_widget)
        
        # 右侧：预览区域
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # 预览标签
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(400, 300)
        self.preview_label.setStyleSheet("border: 1px solid #ddd; background-color: #2d2d2d;")
        self.preview_label.setText("预览")
        
        # 滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.preview_label)
        scroll_area.setWidgetResizable(True)
        scroll_area.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(scroll_area)
        
        # 预览控制
        preview_control = QHBoxLayout()
        
        self.prev_btn = QPushButton("◀ 上一帧")
        self.prev_btn.setMaximumWidth(100)
        preview_control.addWidget(self.prev_btn)
        
        self.next_btn = QPushButton("下一帧 ▶")
        self.next_btn.setMaximumWidth(100)
        preview_control.addWidget(self.next_btn)
        
        preview_control.addStretch()
        
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(max(0, len(self.current_frames) - 1))
        preview_control.addWidget(self.frame_slider)
        
        self.frame_counter = QLabel("0/0")
        self.frame_counter.setMinimumWidth(60)
        preview_control.addWidget(self.frame_counter)
        
        right_layout.addLayout(preview_control)
        
        splitter.addWidget(right_widget)
        
        # 设置分割比例
        splitter.setSizes([300, 600])
        
        main_layout.addWidget(splitter)
        
        # 底部按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
        
        # 加载帧到列表
        self._load_frames_to_list()
    
    def _setup_signals(self):
        """设置信号连接"""
        self.play_btn.toggled.connect(self._on_play_toggled)
        self.delete_btn.clicked.connect(self._on_delete_current)
        self.delete_range_btn.clicked.connect(self._on_delete_range)
        self.move_up_btn.clicked.connect(self._on_move_up)
        self.move_down_btn.clicked.connect(self._on_move_down)
        self.crop_btn.clicked.connect(self._on_crop_frames)
        self.reset_btn.clicked.connect(self._on_reset)
        self.select_all_btn.clicked.connect(self._on_select_all)
        self.deselect_all_btn.clicked.connect(self._on_deselect_all)
        self.prev_btn.clicked.connect(self._on_prev_frame)
        self.next_btn.clicked.connect(self._on_next_frame)
        self.frame_slider.valueChanged.connect(self._on_slider_changed)
        self.frame_list.itemSelectionChanged.connect(self._on_selection_changed)
        
        self.play_timer.timeout.connect(self._on_play_timeout)
    
    def _load_frames_to_list(self):
        """加载帧到列表"""
        self.frame_list.clear()
        
        for i, frame in enumerate(self.current_frames):
            try:
                # 创建缩略图
                height, width = frame.shape[:2]
                # 缩放缩略图
                thumb_width = 160
                thumb_height = int(height * thumb_width / width)
                
                frame_resized = cv2.resize(frame, (thumb_width, thumb_height))
                frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
                
                bytes_per_line = 3 * thumb_width
                qimage = QImage(frame_rgb.data, thumb_width, thumb_height, 
                               bytes_per_line, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(qimage)
                
                # 创建列表项
                item = QListWidgetItem()
                item.setIcon(QIcon(pixmap))
                item.setText(f"帧 {i+1}")
                item.setData(Qt.UserRole, i)  # 保存原始索引
                item.setTextAlignment(Qt.AlignCenter)
                item.setSizeHint(QSize(180, 150))
                
                self.frame_list.addItem(item)
            except Exception as e:
                print(f"创建缩略图失败: {e}")
        
        # 更新滑块范围
        self.frame_slider.setMaximum(max(0, len(self.current_frames) - 1))
        self._update_info()
    
    def _update_preview(self):
        """更新预览"""
        if not self.current_frames or self.current_index >= len(self.current_frames):
            return
        
        try:
            frame = self.current_frames[self.current_index]
            
            # 转换为QPixmap
            height, width = frame.shape[:2]
            bytes_per_line = 3 * width
            qimage = QImage(frame.data, width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
            
            # 缩放到预览区域
            pixmap = QPixmap.fromImage(qimage)
            label_size = self.preview_label.size()
            scaled_pixmap = pixmap.scaled(label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            self.preview_label.setPixmap(scaled_pixmap)
            
            # 更新滑块和计数器
            self.frame_slider.blockSignals(True)
            self.frame_slider.setValue(self.current_index)
            self.frame_slider.blockSignals(False)
            
            self.frame_counter.setText(f"{self.current_index + 1}/{len(self.current_frames)}")
            
            # 高亮列表中的当前项
            for i in range(self.frame_list.count()):
                item = self.frame_list.item(i)
                if item.data(Qt.UserRole) == self.current_index:
                    item.setSelected(True)
                    self.frame_list.scrollToItem(item)
                else:
                    item.setSelected(False)
                    
        except Exception as e:
            print(f"更新预览时出错: {e}")
    
    def _update_info(self):
        """更新信息显示"""
        self.frame_info_label.setText(f"总帧数: {len(self.current_frames)} | 当前帧: {self.current_index + 1}")
    
    def _on_play_toggled(self, checked):
        """播放/暂停切换"""
        if checked:
            self.is_playing = True
            self.play_btn.setText("⏸ 暂停")
            self.play_timer.start(100)  # 100ms刷新，约10fps
        else:
            self.is_playing = False
            self.play_btn.setText("▶ 播放")
            self.play_timer.stop()
    
    def _on_play_timeout(self):
        """播放定时器超时"""
        if self.current_frames:
            self.current_index = (self.current_index + 1) % len(self.current_frames)
            self._update_preview()
    
    def _on_delete_current(self):
        """删除当前帧"""
        if not self.current_frames:
            return
        
        if len(self.current_frames) <= 1:
            QMessageBox.warning(self, "警告", "至少保留一帧")
            return
        
        reply = QMessageBox.question(
            self, "确认删除", 
            f"确定要删除第 {self.current_index + 1} 帧吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            del self.current_frames[self.current_index]
            if self.current_index >= len(self.current_frames):
                self.current_index = len(self.current_frames) - 1
            
            self._load_frames_to_list()
            self._update_preview()
    
    def _on_delete_range(self):
        """删除选定范围"""
        selected_items = self.frame_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "警告", "请先选择要删除的帧")
            return
        
        if len(selected_items) >= len(self.current_frames):
            QMessageBox.warning(self, "警告", "不能删除所有帧")
            return
        
        reply = QMessageBox.question(
            self, "确认删除", 
            f"确定要删除选中的 {len(selected_items)} 帧吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 获取要删除的索引（从大到小排序，避免索引变化）
            indices_to_delete = sorted([item.data(Qt.UserRole) for item in selected_items], reverse=True)
            
            for idx in indices_to_delete:
                if idx < len(self.current_frames):
                    del self.current_frames[idx]
            
            # 调整当前索引
            if self.current_index >= len(self.current_frames):
                self.current_index = len(self.current_frames) - 1
            
            self._load_frames_to_list()
            self._update_preview()
    
    def _on_move_up(self):
        """上移当前帧"""
        if self.current_index > 0:
            # 交换帧
            self.current_frames[self.current_index], self.current_frames[self.current_index - 1] = \
                self.current_frames[self.current_index - 1], self.current_frames[self.current_index]
            
            self.current_index -= 1
            self._load_frames_to_list()
            self._update_preview()
    
    def _on_move_down(self):
        """下移当前帧"""
        if self.current_index < len(self.current_frames) - 1:
            # 交换帧
            self.current_frames[self.current_index], self.current_frames[self.current_index + 1] = \
                self.current_frames[self.current_index + 1], self.current_frames[self.current_index]
            
            self.current_index += 1
            self._load_frames_to_list()
            self._update_preview()
    
    def _on_crop_frames(self):
        """裁剪帧（简化版：提示功能）"""
        QMessageBox.information(self, "提示", "裁剪功能将在后续版本中添加")
    
    def _on_reset(self):
        """重置编辑"""
        reply = QMessageBox.question(
            self, "确认重置", 
            "确定要放弃所有编辑吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.current_frames = self.frames.copy()
            self.current_index = 0
            self._load_frames_to_list()
            self._update_preview()
    
    def _on_select_all(self):
        """全选"""
        self.frame_list.selectAll()
    
    def _on_deselect_all(self):
        """取消全选"""
        self.frame_list.clearSelection()
    
    def _on_prev_frame(self):
        """上一帧"""
        if self.current_index > 0:
            self.current_index -= 1
            self._update_preview()
    
    def _on_next_frame(self):
        """下一帧"""
        if self.current_index < len(self.current_frames) - 1:
            self.current_index += 1
            self._update_preview()
    
    def _on_slider_changed(self, value):
        """滑块值改变"""
        if 0 <= value < len(self.current_frames):
            self.current_index = value
            self._update_preview()
    
    def _on_selection_changed(self):
        """列表选择改变"""
        selected_count = len(self.frame_list.selectedItems())
        if selected_count > 0:
            self.range_label.setText(f"选择范围: {selected_count} 帧")
        else:
            self.range_label.setText("选择范围: 无")
    
    def get_edited_frames(self):
        """获取编辑后的帧"""
        return self.current_frames
    
    def closeEvent(self, event):
        """关闭事件"""
        self.play_timer.stop()
        event.accept()

# ==================== 播放器窗口 ====================
class GIFPlayerWindow(QMainWindow):
    """GIF播放器窗口"""
    
    def __init__(self, frames, fps=10, parent=None):
        super().__init__(parent)
        self.frames = frames
        self.fps = fps
        self.current_index = 0
        self.play_timer = QTimer()
        self.is_playing = False
        
        self.setWindowTitle("GIF播放器")
        self.setMinimumSize(600, 500)
        
        self._setup_ui()
        self._setup_signals()
        self._update_preview()
    
    def _setup_ui(self):
        """设置用户界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        
        # 预览标签
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(500, 400)
        self.preview_label.setStyleSheet("border: 2px solid #ddd; background-color: #2d2d2d;")
        self.preview_label.setText("加载中...")
        
        # 滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.preview_label)
        scroll_area.setWidgetResizable(True)
        scroll_area.setAlignment(Qt.AlignCenter)
        layout.addWidget(scroll_area)
        
        # 控制栏
        control_layout = QHBoxLayout()
        
        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.setCheckable(True)
        self.play_btn.setMaximumWidth(100)
        control_layout.addWidget(self.play_btn)
        
        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setMaximumWidth(100)
        control_layout.addWidget(self.stop_btn)
        
        control_layout.addStretch()
        
        self.speed_label = QLabel("播放速度:")
        control_layout.addWidget(self.speed_label)
        
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "1.0x", "1.5x", "2.0x"])
        self.speed_combo.setCurrentIndex(1)
        self.speed_combo.setMaximumWidth(80)
        control_layout.addWidget(self.speed_combo)
        
        layout.addLayout(control_layout)
        
        # 进度条
        progress_layout = QHBoxLayout()
        progress_layout.addWidget(QLabel("帧:"))
        
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(max(0, len(self.frames) - 1))
        progress_layout.addWidget(self.frame_slider)
        
        self.frame_label = QLabel(f"0/{len(self.frames)}")
        self.frame_label.setMinimumWidth(60)
        progress_layout.addWidget(self.frame_label)
        
        layout.addLayout(progress_layout)
        
        # 信息标签
        self.info_label = QLabel(f"总帧数: {len(self.frames)} | FPS: {self.fps}")
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)
    
    def _setup_signals(self):
        """设置信号连接"""
        self.play_btn.toggled.connect(self._on_play_toggled)
        self.stop_btn.clicked.connect(self._on_stop)
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        self.frame_slider.valueChanged.connect(self._on_slider_changed)
        
        self.play_timer.timeout.connect(self._on_play_timeout)
    
    def _update_preview(self):
        """更新预览"""
        if not self.frames or self.current_index >= len(self.frames):
            return
        
        try:
            frame = self.frames[self.current_index]
            
            # 转换为QPixmap
            height, width = frame.shape[:2]
            bytes_per_line = 3 * width
            qimage = QImage(frame.data, width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
            
            # 缩放到预览区域
            pixmap = QPixmap.fromImage(qimage)
            label_size = self.preview_label.size()
            scaled_pixmap = pixmap.scaled(label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            self.preview_label.setPixmap(scaled_pixmap)
            
            # 更新滑块
            self.frame_slider.blockSignals(True)
            self.frame_slider.setValue(self.current_index)
            self.frame_slider.blockSignals(False)
            
            self.frame_label.setText(f"{self.current_index + 1}/{len(self.frames)}")
            
        except Exception as e:
            print(f"更新预览时出错: {e}")
    
    def _on_play_toggled(self, checked):
        """播放/暂停切换"""
        if checked:
            self.is_playing = True
            self.play_btn.setText("⏸ 暂停")
            
            # 根据速度设置定时器间隔
            speed_factor = float(self.speed_combo.currentText().replace('x', ''))
            interval = int(1000 / (self.fps * speed_factor))
            self.play_timer.start(interval)
        else:
            self.is_playing = False
            self.play_btn.setText("▶ 播放")
            self.play_timer.stop()
    
    def _on_stop(self):
        """停止播放"""
        self.play_btn.setChecked(False)
        self.current_index = 0
        self._update_preview()
    
    def _on_play_timeout(self):
        """播放定时器超时"""
        if self.frames:
            self.current_index = (self.current_index + 1) % len(self.frames)
            self._update_preview()
    
    def _on_speed_changed(self, index):
        """速度改变"""
        if self.is_playing:
            # 重新启动定时器以应用新速度
            self.play_btn.setChecked(False)
            self.play_btn.setChecked(True)
    
    def _on_slider_changed(self, value):
        """滑块值改变"""
        if 0 <= value < len(self.frames):
            self.current_index = value
            self._update_preview()
    
    def closeEvent(self, event):
        """关闭事件"""
        self.play_timer.stop()
        event.accept()

# ==================== GIF编码线程 ====================
class GIFEncodingThread(QThread):
    """GIF编码处理线程"""
    progress_updated = Signal(int)
    status_updated = Signal(str)
    encoding_finished = Signal(str)
    encoding_error = Signal(str)
    
    def __init__(self, frames, output_path, fps, scale_percent, quality, colors):
        super().__init__()
        self.frames = frames
        self.output_path = output_path
        self.fps = fps
        self.scale_percent = scale_percent
        self.quality = quality
        self.colors = colors
        self.is_running = True
        
    def run(self):
        """线程运行主函数"""
        try:
            if not self.frames:
                self.encoding_error.emit("没有捕获到任何帧")
                return
            
            self.status_updated.emit("正在处理图像...")
            processed_frames = []
            total_frames = len(self.frames)
            
            # 处理每一帧
            for i, frame in enumerate(self.frames):
                if not self.is_running:
                    return
                
                try:
                    # 缩放处理
                    if self.scale_percent != 100:
                        width = int(frame.shape[1] * self.scale_percent / 100)
                        height = int(frame.shape[0] * self.scale_percent / 100)
                        frame = cv2.resize(frame, (width, height))
                    
                    # BGR转RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    processed_frames.append(frame_rgb)
                except Exception as e:
                    print(f"处理帧 {i} 时出错: {e}")
                    continue
                
                # 更新进度
                progress = int((i + 1) / total_frames * 40)
                self.progress_updated.emit(progress)
            
            if not processed_frames:
                self.encoding_error.emit("没有有效的帧可以处理")
                return
            
            self.status_updated.emit("正在生成GIF...")
            
            # 转换为PIL Image列表
            pil_frames = []
            for frame in processed_frames:
                try:
                    pil_img = Image.fromarray(frame)
                    pil_frames.append(pil_img)
                except Exception as e:
                    print(f"转换为PIL图像时出错: {e}")
                    continue
            
            if not pil_frames:
                self.encoding_error.emit("无法创建PIL图像")
                return
            
            # 保存为GIF
            # 计算每帧持续时间（毫秒）
            duration = int(1000 / self.fps)
            
            # 优化调色板
            if self.colors < 256:
                self.status_updated.emit("正在优化颜色...")
                paletted_frames = []
                for i, frame in enumerate(pil_frames):
                    if not self.is_running:
                        return
                    try:
                        # 转换为P调色板模式
                        frame_p = frame.convert('P', palette=Image.ADAPTIVE, colors=self.colors)
                        paletted_frames.append(frame_p)
                    except Exception as e:
                        print(f"优化颜色时出错: {e}")
                        paletted_frames.append(frame)
                    
                    progress = 40 + int((i + 1) / len(pil_frames) * 40)
                    self.progress_updated.emit(progress)
                
                pil_frames = paletted_frames
            
            # 保存GIF
            try:
                pil_frames[0].save(
                    self.output_path,
                    save_all=True,
                    append_images=pil_frames[1:],
                    duration=duration,
                    loop=0,
                    quality=self.quality,
                    optimize=True
                )
                
                self.progress_updated.emit(100)
                self.status_updated.emit("GIF生成完成")
                self.encoding_finished.emit(self.output_path)
            except Exception as e:
                self.encoding_error.emit(f"保存GIF失败: {str(e)}")
            
        except Exception as e:
            self.encoding_error.emit(f"编码失败: {str(e)}")
            traceback.print_exc()
    
    def stop(self):
        """停止线程"""
        self.is_running = False

# ==================== 屏幕捕获线程 ====================
class ScreenCaptureThread(QThread):
    """屏幕捕获线程"""
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
        self.target_fps = 15  # 默认捕获帧率
        
    def run(self):
        """线程运行主函数"""
        try:
            self.is_running = True
            self.capture_event.set()
            
            # 获取屏幕
            screen = QApplication.primaryScreen()
            if not screen:
                self.capture_error.emit("无法获取屏幕")
                return
            
            frame_interval = 1.0 / self.target_fps  # 帧间隔（秒）
            
            while self.is_running:
                if self.paused:
                    self.msleep(100)
                    continue
                
                if not self.capture_event.is_set():
                    break
                
                try:
                    # 控制捕获帧率
                    current_time = time.time()
                    if current_time - self.last_capture_time < frame_interval:
                        self.msleep(1)
                        continue
                    
                    # 捕获屏幕区域
                    pixmap = screen.grabWindow(0, 
                                             self.capture_rect.x(),
                                             self.capture_rect.y(),
                                             self.capture_rect.width(),
                                             self.capture_rect.height())
                    
                    # 转换为QImage
                    qimage = pixmap.toImage()
                    
                    # 检查图像是否有效
                    if qimage.isNull():
                        self.msleep(10)
                        continue
                    
                    width = qimage.width()
                    height = qimage.height()
                    
                    if width <= 0 or height <= 0:
                        self.msleep(10)
                        continue
                    
                    # 将QImage转换为numpy数组
                    ptr = qimage.constBits()
                    
                    # 根据QImage格式创建数组
                    if qimage.format() == QImage.Format_ARGB32 or qimage.format() == QImage.Format_RGB32:
                        # ARGB32格式，每个像素4字节
                        arr = np.array(ptr, copy=True).reshape(height, width, 4)
                        # 转换为BGR格式（OpenCV使用）
                        frame = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
                    else:
                        # 其他格式，转换为RGB888
                        qimage_rgb = qimage.convertToFormat(QImage.Format_RGB888)
                        ptr_rgb = qimage_rgb.constBits()
                        arr = np.array(ptr_rgb, copy=True).reshape(height, width, 3)
                        # RGB转BGR
                        frame = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                    
                    self.frames.append(frame)
                    
                    # 发送帧用于预览
                    self.frame_captured.emit(frame)
                    
                    self.last_capture_time = current_time
                    
                except Exception as e:
                    print(f"捕获单帧时出错: {e}")
                    traceback.print_exc()
                    self.msleep(10)
                
        except Exception as e:
            self.capture_error.emit(f"捕获失败: {str(e)}")
            traceback.print_exc()
        finally:
            self.capture_finished.emit()
    
    def stop(self):
        """停止捕获"""
        self.is_running = False
        self.capture_event.clear()
    
    def pause(self):
        """暂停捕获"""
        self.paused = True
    
    def resume(self):
        """恢复捕获"""
        self.paused = False
    
    def get_frames(self):
        """获取捕获的帧"""
        return self.frames.copy()
    
    def clear_frames(self):
        """清除帧"""
        self.frames.clear()
    
    def set_target_fps(self, fps):
        """设置目标帧率"""
        self.target_fps = max(1, min(fps, 30))

# ==================== 区域选择窗口 ====================
class RegionSelectionWindow(QWidget):
    """屏幕区域选择窗口"""
    region_selected = Signal(QRect)
    
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint | 
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
        # 获取所有屏幕的联合几何体
        self.screen_geometry = self._get_virtual_desktop_geometry()
        self.setGeometry(self.screen_geometry)
        
        self.start_point = None
        self.end_point = None
        self.is_selecting = False
        
        # 设置光标
        self.setCursor(QCursor(Qt.CrossCursor))
        
        # 半透明遮罩颜色
        self.mask_color = QColor(0, 0, 0, 100)
        self.selection_color = QColor(0, 120, 215, 50)
        self.border_color = QColor(0, 120, 215)
        
        # 提示信息
        self.show_instructions = True
        
    def _get_virtual_desktop_geometry(self) -> QRect:
        """获取虚拟桌面的几何区域（所有屏幕的组合）"""
        geometry = QRect()
        for screen in QApplication.screens():
            geometry = geometry.united(screen.geometry())
        return geometry
    
    def paintEvent(self, event):
        """绘制遮罩和选择区域"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制半透明遮罩
        painter.fillRect(self.rect(), self.mask_color)
        
        if self.start_point and self.end_point:
            # 计算选择区域
            rect = QRect(self.start_point, self.end_point).normalized()
            
            # 清除选择区域的遮罩
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(rect, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            
            # 绘制选择区域边框
            pen = QPen(self.border_color, 2)
            pen.setStyle(Qt.SolidLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(self.selection_color))
            painter.drawRect(rect)
            
            # 绘制尺寸信息
            if rect.width() > 50 and rect.height() > 30:
                info_text = f"{rect.width()} × {rect.height()}"
                painter.setPen(QPen(Qt.white))
                painter.setFont(QFont("Microsoft YaHei", 9))
                painter.drawText(
                    rect.topLeft() + QPoint(5, -5),
                    info_text
                )
        
        if self.show_instructions and not self.is_selecting:
            # 绘制使用说明
            painter.setPen(QPen(Qt.white))
            painter.setFont(QFont("Microsoft YaHei", 12))
            instructions = "拖动鼠标选择录制区域 | 按 ESC 取消"
            text_rect = painter.fontMetrics().boundingRect(instructions)
            text_rect.moveCenter(self.rect().center())
            painter.drawText(text_rect, instructions)
    
    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.LeftButton:
            self.start_point = event.position().toPoint()
            self.end_point = self.start_point
            self.is_selecting = True
            self.show_instructions = False
            self.update()
    
    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        if self.is_selecting:
            self.end_point = event.position().toPoint()
            self.update()
    
    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        if event.button() == Qt.LeftButton and self.is_selecting:
            self.end_point = event.position().toPoint()
            self.is_selecting = False
            
            rect = QRect(self.start_point, self.end_point).normalized()
            if rect.width() > 10 and rect.height() > 10:
                self.region_selected.emit(rect)
            self.close()
    
    def keyPressEvent(self, event):
        """键盘按下事件"""
        if event.key() == Qt.Key_Escape:
            self.close()
    
    def showEvent(self, event):
        """窗口显示事件"""
        super().showEvent(event)
        self.show_instructions = True
        self.start_point = None
        self.end_point = None
        self.is_selecting = False
        self.update()

# ==================== 主窗口类 ====================
class ScreenToGIFMainWindow(QMainWindow):
    """屏幕录制转GIF主窗口"""
    
    def __init__(self):
        super().__init__()
        # 配置文件放在程序所在目录
        program_dir = os.path.dirname(sys.argv[0])
        self.config_file = os.path.join(program_dir, "screentogif_config.json")
        self.config = AppConfig.load_from_file(self.config_file)
        
        # 确保输出目录存在
        os.makedirs(self.config.output_directory, exist_ok=True)
        
        self.selection_window = None
        self.capture_thread = None
        self.encode_thread = None
        self.capture_rect = None
        self.captured_frames = []
        self.preview_timer = QTimer()
        self.preview_index = 0
        self.is_recording = False
        self.last_frame_time = 0
        self.frame_count = 0
        self.player_window = None
        self.editor_dialog = None
        
        self._setup_ui()
        self._load_config()
        self._check_icon()
        self._setup_signals()
        
        # 恢复窗口位置
        if hasattr(self.config, 'window_x') and hasattr(self.config, 'window_y'):
            self.move(self.config.window_x, self.config.window_y)
        if hasattr(self.config, 'window_width') and hasattr(self.config, 'window_height'):
            self.resize(self.config.window_width, self.config.window_height)
    
    def _setup_ui(self):
        """设置用户界面"""
        self.setWindowTitle("屏幕录制转GIF工具 - 增强版")
        self.setMinimumSize(900, 700)
        
        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # 创建菜单栏
        self._create_menu_bar()
        
        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setChildrenCollapsible(False)
        
        # ===== 左侧控制面板 =====
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(10)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 录制控制组
        control_group = QGroupBox("录制控制")
        control_layout = QGridLayout(control_group)
        control_layout.setVerticalSpacing(10)
        
        # 选择区域按钮
        self.select_region_btn = QPushButton("选择录制区域")
        self.select_region_btn.setMinimumHeight(40)
        self.select_region_btn.setObjectName("primary_button")
        control_layout.addWidget(self.select_region_btn, 0, 0, 1, 2)
        
        # 开始/停止按钮
        self.start_capture_btn = QPushButton("开始录制")
        self.start_capture_btn.setMinimumHeight(40)
        self.start_capture_btn.setEnabled(False)
        self.start_capture_btn.setObjectName("success_button")
        
        self.stop_capture_btn = QPushButton("停止录制")
        self.stop_capture_btn.setMinimumHeight(40)
        self.stop_capture_btn.setEnabled(False)
        self.stop_capture_btn.setObjectName("danger_button")
        
        control_layout.addWidget(self.start_capture_btn, 1, 0)
        control_layout.addWidget(self.stop_capture_btn, 1, 1)
        
        # 区域信息
        self.region_info_label = QLabel("未选择区域")
        self.region_info_label.setAlignment(Qt.AlignCenter)
        self.region_info_label.setMinimumHeight(30)
        self.region_info_label.setStyleSheet("background-color: #f0f0f0; border-radius: 5px; padding: 5px;")
        control_layout.addWidget(self.region_info_label, 2, 0, 1, 2)
        
        left_layout.addWidget(control_group)
        
        # 录制设置组
        settings_group = QGroupBox("录制设置")
        settings_layout = QGridLayout(settings_group)
        settings_layout.setVerticalSpacing(10)
        
        # FPS设置
        settings_layout.addWidget(QLabel("帧率 (FPS):"), 0, 0)
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 30)
        self.fps_spin.setValue(self.config.fps)
        self.fps_spin.setSuffix(" fps")
        self.fps_spin.setToolTip("每秒捕获的帧数，值越大GIF越流畅但文件越大")
        settings_layout.addWidget(self.fps_spin, 0, 1)
        
        # 缩放比例
        settings_layout.addWidget(QLabel("缩放比例:"), 1, 0)
        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(10, 200)
        self.scale_spin.setValue(self.config.scale_percent)
        self.scale_spin.setSuffix(" %")
        self.scale_spin.setToolTip("输出GIF的缩放比例，100%为原始大小")
        settings_layout.addWidget(self.scale_spin, 1, 1)
        
        # GIF质量
        settings_layout.addWidget(QLabel("GIF质量:"), 2, 0)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(self.config.quality)
        self.quality_spin.setSuffix(" %")
        self.quality_spin.setToolTip("GIF压缩质量，越高画质越好但文件越大")
        settings_layout.addWidget(self.quality_spin, 2, 1)
        
        # 颜色数
        settings_layout.addWidget(QLabel("颜色数:"), 3, 0)
        self.colors_spin = QSpinBox()
        self.colors_spin.setRange(2, 256)
        self.colors_spin.setValue(self.config.colors)
        self.colors_spin.setSuffix(" 色")
        self.colors_spin.setToolTip("使用的颜色数量，越少文件越小但画质越差")
        settings_layout.addWidget(self.colors_spin, 3, 1)
        
        # 自动开始录制
        self.auto_start_check = QCheckBox("选择区域后自动开始录制")
        self.auto_start_check.setChecked(self.config.auto_start)
        settings_layout.addWidget(self.auto_start_check, 4, 0, 1, 2)
        
        # 显示预览
        self.show_preview_check = QCheckBox("显示实时预览")
        self.show_preview_check.setChecked(self.config.show_preview)
        settings_layout.addWidget(self.show_preview_check, 5, 0, 1, 2)
        
        left_layout.addWidget(settings_group)
        
        # 输出设置组
        output_group = QGroupBox("输出设置")
        output_layout = QGridLayout(output_group)
        output_layout.setVerticalSpacing(10)
        
        # 输出目录（只读显示）
        output_layout.addWidget(QLabel("输出目录:"), 0, 0)
        
        self.output_dir_label = QLabel(self.config.output_directory)
        self.output_dir_label.setWordWrap(True)
        self.output_dir_label.setStyleSheet("background-color: #f0f0f0; padding: 5px; border-radius: 3px;")
        output_layout.addWidget(self.output_dir_label, 0, 1)
        
        self.open_output_dir_btn = QPushButton("打开文件夹")
        self.open_output_dir_btn.setMaximumWidth(100)
        output_layout.addWidget(self.open_output_dir_btn, 1, 0)
        
        left_layout.addWidget(output_group)
        
        # 录制后操作组
        post_group = QGroupBox("录制后操作")
        post_layout = QGridLayout(post_group)
        post_layout.setVerticalSpacing(10)
        
        # 播放按钮
        self.play_btn = QPushButton("▶ 播放录制")
        self.play_btn.setMinimumHeight(35)
        self.play_btn.setEnabled(False)
        self.play_btn.setObjectName("info_button")
        self.play_btn.setToolTip("播放当前录制的帧")
        post_layout.addWidget(self.play_btn, 0, 0)
        
        # 编辑按钮
        self.edit_btn = QPushButton("✎ 编辑帧")
        self.edit_btn.setMinimumHeight(35)
        self.edit_btn.setEnabled(False)
        self.edit_btn.setObjectName("warning_button")
        self.edit_btn.setToolTip("编辑录制的帧（删除、调整顺序等）")
        post_layout.addWidget(self.edit_btn, 0, 1)
        
        # 生成按钮
        self.generate_gif_btn = QPushButton("生成GIF")
        self.generate_gif_btn.setMinimumHeight(40)
        self.generate_gif_btn.setEnabled(False)
        self.generate_gif_btn.setObjectName("primary_button")
        self.generate_gif_btn.setToolTip("将录制的帧生成为GIF文件")
        post_layout.addWidget(self.generate_gif_btn, 1, 0, 1, 2)
        
        left_layout.addWidget(post_group)
        
        # 进度条组
        progress_group = QGroupBox("处理进度")
        progress_layout = QVBoxLayout(progress_group)
        
        # 状态标签
        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setMinimumHeight(30)
        progress_layout.addWidget(self.status_label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        progress_layout.addWidget(self.progress_bar)
        
        left_layout.addWidget(progress_group)
        
        # 添加弹性空间
        left_layout.addStretch()
        
        # ===== 右侧预览面板 =====
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(10)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # 预览标签组
        preview_group = QGroupBox("实时预览")
        preview_layout = QVBoxLayout(preview_group)
        
        # 预览标签
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(400, 300)
        self.preview_label.setStyleSheet("border: 2px solid #ddd; background-color: #2d2d2d; color: white;")
        self.preview_label.setText("等待开始录制...")
        
        # 使用滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.preview_label)
        scroll_area.setWidgetResizable(True)
        scroll_area.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(scroll_area)
        
        right_layout.addWidget(preview_group)
        
        # 帧信息
        self.frames_info_label = QLabel("已捕获: 0 帧")
        self.frames_info_label.setAlignment(Qt.AlignRight)
        self.frames_info_label.setMinimumHeight(30)
        right_layout.addWidget(self.frames_info_label)
        
        # 录制历史
        history_group = QGroupBox("最近录制")
        history_layout = QVBoxLayout(history_group)
        
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(120)
        self.history_list.itemDoubleClicked.connect(self._on_history_item_clicked)
        history_layout.addWidget(self.history_list)
        
        right_layout.addWidget(history_group)
        
        # 添加面板到分割器
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 500])
        
        main_layout.addWidget(splitter)
        
        # 状态栏
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("就绪")
        
        # 应用样式表
        self._apply_styles()
        
        # 刷新历史记录
        self._refresh_history()
    
    def _create_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        open_folder_action = QAction("打开输出文件夹", self)
        open_folder_action.triggered.connect(self._on_open_output_folder)
        file_menu.addAction(open_folder_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 编辑菜单
        edit_menu = menubar.addMenu("编辑")
        
        clear_frames_action = QAction("清除所有帧", self)
        clear_frames_action.triggered.connect(self._on_clear_frames)
        edit_menu.addAction(clear_frames_action)
        
        # 视图菜单
        view_menu = menubar.addMenu("视图")
        
        always_on_top_action = QAction("窗口置顶", self)
        always_on_top_action.setCheckable(True)
        always_on_top_action.triggered.connect(self._on_toggle_always_on_top)
        view_menu.addAction(always_on_top_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)
    
    def _apply_styles(self):
        """应用样式表"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #ddd;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                border: none;
                border-radius: 5px;
                padding: 8px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#primary_button {
                background-color: #0078d4;
                color: white;
            }
            QPushButton#primary_button:hover {
                background-color: #005a9e;
            }
            QPushButton#primary_button:pressed {
                background-color: #004578;
            }
            QPushButton#success_button {
                background-color: #28a745;
                color: white;
            }
            QPushButton#success_button:hover {
                background-color: #218838;
            }
            QPushButton#success_button:pressed {
                background-color: #1e7e34;
            }
            QPushButton#danger_button {
                background-color: #dc3545;
                color: white;
            }
            QPushButton#danger_button:hover {
                background-color: #c82333;
            }
            QPushButton#danger_button:pressed {
                background-color: #bd2130;
            }
            QPushButton#info_button {
                background-color: #17a2b8;
                color: white;
            }
            QPushButton#info_button:hover {
                background-color: #138496;
            }
            QPushButton#warning_button {
                background-color: #ffc107;
                color: black;
            }
            QPushButton#warning_button:hover {
                background-color: #e0a800;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QSpinBox, QLineEdit, QComboBox {
                padding: 5px;
                border: 1px solid #ddd;
                border-radius: 4px;
                min-height: 20px;
                background-color: white;
            }
            QSpinBox:focus, QLineEdit:focus, QComboBox:focus {
                border-color: #0078d4;
                outline: none;
            }
            QProgressBar {
                border: 2px solid #ddd;
                border-radius: 5px;
                text-align: center;
                min-height: 25px;
            }
            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 3px;
            }
            QCheckBox {
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox::indicator:unchecked {
                border: 1px solid #ddd;
                background-color: white;
            }
            QCheckBox::indicator:checked {
                background-color: #0078d4;
                border: 1px solid #0078d4;
            }
            QScrollArea {
                border: none;
                background-color: #f5f5f5;
            }
            QLabel {
                color: #333333;
            }
            QSplitter::handle {
                background-color: #ddd;
            }
            QSplitter::handle:hover {
                background-color: #0078d4;
            }
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
            }
            QListWidget::item:hover {
                background-color: #e6f2ff;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
                color: white;
            }
        """)
    
    def _setup_signals(self):
        """设置信号连接"""
        self.select_region_btn.clicked.connect(self._on_select_region)
        self.start_capture_btn.clicked.connect(self._on_start_capture)
        self.stop_capture_btn.clicked.connect(self._on_stop_capture)
        self.open_output_dir_btn.clicked.connect(self._on_open_output_folder)
        self.generate_gif_btn.clicked.connect(self._on_generate_gif)
        self.play_btn.clicked.connect(self._on_play_recording)
        self.edit_btn.clicked.connect(self._on_edit_frames)
        
        # 设置改变保存
        self.fps_spin.valueChanged.connect(self._save_config)
        self.scale_spin.valueChanged.connect(self._save_config)
        self.quality_spin.valueChanged.connect(self._save_config)
        self.colors_spin.valueChanged.connect(self._save_config)
        self.auto_start_check.stateChanged.connect(self._save_config)
        self.show_preview_check.stateChanged.connect(self._save_config)
        
        # 预览定时器
        self.preview_timer.timeout.connect(self._update_preview)
    
    def _check_icon(self):
        """检查并设置图标"""
        icon_path = os.path.join(os.path.dirname(sys.argv[0]), "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.setWindowIcon(QIcon(icon_path))
            except Exception as e:
                print(f"设置图标失败: {e}")
    
    def _load_config(self):
        """加载配置到界面"""
        try:
            # 确保输出目录存在
            os.makedirs(self.config.output_directory, exist_ok=True)
            self.output_dir_label.setText(self.config.output_directory)
            
            # 恢复上次选择的区域
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
        except Exception as e:
            print(f"加载配置失败: {e}")
    
    def _save_config(self):
        """保存界面配置到文件"""
        try:
            self.config.fps = self.fps_spin.value()
            self.config.scale_percent = self.scale_spin.value()
            self.config.quality = self.quality_spin.value()
            self.config.colors = self.colors_spin.value()
            self.config.auto_start = self.auto_start_check.isChecked()
            self.config.show_preview = self.show_preview_check.isChecked()
            self.config.window_x = self.x()
            self.config.window_y = self.y()
            self.config.window_width = self.width()
            self.config.window_height = self.height()
            
            if self.capture_rect:
                self.config.last_selection = {
                    'x': self.capture_rect.x(),
                    'y': self.capture_rect.y(),
                    'width': self.capture_rect.width(),
                    'height': self.capture_rect.height()
                }
            
            self.config.save_to_file(self.config_file)
        except Exception as e:
            print(f"保存配置失败: {e}")
    
    def _refresh_history(self):
        """刷新历史记录"""
        self.history_list.clear()
        
        try:
            output_dir = self.config.output_directory
            if os.path.exists(output_dir):
                # 获取所有gif文件，按修改时间排序
                gif_files = []
                for file in os.listdir(output_dir):
                    if file.lower().endswith('.gif'):
                        file_path = os.path.join(output_dir, file)
                        mod_time = os.path.getmtime(file_path)
                        gif_files.append((mod_time, file, file_path))
                
                # 按时间倒序排序
                gif_files.sort(reverse=True)
                
                # 显示最近10个
                for mod_time, file, file_path in gif_files[:10]:
                    dt = datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M")
                    item_text = f"{file} ({dt})"
                    item = QListWidgetItem(item_text)
                    item.setData(Qt.UserRole, file_path)
                    self.history_list.addItem(item)
        except Exception as e:
            print(f"刷新历史记录失败: {e}")
    
    def _on_select_region(self):
        """选择录制区域"""
        self.selection_window = RegionSelectionWindow()
        self.selection_window.region_selected.connect(self._on_region_selected)
        self.selection_window.show()
        
        # 最小化主窗口以便选择
        self.showMinimized()
    
    def _on_region_selected(self, rect):
        """区域选择完成"""
        self.capture_rect = rect
        self.region_info_label.setText(f"区域: {rect.width()} × {rect.height()}")
        
        # 保存区域信息
        self._save_config()
        
        # 启用开始按钮
        self.start_capture_btn.setEnabled(True)
        
        # 恢复窗口
        self.showNormal()
        self.activateWindow()
        
        # 如果勾选了自动开始，直接开始录制
        if self.auto_start_check.isChecked():
            self._on_start_capture()
    
    def _on_start_capture(self):
        """开始录制"""
        if not self.capture_rect:
            QMessageBox.warning(self, "警告", "请先选择录制区域")
            return
        
        # 重置状态
        self.captured_frames = []
        self.preview_index = 0
        self.progress_bar.setValue(0)
        self.is_recording = True
        self.last_frame_time = time.time()
        self.frame_count = 0
        
        # 更新按钮状态
        self.select_region_btn.setEnabled(False)
        self.start_capture_btn.setEnabled(False)
        self.stop_capture_btn.setEnabled(True)
        self.generate_gif_btn.setEnabled(False)
        self.play_btn.setEnabled(False)
        self.edit_btn.setEnabled(False)
        
        # 创建并启动捕获线程
        self.capture_thread = ScreenCaptureThread(self.capture_rect)
        self.capture_thread.set_target_fps(self.fps_spin.value())
        self.capture_thread.frame_captured.connect(self._on_frame_captured)
        self.capture_thread.capture_finished.connect(self._on_capture_finished)
        self.capture_thread.capture_error.connect(self._on_capture_error)
        
        self.capture_thread.start()
        
        self._update_status("正在录制...")
        
        # 启动预览定时器
        if self.show_preview_check.isChecked():
            self.preview_timer.start(100)  # 100ms刷新预览
    
    def _on_stop_capture(self):
        """停止录制"""
        self.is_recording = False
        
        if self.capture_thread:
            self.capture_thread.stop()
            self.capture_thread.wait(1000)
            self.capture_thread = None
        
        self.preview_timer.stop()
        
        # 更新按钮状态
        self.select_region_btn.setEnabled(True)
        self.start_capture_btn.setEnabled(True)
        self.stop_capture_btn.setEnabled(False)
        
        # 如果有捕获的帧，启用相关按钮
        if self.captured_frames:
            self.generate_gif_btn.setEnabled(True)
            self.play_btn.setEnabled(True)
            self.edit_btn.setEnabled(True)
            self._update_status(f"录制完成，共捕获 {len(self.captured_frames)} 帧")
        else:
            self._update_status("未捕获到任何帧")
    
    def _on_frame_captured(self, frame):
        """帧捕获回调"""
        if self.is_recording:
            self.captured_frames.append(frame)
            self.frame_count += 1
            self.frames_info_label.setText(f"已捕获: {len(self.captured_frames)} 帧")
    
    def _on_capture_finished(self):
        """捕获完成回调"""
        pass
    
    def _on_capture_error(self, error_msg):
        """捕获错误回调"""
        QMessageBox.critical(self, "错误", f"捕获出错: {error_msg}")
        self._on_stop_capture()
    
    def _update_preview(self):
        """更新预览"""
        if not self.captured_frames or not self.show_preview_check.isChecked():
            return
        
        try:
            # 循环显示帧
            if self.preview_index >= len(self.captured_frames):
                self.preview_index = 0
            
            frame = self.captured_frames[self.preview_index]
            
            # 转换为QPixmap
            height, width = frame.shape[:2]
            bytes_per_line = 3 * width
            qimage = QImage(frame.data, width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
            
            # 缩放到预览区域
            pixmap = QPixmap.fromImage(qimage)
            label_size = self.preview_label.size()
            scaled_pixmap = pixmap.scaled(label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            self.preview_label.setPixmap(scaled_pixmap)
            self.preview_index += 1
        except Exception as e:
            print(f"更新预览时出错: {e}")
            traceback.print_exc()
    
    def _on_play_recording(self):
        """播放录制的帧"""
        if not self.captured_frames:
            QMessageBox.warning(self, "警告", "没有可播放的帧")
            return
        
        # 关闭已存在的播放器
        if self.player_window and self.player_window.isVisible():
            self.player_window.close()
        
        # 创建新的播放器
        self.player_window = GIFPlayerWindow(
            self.captured_frames.copy(),
            self.fps_spin.value(),
            self
        )
        self.player_window.show()
    
    def _on_edit_frames(self):
        """编辑帧"""
        if not self.captured_frames:
            QMessageBox.warning(self, "警告", "没有可编辑的帧")
            return
        
        # 创建编辑器对话框
        self.editor_dialog = FrameEditorDialog(self.captured_frames, self)
        
        # 如果用户点击确定，更新帧
        if self.editor_dialog.exec() == QDialog.Accepted:
            edited_frames = self.editor_dialog.get_edited_frames()
            
            # 如果有变化
            if len(edited_frames) != len(self.captured_frames):
                self.captured_frames = edited_frames
                self.frames_info_label.setText(f"已捕获: {len(self.captured_frames)} 帧 (已编辑)")
                self._update_status(f"编辑完成，当前 {len(self.captured_frames)} 帧")
                
                # 更新预览
                self.preview_index = 0
                self._update_preview()
    
    def _on_clear_frames(self):
        """清除所有帧"""
        if self.captured_frames:
            reply = QMessageBox.question(
                self, "确认清除",
                "确定要清除所有录制的帧吗？",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.captured_frames = []
                self.frames_info_label.setText("已捕获: 0 帧")
                self.preview_label.clear()
                self.preview_label.setText("等待开始录制...")
                self.generate_gif_btn.setEnabled(False)
                self.play_btn.setEnabled(False)
                self.edit_btn.setEnabled(False)
                self._update_status("已清除所有帧")
    
    def _on_generate_gif(self):
        """生成GIF"""
        if not self.captured_frames:
            QMessageBox.warning(self, "警告", "没有可用的帧，请先录制")
            return
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"screen_recording_{timestamp}.gif"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存GIF文件",
            os.path.join(self.config.output_directory, default_filename),
            "GIF文件 (*.gif)"
        )
        
        if not file_path:
            return
        
        # 更新按钮状态
        self.generate_gif_btn.setEnabled(False)
        self.select_region_btn.setEnabled(False)
        self.start_capture_btn.setEnabled(False)
        self.play_btn.setEnabled(False)
        self.edit_btn.setEnabled(False)
        
        # 创建编码线程
        self.encode_thread = GIFEncodingThread(
            self.captured_frames.copy(),
            file_path,
            self.fps_spin.value(),
            self.scale_spin.value(),
            self.quality_spin.value(),
            self.colors_spin.value()
        )
        
        self.encode_thread.progress_updated.connect(self.progress_bar.setValue)
        self.encode_thread.status_updated.connect(self._update_status)
        self.encode_thread.encoding_finished.connect(self._on_encoding_finished)
        self.encode_thread.encoding_error.connect(self._on_encoding_error)
        
        self.encode_thread.start()
        
        self._update_status("正在生成GIF...")
    
    def _on_encoding_finished(self, file_path):
        """编码完成回调"""
        self.progress_bar.setValue(100)
        self._update_status(f"GIF已保存: {os.path.basename(file_path)}")
        
        # 恢复按钮状态
        self.generate_gif_btn.setEnabled(True)
        self.select_region_btn.setEnabled(True)
        self.start_capture_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.edit_btn.setEnabled(True)
        
        # 刷新历史记录
        self._refresh_history()
        
        # 询问是否打开文件位置
        reply = QMessageBox.question(
            self,
            "完成",
            f"GIF已保存到:\n{file_path}\n\n是否打开所在文件夹？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self._open_file_location(file_path)
    
    def _on_encoding_error(self, error_msg):
        """编码错误回调"""
        QMessageBox.critical(self, "错误", f"生成GIF失败:\n{error_msg}")
        
        # 恢复按钮状态
        self.generate_gif_btn.setEnabled(True)
        self.select_region_btn.setEnabled(True)
        self.start_capture_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.edit_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self._update_status("生成失败")
    
    def _on_open_output_folder(self):
        """打开输出文件夹"""
        try:
            output_dir = self.config.output_directory
            if os.path.exists(output_dir):
                QDesktopServices.openUrl(QUrl.fromLocalFile(output_dir))
            else:
                QMessageBox.warning(self, "警告", "输出文件夹不存在")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开文件夹: {e}")
    
    def _on_history_item_clicked(self, item):
        """历史记录项双击"""
        file_path = item.data(Qt.UserRole)
        if file_path and os.path.exists(file_path):
            self._open_file_location(file_path)
    
    def _on_toggle_always_on_top(self, checked):
        """切换窗口置顶"""
        if checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()
    
    def _on_about(self):
        """关于对话框"""
        QMessageBox.about(
            self,
            "关于屏幕录制转GIF工具",
            f"""<h2>屏幕录制转GIF工具 增强版</h2>
            <p>版本: 2.0</p>
            <p>一个简单易用的屏幕区域录制转GIF工具。</p>
            <p>功能特点：</p>
            <ul>
                <li>支持选择任意屏幕区域</li>
                <li>可调节帧率、缩放比例和颜色数</li>
                <li>录制后播放和编辑功能</li>
                <li>多线程处理，界面不卡顿</li>
                <li>自动保存配置</li>
            </ul>
            <p>输出目录: {self.config.output_directory}</p>"""
        )
    
    def _open_file_location(self, file_path):
        """打开文件所在位置"""
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
        """更新状态信息"""
        self.status_label.setText(message)
        self.status_bar.showMessage(message)
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 停止所有线程
        if self.capture_thread and self.capture_thread.isRunning():
            self.capture_thread.stop()
            self.capture_thread.wait(2000)
        
        if self.encode_thread and self.encode_thread.isRunning():
            self.encode_thread.stop()
            self.encode_thread.wait(2000)
        
        # 关闭播放器和编辑器
        if self.player_window and self.player_window.isVisible():
            self.player_window.close()
        
        if self.editor_dialog and self.editor_dialog.isVisible():
            self.editor_dialog.close()
        
        # 保存配置
        self._save_config()
        
        event.accept()

# ==================== 程序入口 ====================
def main():
    """主函数"""
    try:
        # 创建应用程序
        app = QApplication(sys.argv)
        app.setApplicationName("ScreenToGIF")
        app.setOrganizationName("ScreenToGIF")
        
        # 设置应用程序字体
        font = QFont("Microsoft YaHei", 9)
        app.setFont(font)
        
        # 创建并显示主窗口
        window = ScreenToGIFMainWindow()
        window.show()
        
        # 运行应用程序
        sys.exit(app.exec())
    except Exception as e:
        print(f"程序启动失败: {e}")
        traceback.print_exc()
        input("按回车键退出...")

if __name__ == "__main__":
    main()