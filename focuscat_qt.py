from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtMultimedia import QSoundEffect
import os, random, re, hashlib, colorsys, sys

# ===== Constants / 常量 =====
DEFAULT_SAVE     = "autosave.txt"       # default autosave path / 默认自动保存路径
POMODORO_MIN     = 25                   # default focus minutes / 默认番茄钟分钟数
HEARTBEAT_MS     = 200                  # UI heartbeat interval / 心跳刷新间隔
SENT_END_RE      = r"[\.!\?。！？…]+"     # sentence-end regex / 句末正则
QUOTE_ROTATE_MIN = 60                   # min quote rotate seconds / 喵语最短轮换秒
QUOTE_ROTATE_MAX = 120                  # max quote rotate seconds / 喵语最长轮换秒

THEMES = {  # theme palette / 主题配色
    "dark":    {"bg": "#181818", "fg": "#ffffff", "bar": "#202020"},
    "light":   {"bg": "#FAFAFA", "fg": "#111111", "bar": "#EFEFEF"},
    "eyecare": {"bg": "#FFF3B0", "fg": "#2b2b2b", "bar": "#FFE89A"},
}

PALETTE = [  # base colors for gradients / 渐变基色池
    "#FF6B6B", "#FFD93D", "#6BCB77", "#4D96FF", "#FF9CEE",
    "#A3E4DB", "#FFB26B", "#B983FF", "#FFC7C7", "#7DE5ED"
]

QUOTES_ZH = [  # rotating quotes (ZH) / 中文提示语
    "(｡･∀･)ﾉﾞ 喵～好棒，继续写！", "(*´∀`)♡ 再来一句！", "(⁎˃ᴗ˂⁎) 你今天状态很好喵！",
    "(ฅ'ω'ฅ)♪ 伸个懒腰，然后继续～", "(●´ω｀●) FocusCat 为你守护专注 ✨",
    "(⁎˃ᴗ˂⁎) 喝口水，眼睛休息十秒喵～", "(=^･ω･^=) 先写不完美，也很棒喵！"
]
QUOTES_EN = [  # rotating quotes (EN) / 英文提示语
    "(｡･∀･)ﾉﾞ Meow~ you're doing great!", "(*´∀`)♡ One more line, you got this!",
    "(⁎˃ᴗ˂⁎) Looking sharp today, human!", "(ฅ'ω'ฅ)♪ Stretch a bit and keep going!",
    "(●´ω｀●) FocusCat is guarding your focus ✨", "(⁎˃ᴗ˂⁎) Sip some water and relax your eyes!",
    "(=^･ω･^=) It's okay to write imperfectly first!"
]

# common abbreviations to avoid false sentence split / 常见缩写避免误判句末
ABBREVIATIONS = [
    "e.g.", "i.e.", "etc.", "vs.", "cf.", "fig.", "al.", "ca.",
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.",
    "ph.d.", "u.s.", "u.k.", "a.m.", "p.m.",
    "eg.", "ie.", "etc"  # loose forms / 常见漏点写法
]


# ===== Widgets / 组件 =====
class BgCentralWidget(QtWidgets.QWidget):
    """Central widget that draws a cover background image.
		绘制铺满的背景图的中心容器。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg_pix: QtGui.QPixmap | None = None
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)

    def set_background_image(self, path: str):
        """Set cover background image.
		设置铺满背景图。"""
        pm = QtGui.QPixmap(path)
        if pm.isNull():
            raise RuntimeError("Failed to load image / 无法加载图片")
        self._bg_pix = pm
        self.update()

    def clear_background(self):
        """Clear background image.
		清除背景图。"""
        self._bg_pix = None
        self.update()

    def paintEvent(self, e: QtGui.QPaintEvent) -> None:
        """Cover-scale draw; center-crop.
		等比放大并居中裁切。"""
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), self.palette().window())
        if self._bg_pix:
            tgt = self.rect()
            sw, sh = self._bg_pix.width(), self._bg_pix.height()
            tw, th = tgt.width(), tgt.height()
            if sw > 0 and sh > 0 and tw > 0 and th > 0:
                scale = max(tw / sw, th / sh)
                nw, nh = int(sw * scale), int(sh * scale)
                ox, oy = (nw - tw) // 2, (nh - th) // 2
                scaled = self._bg_pix.scaled(
                    nw, nh,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation
                )
                src = QtCore.QRect(ox, oy, tw, th)
                p.drawPixmap(tgt, scaled, src)
        p.end()
        super().paintEvent(e)

class ShadedTextEdit(QtWidgets.QTextEdit):
    """Text editor with fixed semi-transparent overlay rectangle.
		带固定半透明矩形底的文本编辑器（大小不随文字变化）。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.WidgetWidth)

        # --- overlay params / 黑底参数 ---
        self.overlay_enabled = True      # 是否启用
        self.overlay_alpha   = 77       # 透明度 0~255
        self.overlay_radius  = 8         # 圆角
        self.overlay_margin  = 8         # 视口四边内缩（避免贴边）
        self.overlay_extra   = 18        # 在可编辑区域基础上再向外扩一圈（保证更大于文字区域）

    def paintEvent(self, ev: QtGui.QPaintEvent) -> None:
        # 先画黑底，再交给基类画文字
        if self.overlay_enabled:
            # 以 viewport 为基准，先留一个内边距
            base_rect = self.viewport().rect().adjusted(
                self.overlay_margin, self.overlay_margin,
                -self.overlay_margin, -self.overlay_margin
            )
            # 再整体向外扩一圈，确保覆盖范围 > 文字区域
            r = base_rect.adjusted(
                -self.overlay_extra, -self.overlay_extra,
                 self.overlay_extra,  self.overlay_extra
            )
            p = QtGui.QPainter(self.viewport())
            p.setRenderHint(QtGui.QPainter.Antialiasing, True)
            path = QtGui.QPainterPath()
            path.addRoundedRect(QtCore.QRectF(r), self.overlay_radius, self.overlay_radius)
            p.fillPath(path, QtGui.QColor(0, 0, 0, int(self.overlay_alpha)))
            p.end()
        super().paintEvent(ev)

    # —— 菜单要用到的两个方法（名称保持不变）——
    def set_overlay_alpha(self, v: int):
        """set transparency 0~255
		设置透明度 0~255"""
        self.overlay_alpha = max(0, min(255, int(v)))
        self.viewport().update()

    def set_overlay_enabled(self, enabled: bool):
        """toggle shade on/off
		开关黑底"""
        self.overlay_enabled = bool(enabled)
        self.viewport().update()

    # 可选：在代码里动态微调边距/扩展量（不接菜单也行）
    def set_overlay_margins(self, margin: int = None, extra: int = None, radius: int = None):
        if margin is not None: self.overlay_margin = max(0, int(margin))
        if extra  is not None: self.overlay_extra  = max(0, int(extra))
        if radius is not None: self.overlay_radius = max(0, int(radius))
        self.viewport().update()

# ===== Main Window / 主窗体 =====
class FocusCat(QtWidgets.QMainWindow):
    """Main window.
		主窗口。"""
    def __init__(self):
        super().__init__()

        # --- Window meta / 窗口信息 ---
        self.setWindowTitle("FocusCat")
        self.resize(980, 640)
        icon_path = os.path.join(os.path.dirname(__file__), "assets", "images", "focuscat_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))

        # --- States / 状态 ---
        self.theme_key     = "dark"     # current theme / 当前主题
        self.time_left     = POMODORO_MIN * 60
        self.running       = False
        self.quote_lang    = "en"
        self._last_colored_pos = 0

        # --- Quote timer / 喵语定时器 ---
        self._quote_timer = QtCore.QTimer(self)
        self._quote_timer.setSingleShot(True)
        self._quote_timer.timeout.connect(self._rotate_quote)

        # --- Central / 中心容器(背景绘制) ---
        self.central = BgCentralWidget(self)
        self.setCentralWidget(self.central)

        # --- Sounds / 声音 ---
        self.sound_enabled    = True
        self.meow_volume      = 0.25
        self.meow_count       = 0
        self.meow_effects:    list[QSoundEffect] = []
        self.surprise_effects:list[QSoundEffect] = []
        self.surprise_prob    = 0.10  # demo probability / 演示用概率
        self._load_meow_sounds()
        self._ensure_state_dir()

        # --- Top bar / 顶部栏 ---
        top = QtWidgets.QWidget(self.central)
        top.setObjectName("topbar")
        hl  = QtWidgets.QHBoxLayout(top)
        hl.setContentsMargins(10, 6, 10, 6)

        self.lbl_timer = QtWidgets.QLabel(self._fmt_time(), top)
        self.btn_start = QtWidgets.QPushButton("▶ Start", top); self.btn_start.clicked.connect(self.start_timer)
        self.btn_pause = QtWidgets.QPushButton("⏸ Pause", top); self.btn_pause.clicked.connect(self.pause_timer)
        self.btn_reset = QtWidgets.QPushButton("↺ Reset", top); self.btn_reset.clicked.connect(self.reset_timer)
        self.lbl_quote = QtWidgets.QLabel("Meow~ ready to write?", top)

        # --- Meow button with icon / 猫头按钮（按下变脸） ---
        self.asset_dir = os.path.join(os.path.dirname(__file__), "assets")
        self.cat_img_normal  = QtGui.QPixmap(os.path.join(self.asset_dir, "images", "cat_normal.png"))
        self.cat_img_pressed = QtGui.QPixmap(os.path.join(self.asset_dir, "images", "cat_meow.png"))

        self.btn_meow = QtWidgets.QPushButton("", top)
        self.btn_meow.setFlat(True)
        self.btn_meow.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.btn_meow.setStyleSheet(
            "QPushButton{background:transparent;border:none;}"
            "QPushButton:pressed{padding-left:1px;padding-top:1px;}"
        )
        self.btn_meow.installEventFilter(self)

        self._meow_pressed = False
        self._meow_min_show_ms = 140
        self._meow_press_time = 0
        self._meow_revert_timer = QtCore.QTimer(self)
        self._meow_revert_timer.setSingleShot(True)
        self._meow_revert_timer.timeout.connect(self._revert_meow_icon)

        if not self.cat_img_normal.isNull():
            self.btn_meow.setIcon(QtGui.QIcon(self.cat_img_normal))
            self.btn_meow.setIconSize(QtCore.QSize(50, 50))
            self.btn_meow.setFixedSize(54, 54)
        else:
            self.btn_meow.setText("Meow")
            self.btn_meow.setFixedSize(84, 32)

        self.lbl_meow_count = QtWidgets.QLabel("0", top)
        self.lbl_meow_count.setMinimumWidth(24)
        self.lbl_meow_count.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self._load_meow_count()

        self.btn_save = QtWidgets.QPushButton("💾 Save", top)
        self.btn_save.clicked.connect(lambda: self.save_file(False))

        for w in (self.lbl_timer, self.btn_start, self.btn_pause, self.btn_reset, self.lbl_quote):
            hl.addWidget(w)
        hl.addStretch(1)
        hl.addWidget(self.btn_meow)
        hl.addWidget(self.lbl_meow_count)
        hl.addWidget(self.btn_save)
        self.btn_meow.setEnabled(self.sound_enabled)

        # --- Editor / 编辑器 ---
        self.editor = ShadedTextEdit(self.central)
        mono = QtGui.QFont()
        mono.setFamilies([
            "Sarasa Mono SC", "JetBrains Mono NL", "Cascadia Mono PL",
            "Microsoft YaHei UI", "Noto Sans Mono CJK SC", "Consolas"
        ])
        mono.setPointSize(16)
        mono.setStyleHint(QtGui.QFont.Monospace)
        self.editor.setFont(mono)

        # --- Layout / 布局 ---
        lay = QtWidgets.QVBoxLayout(self.central)
        lay.setContentsMargins(40, 24, 40, 24)
        lay.setSpacing(8)
        lay.addWidget(top, 0)
        lay.addWidget(self.editor, 1)

        # --- Status bar / 状态栏 ---
        self.status = self.statusBar()
        self._update_word_status()

        # --- Menus / 菜单 ---
        self._build_menus()

        # --- Theme / 主题 ---
        self._apply_theme(self.theme_key)

        # --- Autosave & heartbeat / 自动保存 + 心跳 ---
        self._autosave_timer = QtCore.QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start(15000)

        self._heartbeat = QtCore.QTimer(self)
        self._heartbeat.timeout.connect(self._heartbeat_tick)
        self._heartbeat.start(HEARTBEAT_MS)

        # --- Load default file & colorize / 载入与初次上色 ---
        self.current_file = DEFAULT_SAVE
        self._load_if_exists(DEFAULT_SAVE)
        self._colorize_all_sentences_once()

        # --- Start quote rotation / 开始喵语轮换 ---
        self._schedule_quote_rotation(immediate=True)

        # --- Default background / 默认背景 ---
        default_bg = os.path.join(os.path.dirname(__file__), "assets", "images", "bg_default.jpg")
        if os.path.exists(default_bg):
            try:
                self.central.set_background_image(default_bg)
                self.status.showMessage("Default background loaded / 默认背景已加载", 3000)
            except Exception as e:
                print(f"加载默认背景失败: {e}")

    # ===== Event filter for meow icon / 猫头像按下-松开图像切换 =====
    def eventFilter(self, obj, ev):
        if obj is self.btn_meow:
            t = ev.type()
            if t == QtCore.QEvent.Type.MouseButtonPress:
                self._meow_revert_timer.stop()
                self._set_pressed_icon()
                self.btn_meow.grabMouse()
                self._meow_pressed = True
                self._meow_press_time = QtCore.QTime.currentTime().msecsSinceStartOfDay()
                self._on_meow_clicked()
                return True
            elif t == QtCore.QEvent.Type.MouseButtonRelease:
                self.btn_meow.releaseMouse()
                now = QtCore.QTime.currentTime().msecsSinceStartOfDay()
                remain = max(0, self._meow_min_show_ms - (now - self._meow_press_time))
                self._meow_revert_timer.stop()
                (self._revert_meow_icon() if remain == 0 else self._meow_revert_timer.start(remain))
                return True
            elif t == QtCore.QEvent.Type.Leave:
                if self._meow_pressed:
                    now = QtCore.QTime.currentTime().msecsSinceStartOfDay()
                    remain = max(0, self._meow_min_show_ms - (now - self._meow_press_time))
                    self._meow_revert_timer.stop()
                    (self._revert_meow_icon() if remain == 0 else self._meow_revert_timer.start(remain))
                return False
        return super().eventFilter(obj, ev)

    def _set_pressed_icon(self):
        """switch to pressed icon.
		切换到按下图标。"""
        if not self.cat_img_pressed.isNull():
            self.btn_meow.setIcon(QtGui.QIcon(self.cat_img_pressed))

    def _revert_meow_icon(self):
        """revert to normal icon.
		恢复普通图标。"""
        if not self.cat_img_normal.isNull():
            self.btn_meow.setIcon(QtGui.QIcon(self.cat_img_normal))
        self._meow_pressed = False

    # ===== Menus / 菜单 =====
    def _build_menus(self):
        bar = self.menuBar()

        # File / 文件
        m_file = bar.addMenu("File")
        act_new  = m_file.addAction("New");  act_new.setShortcut("Ctrl+N"); act_new.triggered.connect(self.new_file)
        act_open = m_file.addAction("Open..."); act_open.setShortcut("Ctrl+O"); act_open.triggered.connect(self.open_file)
        m_file.addSeparator()
        act_save = m_file.addAction("Save"); act_save.setShortcut("Ctrl+S"); act_save.triggered.connect(lambda: self.save_file(False))
        m_file.addAction("Save As...", lambda: self.save_file(True))
        m_file.addSeparator(); m_file.addAction("Exit", self.close)

        # Setting / 设置
        m_set   = bar.addMenu("Setting")

        m_theme = m_set.addMenu("Theme")
        m_theme.addAction("Dark",    lambda: self._apply_theme("dark"))
        m_theme.addAction("Light",   lambda: self._apply_theme("light"))
        m_theme.addAction("Eye-care Yellow", lambda: self._apply_theme("eyecare"))

        m_bg = m_set.addMenu("Background")
        m_bg.addAction("Set Image...", self._set_background_image)
        m_bg.addAction("Clear Background", self._clear_background)

        m_lang = m_set.addMenu("Quotes Language")
        m_lang.addAction("中文",    lambda: self._set_quote_lang("zh"))
        m_lang.addAction("English", lambda: self._set_quote_lang("en"))

        # Overlay / 黑底
        m_overlay = m_set.addMenu("Overlay")
        act_toggle = QtGui.QAction("Show Background Shade", self)
        act_toggle.setCheckable(True)
        act_toggle.setChecked(self.editor.overlay_enabled)
        act_toggle.toggled.connect(self.editor.set_overlay_enabled)
        m_overlay.addAction(act_toggle)

        overlay_action = QtWidgets.QWidgetAction(self)
        overlay_widget = QtWidgets.QWidget(self)
        ov_lay = QtWidgets.QVBoxLayout(overlay_widget); ov_lay.setContentsMargins(8, 6, 8, 6)

        lbl_op = QtWidgets.QLabel(f"Opacity: {self.editor.overlay_alpha}", overlay_widget)
        sld_op = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal, overlay_widget)
        sld_op.setRange(0, 255); sld_op.setSingleStep(5); sld_op.setPageStep(15); sld_op.setValue(self.editor.overlay_alpha)
        sld_op.valueChanged.connect(lambda v: (self.editor.set_overlay_alpha(v), lbl_op.setText(f"Opacity: {v}")))
        ov_lay.addWidget(lbl_op); ov_lay.addWidget(sld_op)

        overlay_action.setDefaultWidget(overlay_widget)
        m_overlay.addAction(overlay_action)

        # Sound / 声音
        m_sound = m_set.addMenu("Sound")
        act_enable = QtGui.QAction("Enable Meow Sounds", self)
        act_enable.setCheckable(True); act_enable.setChecked(self.sound_enabled)
        act_enable.toggled.connect(self._toggle_sound)
        m_sound.addAction(act_enable)

        act_reset_count = QtGui.QAction("Reset Meow Counter", self)
        act_reset_count.triggered.connect(self._reset_meow_count)
        m_sound.addAction(act_reset_count)

        # Volume slider / 音量滑块
        m_sound.addSeparator()
        vol_action = QtWidgets.QWidgetAction(self)
        vol_widget = QtWidgets.QWidget(self)
        hl = QtWidgets.QHBoxLayout(vol_widget); hl.setContentsMargins(8, 6, 8, 6)
        self.lbl_vol = QtWidgets.QLabel(f"Volume: {int(self.meow_volume*100)}%", vol_widget)
        sld_vol = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal, vol_widget)
        sld_vol.setRange(0, 100); sld_vol.setValue(int(self.meow_volume*100))
        sld_vol.valueChanged.connect(self._on_meow_volume)
        hl.addWidget(self.lbl_vol); hl.addWidget(sld_vol)
        vol_action.setDefaultWidget(vol_widget)
        m_sound.addAction(vol_action)

        # Focus / 专注
        m_focus = bar.addMenu("Focus")
        m_focus.addAction("Start Focus", self.start_timer)
        m_focus.addAction("Pause Focus", self.pause_timer)
        m_focus.addAction("Reset Focus", self.reset_timer)
        m_focus.addSeparator()
        m_focus.addAction("Recolor ALL Now", self._colorize_all_sentences_once)

    # ===== Theme / 主题 =====
    def _apply_theme(self, key: str):
        """Apply app-wide palette & styles.
		应用统一调色板与样式。"""
        self.theme_key = key
        conf = THEMES[key]
        QtWidgets.QApplication.setStyle("Fusion")

        pal = QtGui.QPalette()
        fg, bg, bar = QtGui.QColor(conf["fg"]), QtGui.QColor(conf["bg"]), QtGui.QColor(conf["bar"])
        pal.setColor(QtGui.QPalette.ColorRole.Window, bg)
        pal.setColor(QtGui.QPalette.ColorRole.WindowText, fg)
        pal.setColor(QtGui.QPalette.ColorRole.Text, fg)
        pal.setColor(QtGui.QPalette.ColorRole.BrightText, fg)
        pal.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(0, 0, 0, 0))
        pal.setColor(QtGui.QPalette.ColorRole.AlternateBase, bg)
        pal.setColor(QtGui.QPalette.ColorRole.Button, bar)
        pal.setColor(QtGui.QPalette.ColorRole.ButtonText, fg)
        pal.setColor(QtGui.QPalette.ColorRole.ToolTipBase, bar)
        pal.setColor(QtGui.QPalette.ColorRole.ToolTipText, fg)
        pal.setColor(QtGui.QPalette.ColorRole.Highlight, fg)
        pal.setColor(QtGui.QPalette.ColorRole.HighlightedText, bg)

        dis_fg = QtGui.QColor(fg); dis_fg.setAlpha(160)
        pal.setColor(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Text, dis_fg)
        pal.setColor(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.ButtonText, dis_fg)
        pal.setColor(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.WindowText, dis_fg)

        QtWidgets.QApplication.setPalette(pal)
        self.setPalette(pal)
        self.central.setPalette(pal)
        self.central.setAutoFillBackground(True)

        self.setStyleSheet(f"""
            QWidget#topbar {{
                background: {conf['bar']};
                color: {conf['fg']};
            }}
            QMenuBar, QMenu {{
                background: {conf['bar']};
                color: {conf['fg']};
            }}
            QMenu::item:selected {{ background: rgba(255,255,255,0.15); }}
            QPushButton, QLabel {{ color: {conf['fg']}; font-size: 15px; font-weight: 500; }}
            QTextEdit {{
                background: transparent; border: none; color: {conf['fg']};
                selection-background-color: {conf['fg']}; selection-color: {conf['bg']};
            }}
        """)

        self.central.update()
        self.menuBar().update()
        self.editor.viewport().update()

    # ===== File ops / 文件操作 =====
    def new_file(self):
        """Clear to new file.
		新建并清空内容。"""
        if self._confirm_discard():
            self.editor.clear()
            self.current_file = DEFAULT_SAVE
            self.setWindowTitle("FocusCat - Untitled")
            self._update_word_status()
            self._last_colored_pos = 0

    def open_file(self):
        """Open a text file.
		打开文本文件。"""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open", "", "Text (*.txt);;All files (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.editor.setPlainText(f.read())
            self.current_file = path
            self.setWindowTitle(f"FocusCat - {os.path.basename(path)}")
            self._update_word_status()
            self._last_colored_pos = 0
            self._colorize_all_sentences_once()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Open failed", str(e))

    def save_file(self, save_as=False):
        """Save current content.
		保存当前内容。"""
        path = self.current_file
        if save_as or path == DEFAULT_SAVE:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save As", "", "Text (*.txt);;All files (*)")
            if not path:
                return
            self.current_file = path
            self.setWindowTitle(f"FocusCat - {os.path.basename(path)}")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.editor.toPlainText())
            self._set_quote(self._random_quote())
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Save failed", str(e))

    def _load_if_exists(self, path):
        """Load file if exists.
		若文件存在则加载。"""
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.editor.setPlainText(f.read())
                self.setWindowTitle(f"FocusCat - {os.path.basename(path)}")
                self._update_word_status()
            except Exception:
                pass

    def _confirm_discard(self):
        """Confirm discard when not empty.
		非空时确认放弃。"""
        if not self.editor.toPlainText().strip():
            return True
        ret = QtWidgets.QMessageBox.question(self, "New file", "Discard current content?")
        return ret == QtWidgets.QMessageBox.StandardButton.Yes

    # ===== Background / 背景图 =====
    def _set_background_image(self):
        """Choose and set background image.
		选择并设置背景图。"""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose Background Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif);;All files (*)"
        )
        if not path:
            return
        try:
            self.central.set_background_image(path)
            self.status.showMessage(f"Background set: {os.path.basename(path)}", 4000)
            QtWidgets.QMessageBox.information(self, "Background Set", f"已成功设置背景图：\n{os.path.basename(path)}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Set Background Failed", str(e))

    def _clear_background(self):
        """Clear background image.
		清除背景图。"""
        self.central.clear_background()
        self.status.showMessage("Background cleared", 3000)
        QtWidgets.QMessageBox.information(self, "Background Cleared", "已清除背景图。")

    # ===== Status / 状态栏 =====
    def _update_word_status(self):
        """update words count on status bar.
		更新状态栏字数。"""
        words = len(self.editor.toPlainText().split())
        self.status.showMessage(f"Words: {words}", 2000)

    # ===== Gradient utilities / 渐变工具 =====
    def _stable_gradient(self, base_hex: str, length: int, seed: int):
        """HSV-based stable gradient.
		基于 HSV 的稳定渐变。"""
        r = int(base_hex[1:3], 16) / 255.0
        g = int(base_hex[3:5], 16) / 255.0
        b = int(base_hex[5:7], 16) / 255.0
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        rnd = random.Random(seed)
        hue_jitter = (rnd.random() * 0.06) - 0.03
        cols = []
        for i in range(max(1, length)):
            t = i / max(1, length - 1)
            vv = max(0.55, min(1.0, v + 0.18 * (t * 2 - 1)))
            hh = (h + hue_jitter * (t * 2 - 1)) % 1.0
            rr, gg, bb = colorsys.hsv_to_rgb(hh, s, vv)
            cols.append(QtGui.QColor(int(rr * 255), int(gg * 255), int(bb * 255)))
        return cols

    # ===== Sentence coloring / 句子上色 =====
    def _doc_text(self): return self.editor.toPlainText()

    def _normalize_span(self, start: int, end: int):
        """trim span for color seed; return normalized range.
		对区间做首尾空白对齐并返回规范化文本用于取色。"""
        full = self._doc_text()
        seg  = full[start:end]
        ltrim = len(seg) - len(seg.lstrip())
        rtrim = len(seg) - len(seg.rstrip())
        new_start, new_end = start + ltrim, end - rtrim
        clean = full[new_start:new_end].lower()
        clean = re.sub(r"\s+", " ", clean).strip()
        clean = re.sub(SENT_END_RE + r"$", "", clean).strip()
        return new_start, new_end, clean

    def _clear_format_range(self, start: int, end: int):
        """reset color to theme default.
		将前景色复位为主题默认色。"""
        cur = self.editor.textCursor()
        cur.setPosition(start, QtGui.QTextCursor.MoveAnchor)
        cur.setPosition(end,   QtGui.QTextCursor.KeepAnchor)
        fmt = QtGui.QTextCharFormat()
        fmt.setForeground(QtGui.QBrush(self.palette().color(QtGui.QPalette.ColorRole.Text)))
        cur.mergeCharFormat(fmt)

    def _apply_color_to_range(self, start: int, end: int):
        """color sentence by left-to-right gradient.
		按左到右渐变为句子着色。"""
        start, end, clean = self._normalize_span(start, end)
        if not clean:
            return
        self._clear_format_range(start, end)
        seed = int(hashlib.md5(clean.encode("utf-8")).hexdigest(), 16)
        base = PALETTE[seed % len(PALETTE)]
        grad = self._stable_gradient(base, end - start, seed)
        cur  = self.editor.textCursor()
        for i, qc in enumerate(grad):
            cur.setPosition(start + i, QtGui.QTextCursor.MoveAnchor)
            cur.setPosition(start + i + 1, QtGui.QTextCursor.KeepAnchor)
            fmt = QtGui.QTextCharFormat(); fmt.setForeground(QtGui.QBrush(qc))
            cur.mergeCharFormat(fmt)

    def _colorize_all_sentences_once(self):
        """color all finished sentences.
		为已完成句子批量上色。"""
        full = self._doc_text()
        self._last_colored_pos = 0
        spans, start = [], 0
        for end in self._iter_sentence_ends(full, 0):
            spans.append((start, end)); start = end
        self._colorize_by_spans(spans)

    def _scan_and_color_new_sentences(self):
        """color newly finished sentences.
		为新增完成的句子上色。"""
        full = self._doc_text()
        if self._last_colored_pos >= len(full):
            return
        spans, start = [], self._last_colored_pos
        for end in self._iter_sentence_ends(full, start):
            spans.append((start, end)); start = end
        self._colorize_by_spans(spans)

    def _is_abbrev_end(self, text: str, dot_idx: int) -> bool:
        """whether '.' belongs to an abbreviation
		判断点是否为缩写结尾。"""
        window = text[max(0, dot_idx - 10): dot_idx + 1].lower()
        return any(window.endswith(abbr) for abbr in ABBREVIATIONS)

    def _iter_sentence_ends(self, text: str, start_idx: int = 0):
        """yield end positions of sentences; skip abbrev/digits/inside parens.
		产出句末位置；跳过缩写/小数点/括号未闭合场景。"""
        if start_idx >= len(text):
            return
        END_CHARS = ".?!。！？…"
        paren, i, n = 0, start_idx, len(text)
        while i < n:
            ch = text[i]
            if ch == "(": paren += 1
            elif ch == ")": paren = max(0, paren - 1)

            if ch in END_CHARS:
                if ch == "." and self._is_abbrev_end(text, i):
                    i += 1; continue
                if paren > 0:
                    i += 1; continue
                if ch == "." and i > 0 and i + 1 < n and text[i-1].isdigit() and text[i+1].isdigit():
                    i += 1; continue
                if ch == ".":
                    left  = text[max(0, i - 15):i]
                    right = text[i + 1:min(n, i + 16)]
                    if re.search(r"[A-Za-z0-9_-]$", left) and re.search(r"^[A-Za-z0-9_-]", right):
                        i += 1; continue

                j = i + 1
                while j < n and text[j] in END_CHARS: j += 1
                while j < n and text[j] in [")", "”", "’", '"', "'"]: j += 1
                yield j
                i = j; continue
            i += 1

    def _colorize_by_spans(self, spans):
        """apply color for spans and advance cursor.
		区间上色并推进游标。"""
        for st, ed in spans:
            self._apply_color_to_range(st, ed)
            self._last_colored_pos = ed

    # ===== Quotes / 喵语 =====
    def _random_quote(self):
        """pick a random quote by lang.
		按语言随机选择一句喵语。"""
        pool = QUOTES_ZH if self.quote_lang == "zh" else QUOTES_EN
        return random.choice(pool) if pool else ""

    def _set_quote(self, text): self.lbl_quote.setText(text)
    def _set_quote_lang(self, lang):
        """change language and rotate now.
		切换语言并立即轮换。"""
        self.quote_lang = lang
        self._set_quote(self._random_quote())
        self._schedule_quote_rotation(reset=True)

    def _schedule_quote_rotation(self, immediate=False, reset=False):
        """schedule next quote rotation.
		安排下一次喵语轮换。"""
        if reset: self._quote_timer.stop()
        if immediate: self._set_quote(self._random_quote())
        delay = random.randint(QUOTE_ROTATE_MIN, QUOTE_ROTATE_MAX) * 1000
        self._quote_timer.start(delay)

    def _rotate_quote(self):
        """timer callback to rotate quote.
		定时回调更换喵语。"""
        self._set_quote(self._random_quote())
        self._schedule_quote_rotation()

    # ===== Meow sounds / 喵叫音效 =====
    def _toggle_sound(self, checked: bool):
        """toggle meow sounds; sync button enabled.
		开关音效并同步按钮可用。"""
        self.sound_enabled = bool(checked)
        self.btn_meow.setEnabled(self.sound_enabled)
        self.status.showMessage("Meow sounds: ON" if checked else "Meow sounds: OFF", 1200)

    def _reset_meow_count(self):
        """reset counter to 0 and persist.
		计数清零并写回文件。"""
        self.meow_count = 0
        self.lbl_meow_count.setText("0")
        self._save_meow_count()
        self.status.showMessage("Meow counter reset to 0", 1500)

    def _on_meow_volume(self, v: int):
        """update volume and labels; apply to effects.
		更新音量与标签并应用到音效。"""
        self.meow_volume = v / 100.0
        self.lbl_vol.setText(f"Volume: {v}%")
        for eff in (*self.meow_effects, *self.surprise_effects):
            eff.setVolume(self.meow_volume)
        self.status.showMessage(f"Meow volume = {v}%", 1200)

    def _on_meow_clicked(self):
        """increase count and play sound (with rare surprise).
		计数并播放声音（含小概率惊喜）。"""
        self.meow_count += 1
        self.lbl_meow_count.setText(str(self.meow_count))
        self._save_meow_count()

        if not self.sound_enabled:
            return
        if not self.meow_effects and not self.surprise_effects:
            self.status.showMessage("No sounds found in assets/sounds", 2000)
            return

        use_surprise = bool(self.surprise_effects) and (random.random() < self.surprise_prob)
        pool = self.surprise_effects if use_surprise else self.meow_effects
        eff  = random.choice(pool)
        eff.setLoopCount(1)
        eff.setVolume(self.meow_volume)
        eff.play()
        if use_surprise:
            self.status.showMessage("Surprise meow!", 1500)

    def _load_meow_sounds(self):
        """preload *.wav under assets/sounds.
		预加载 assets/sounds 下的 *.wav。"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        sounds_dir = os.path.join(base_dir, "assets", "sounds")
        self.meow_effects.clear(); self.surprise_effects.clear()
        if not os.path.isdir(sounds_dir): return

        def make_eff(path: str) -> QSoundEffect:
            eff = QSoundEffect(self)
            eff.setSource(QtCore.QUrl.fromLocalFile(path))
            eff.setVolume(self.meow_volume)
            _ = eff.source()  # warm up / 预热
            return eff

        for name in os.listdir(sounds_dir):
            if not name.lower().endswith(".wav"):
                continue
            low = name.lower()
            eff = make_eff(os.path.join(sounds_dir, name))
            (self.surprise_effects if low.startswith(("surprise", "rare", "easter")) else self.meow_effects).append(eff)

    def _ensure_state_dir(self):
        """ensure state dir exists.
		确保状态目录存在。"""
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "state")
        os.makedirs(d, exist_ok=True)

    def _count_path(self) -> str:
        """return meow counter file path.
		返回计数文件路径。"""
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "state", "meow_count.txt")

    def _load_meow_count(self):
        """load total count from file.
		从文件读取总计数。"""
        try:
            with open(self._count_path(), "r", encoding="utf-8") as f:
                self.meow_count = int((f.read() or "0").strip())
        except Exception:
            self.meow_count = 0
        self.lbl_meow_count.setText(str(self.meow_count))

    def _save_meow_count(self):
        """save total count back to file.
		将总计数写回文件。"""
        try:
            with open(self._count_path(), "w", encoding="utf-8") as f:
                f.write(str(self.meow_count))
        except Exception:
            pass

    # ===== Timer / 计时器 =====
    def _fmt_time(self):
        """mm:ss string for title/label.
		返回 mm:ss 格式字符串。"""
        m, s = divmod(self.time_left, 60)
        return f"⏰ {m:02d}:{s:02d}"

    def start_timer(self):
        """start pomodoro.
		开始计时。"""
        if self.running: return
        self.running = True
        self._set_quote("专注开始喵～" if self.quote_lang == "zh" else "Focus mode: meow on!")
        self._render_timer()
        QtCore.QTimer.singleShot(1000, self._tick_timer)

    def pause_timer(self):
        """pause pomodoro.
		暂停计时。"""
        if not self.running: return
        self.running = False
        self._set_quote("先歇一歇，喝口水喵～" if self.quote_lang == "zh" else "Take a sip and a breath~")

    def reset_timer(self):
        """reset to initial minutes.
		复位到初始分钟。"""
        self.running = False
        self.time_left = POMODORO_MIN * 60
        self._render_timer()
        self._set_quote("重置完成，随时开始~" if self.quote_lang == "zh" else "Reset done. Ready anytime!")

    def _tick_timer(self):
        """countdown tick.
		倒计时步进。"""
        if not self.running: return
        if self.time_left > 0:
            self.time_left -= 1
            self._render_timer()
            QtCore.QTimer.singleShot(1000, self._tick_timer)
        else:
            self.running = False
            self._set_quote("时间到啦！伸个懒腰再回来喵～" if self.quote_lang == "zh"
                            else "Time! Stretch and come back meow~")

    def _render_timer(self):
        """refresh title & label with time.
		刷新标题与时间标签。"""
        self.lbl_timer.setText(self._fmt_time())
        self.setWindowTitle(f"FocusCat — {self._fmt_time()}")

    # ===== Heartbeat & autosave / 心跳与自动保存 =====
    def _heartbeat_tick(self):
        """heartbeat refresh and sentence scan.
		心跳刷新与新句扫描。"""
        if self.running:
            self.setWindowTitle(f"FocusCat — {self._fmt_time()}")
        self._scan_and_color_new_sentences()

    def _autosave(self):
        """write autosave file regularly.
		定期写入自动保存文件。"""
        try:
            with open(DEFAULT_SAVE, "w", encoding="utf-8") as f:
                f.write(self.editor.toPlainText())
        except Exception:
            pass


# ===== App entry / 程序入口 =====
def main():
    """Qt app bootstrap.
		Qt 应用启动入口。"""
    app = QtWidgets.QApplication([])
    QtWidgets.QApplication.setStyle("Fusion")

    # global app icon / 全局应用图标
    icon_path = os.path.join(os.path.dirname(__file__), "assets", "images", "cat_icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QtGui.QIcon(icon_path))

    # Windows taskbar AppUserModelID / Windows 任务栏分组 ID
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FocusCat.CatStudio.1.0")
    except Exception:
        pass

    w = FocusCat()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
