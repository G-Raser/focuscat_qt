# focuscat_qt.py — FocusCat (Qt version) with sentence coloring, fixed theming, background image
from PySide6 import QtCore, QtGui, QtWidgets
import os, random, re, hashlib, colorsys
from PySide6.QtMultimedia import QSoundEffect

DEFAULT_SAVE     = "autosave.txt"
POMODORO_MIN     = 25
HEARTBEAT_MS     = 200
SENT_END_RE      = r"[\.!\?。！？…]+"
QUOTE_ROTATE_MIN = 60
QUOTE_ROTATE_MAX = 120

THEMES = {
    "dark":    {"bg":"#181818", "fg":"#ffffff", "bar":"#202020"},
    "light":   {"bg":"#FAFAFA", "fg":"#111111", "bar":"#EFEFEF"},
    "eyecare": {"bg":"#FFF3B0", "fg":"#2b2b2b", "bar":"#FFE89A"},
}

PALETTE = ["#FF6B6B","#FFD93D","#6BCB77","#4D96FF","#FF9CEE",
           "#A3E4DB","#FFB26B","#B983FF","#FFC7C7","#7DE5ED"]

QUOTES_ZH = [
    "喵～好棒，继续写！","(*´∀`)♡ 再来一句！","你今天状态很好喵！",
    "伸个懒腰，然后继续～","FocusCat 为你守护专注 ✨",
    "喝口水，眼睛休息十秒喵～","先写不完美，也很棒喵！"
]
QUOTES_EN = [
    "Meow~ you're doing great!","One more line, you got this!",
    "Looking sharp today, human 🐾","Stretch a bit and keep going!",
    "FocusCat is guarding your focus ✨","Sip some water and relax your eyes.",
    "It's okay to write imperfectly first!"
]

# 常见缩写（末尾带点的）——用于避免把缩写当句末
ABBREVIATIONS = [
    "e.g.", "i.e.", "etc.", "vs.", "cf.", "fig.", "al.", "ca.",
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.",
    "ph.d.", "u.s.", "u.k.", "a.m.", "p.m.",
]
# 中文下也可能混用英文缩写，这里大小写都忽略


class BgCentralWidget(QtWidgets.QWidget):
    """中心容器：自己画背景图（cover），其上放透明 QTextEdit 和顶栏"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg_pix: QtGui.QPixmap|None = None
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)

    def set_background_image(self, path: str):
        pm = QtGui.QPixmap(path)
        if pm.isNull():
            raise RuntimeError("无法加载图片")
        self._bg_pix = pm
        self.update()

    def clear_background(self):
        self._bg_pix = None
        self.update()

    def paintEvent(self, e: QtGui.QPaintEvent) -> None:
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), self.palette().window())
        if self._bg_pix:
            target = self.rect()
            src_w, src_h = self._bg_pix.width(), self._bg_pix.height()
            tgt_w, tgt_h = target.width(), target.height()
            if src_w <= 0 or src_h <= 0 or tgt_w <= 0 or tgt_h <= 0:
                return
            scale = max(tgt_w / src_w, tgt_h / src_h)
            new_w = int(src_w * scale)
            new_h = int(src_h * scale)
            x = (new_w - tgt_w) // 2
            y = (new_h - tgt_h) // 2
            scaled = self._bg_pix.scaled(new_w, new_h,
                                         QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                         QtCore.Qt.TransformationMode.SmoothTransformation)
            src_rect = QtCore.QRect(x, y, tgt_w, tgt_h)
            p.drawPixmap(target, scaled, src_rect)
        p.end()
        super().paintEvent(e)

class ShadedTextEdit(QtWidgets.QTextEdit):
    """
    自动在“可见且有文字”的区域下方绘制半透明黑底，
    不覆盖没有文字的上下边缘和左右外侧留白。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        # 建议开启按窗口宽度换行，底板才会贴合段落列宽
        self.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.WidgetWidth)
        # 可调参数
        self.overlay_enabled = True
        self.overlay_margin_v = 8      # 底板上下外边距
        self.overlay_margin_h = -10     # 底板左右外边距（相对viewport边缘）
        self.overlay_radius   = 5     # 圆角
        self.overlay_alpha    = 170    # 0~255，越大越黑

    def _visible_text_union_rect_doccoords(self):
        """返回文档坐标系下，可见且非空文本块的联合矩形（无则返回None）"""
        doc = self.document()
        layout = doc.documentLayout()
        if layout is None:
            return None

        # 可见范围（文档坐标系）
        y0 = self.verticalScrollBar().value()
        y1 = y0 + self.viewport().height()

        first = True
        union = QtCore.QRectF()
        block = doc.begin()
        while block.isValid():
            if block.length() > 1:  # 有字符（含换行），再判空白
                text = block.text().strip()
                if text:
                    br = layout.blockBoundingRect(block)  # 文档坐标
                    if br.bottom() >= y0 and br.top() <= y1:
                        # 参与可见范围的非空块
                        if first:
                            union = br
                            first = False
                        else:
                            union = union.united(br)
            block = block.next()

        return None if first else union

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        # 在绘制文字之前画固定矩形底板
        if self.overlay_enabled:
            p = QtGui.QPainter(self.viewport())
            color = QtGui.QColor(0, 0, 0, self.overlay_alpha)
            p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            path = QtGui.QPainterPath()

            # —— 可调参数 ——
            width_ratio = 1  # 矩形宽度占编辑区的比例（0~1）
            height_ratio = 1  # 矩形高度占编辑区的比例（0~1）
            radius = self.overlay_radius

            vw = self.viewport().width()
            vh = self.viewport().height()
            rw = vw * width_ratio
            rh = vh * height_ratio

            x = (vw - rw) / 2
            y = (vh - rh) / 2

            rect = QtCore.QRectF(x, y, rw, rh)
            path.addRoundedRect(rect, radius, radius)
            p.fillPath(path, color)
            p.end()

        # 再绘制文字
        super().paintEvent(event)

    def set_overlay_alpha(self, value: int):
        """调透明度 0~255，并重绘"""
        self.overlay_alpha = max(0, min(255, int(value)))
        self.viewport().update()

    def set_overlay_enabled(self, enabled: bool):
        """开关黑底"""
        self.overlay_enabled = bool(enabled)
        self.viewport().update()


class FocusCat(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FocusCat 🐱")
        self.resize(980, 640)

        # 状态
        self.theme_key = "dark"
        self.time_left = POMODORO_MIN * 60
        self.running   = False
        self.quote_lang = "zh"
        self._quote_timer = QtCore.QTimer(self)
        self._quote_timer.setSingleShot(True)
        self._quote_timer.timeout.connect(self._rotate_quote)

        # 句子着色状态
        self._last_colored_pos = 0  # 文档字符偏移（从 0 开始）

        # 中心容器（画背景）
        self.central = BgCentralWidget(self)
        self.setCentralWidget(self.central)

        self.sound_enabled = True  # 菜单可关闭
        self.meow_count = 0  # 计数
        self.meow_volume = 0.85  # 0.0~1.0，全局音量（默认 85%）
        self.meow_effects: list[QSoundEffect] = []
        self._load_meow_sounds()  # 预加载音效（见下面方法）

        # 顶栏
        top = QtWidgets.QWidget(self.central); top.setObjectName("topbar")
        top_layout = QtWidgets.QHBoxLayout(top); top_layout.setContentsMargins(10,6,10,6)
        self.lbl_timer = QtWidgets.QLabel(self._fmt_time(), top)
        self.btn_start = QtWidgets.QPushButton("▶ Start", top); self.btn_start.clicked.connect(self.start_timer)
        self.btn_pause = QtWidgets.QPushButton("⏸ Pause", top); self.btn_pause.clicked.connect(self.pause_timer)
        self.btn_reset = QtWidgets.QPushButton("↺ Reset", top); self.btn_reset.clicked.connect(self.reset_timer)

        # self.lbl_quote = QtWidgets.QLabel("喵～准备开始写作了吗？", top)
        # self.btn_save  = QtWidgets.QPushButton("💾 Save", top); self.btn_save.clicked.connect(lambda: self.save_file(False))
        # for w in (self.lbl_timer, self.btn_start, self.btn_pause, self.btn_reset, self.lbl_quote):
        #     top_layout.addWidget(w)
        # top_layout.addStretch(1); top_layout.addWidget(self.btn_save)

        self.lbl_quote = QtWidgets.QLabel("喵～准备开始写作了吗？", top)

        # --- 新增：Meow 按钮 + 计数 ---
        self.btn_meow = QtWidgets.QPushButton("Meow", top)
        self.btn_meow.setToolTip("Play a random meow sound")
        self.btn_meow.clicked.connect(self._on_meow_clicked)

        self.lbl_meow_count = QtWidgets.QLabel("0", top)
        self.lbl_meow_count.setMinimumWidth(24)
        self.lbl_meow_count.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.lbl_meow_count.setToolTip("Meow click count")

        self.btn_save = QtWidgets.QPushButton("💾 Save", top)
        self.btn_save.clicked.connect(lambda: self.save_file(False))

        for w in (self.lbl_timer, self.btn_start, self.btn_pause, self.btn_reset, self.lbl_quote):
            top_layout.addWidget(w)

        # Save 左边插入 Meow 和计数器
        top_layout.addStretch(1)
        top_layout.addWidget(self.btn_meow)
        top_layout.addWidget(self.lbl_meow_count)
        top_layout.addWidget(self.btn_save)

        # 与菜单开关同步初始可用态
        self.btn_meow.setEnabled(self.sound_enabled)

        # 编辑器（透明）
        # self.editor = QtWidgets.QTextEdit(self.central)
        # self.editor.setAcceptRichText(False)
        # self.editor.setFont(QtGui.QFont("Consolas", 14))
        # self.editor.textChanged.connect(self._update_word_status)

        self.editor = ShadedTextEdit(self.central)
        self.editor.setFont(QtGui.QFont("Consolas", 14))
        # 保持主题样式：确保 Base/背景透明，文字颜色走主题
        # 例如在 _apply_theme 里已有：
        # QTextEdit { background: transparent; border: none; color: <fg>; }

        # 布局
        lay = QtWidgets.QVBoxLayout(self.central)
        lay.setContentsMargins(40, 24, 40, 24); lay.setSpacing(8)
        lay.addWidget(top, 0); lay.addWidget(self.editor, 1)

        # 状态栏
        self.status = self.statusBar(); self._update_word_status()

        # 菜单
        self._build_menus()

        # 主题
        self._apply_theme(self.theme_key)

        # 自动保存
        self._autosave_timer = QtCore.QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start(15000)

        # 心跳：标题刷新 + 句子扫描着色
        self._heartbeat = QtCore.QTimer(self)
        self._heartbeat.timeout.connect(self._heartbeat_tick)
        self._heartbeat.start(HEARTBEAT_MS)

        # 打开 autosave 并进行首次整体着色
        self.current_file = DEFAULT_SAVE
        self._load_if_exists(DEFAULT_SAVE)
        self._colorize_all_sentences_once()

        # 启动喵喵话轮换
        self._schedule_quote_rotation(immediate=True)

        # ---- 默认背景图 ----
        default_bg = os.path.join(os.path.dirname(__file__), "assets", "images", "bg_default.jpg")
        if os.path.exists(default_bg):
            try:
                self.central.set_background_image(default_bg)
                self.status.showMessage("默认背景已加载", 3000)
            except Exception as e:
                print(f"无法加载默认背景: {e}")

    # ---------- 菜单 ----------
    def _build_menus(self):
        bar = self.menuBar()
        m_file = bar.addMenu("File")
        act_new = m_file.addAction("New");     act_new.setShortcut("Ctrl+N"); act_new.triggered.connect(self.new_file)
        act_open= m_file.addAction("Open..."); act_open.setShortcut("Ctrl+O"); act_open.triggered.connect(self.open_file)
        m_file.addSeparator()
        act_save = m_file.addAction("Save");   act_save.setShortcut("Ctrl+S"); act_save.triggered.connect(lambda: self.save_file(False))
        act_saveas = m_file.addAction("Save As..."); act_saveas.triggered.connect(lambda: self.save_file(True))
        m_file.addSeparator(); m_file.addAction("Exit", self.close)

        m_view = bar.addMenu("Setting")
        m_theme = m_view.addMenu("Theme")
        m_theme.addAction("Dark",    lambda: self._apply_theme("dark"))
        m_theme.addAction("Light",   lambda: self._apply_theme("light"))
        m_theme.addAction("Eye-care Yellow", lambda: self._apply_theme("eyecare"))
        m_bg = m_view.addMenu("Background")
        m_bg.addAction("Set Image...", self._set_background_image)
        m_bg.addAction("Clear Background", self._clear_background)
        m_lang = m_view.addMenu("Quotes Language")
        m_lang.addAction("中文",    lambda: self._set_quote_lang("zh"))
        m_lang.addAction("English", lambda: self._set_quote_lang("en"))

        # ===== Overlay（黑底） =====
        m_overlay = m_view.addMenu("Overlay")

        # ===== Sound（声音） =====
        m_sound = m_view.addMenu("Sound")

        act_enable_sound = QtGui.QAction("Enable Meow Sounds", self)
        act_enable_sound.setCheckable(True)
        act_enable_sound.setChecked(self.sound_enabled)

        # --- Volume slider (0~100%) ---
        vol_action = QtWidgets.QWidgetAction(self)
        vol_widget = QtWidgets.QWidget(self)
        vol_layout = QtWidgets.QVBoxLayout(vol_widget)
        vol_layout.setContentsMargins(8, 6, 8, 6)

        vol_label = QtWidgets.QLabel(f"Volume: {int(self.meow_volume * 100)}%", vol_widget)
        vol_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal, vol_widget)
        vol_slider.setRange(0, 100)
        vol_slider.setSingleStep(1)
        vol_slider.setPageStep(5)
        vol_slider.setValue(int(self.meow_volume * 100))

        def _on_volume_changed(val: int):
            self.meow_volume = max(0, min(100, int(val))) / 100.0
            self._apply_meow_volume()
            vol_label.setText(f"Volume: {val}%")
            # 状态栏可选提示
            try:
                self.statusBar().showMessage(f"Meow volume = {val}%", 1200)
            except Exception:
                pass

        vol_slider.valueChanged.connect(_on_volume_changed)
        vol_layout.addWidget(vol_label)
        vol_layout.addWidget(vol_slider)
        vol_action.setDefaultWidget(vol_widget)
        m_sound.addAction(vol_action)

        def _toggle_sound(checked: bool):
            self.sound_enabled = bool(checked)
            # 灰掉按钮更直观
            self.btn_meow.setEnabled(self.sound_enabled)
            self.status.showMessage("Meow sounds: ON" if checked else "Meow sounds: OFF", 1200)

        act_enable_sound.toggled.connect(_toggle_sound)
        m_sound.addAction(act_enable_sound)

        # 2.1 开关
        act_toggle = QtGui.QAction("Show Background Shade", self)
        act_toggle.setCheckable(True)
        act_toggle.setChecked(self.editor.overlay_enabled)
        act_toggle.toggled.connect(self.editor.set_overlay_enabled)
        m_overlay.addAction(act_toggle)

        # 2.2 透明度滑块（0~255）
        overlay_action = QtWidgets.QWidgetAction(self)
        overlay_widget = QtWidgets.QWidget(self)
        overlay_layout = QtWidgets.QVBoxLayout(overlay_widget)
        overlay_layout.setContentsMargins(8, 6, 8, 6)

        lbl = QtWidgets.QLabel(f"Opacity: {self.editor.overlay_alpha}", overlay_widget)
        sld = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal, overlay_widget)
        sld.setRange(0, 255)
        sld.setSingleStep(5)
        sld.setPageStep(15)
        sld.setValue(self.editor.overlay_alpha)

        def _on_opacity(v: int):
            self.editor.set_overlay_alpha(v)
            lbl.setText(f"Opacity: {v}")
            self.status.showMessage(f"Overlay opacity = {v}", 1500)

        sld.valueChanged.connect(_on_opacity)
        overlay_layout.addWidget(lbl)
        overlay_layout.addWidget(sld)

        overlay_action.setDefaultWidget(overlay_widget)
        m_overlay.addAction(overlay_action)


        m_focus = bar.addMenu("Focus")
        m_focus.addAction("Start Focus", self.start_timer)
        m_focus.addAction("Pause Focus", self.pause_timer)
        m_focus.addAction("Reset Focus", self.reset_timer)
        m_focus.addSeparator()
        m_focus.addAction("Recolor ALL Now", self._colorize_all_sentences_once)


    def _apply_theme(self, key: str):
        self.theme_key = key
        conf = THEMES[key]

        # 统一使用 Fusion 样式，避免系统主题把颜色改回去
        QtWidgets.QApplication.setStyle("Fusion")

        # ===== 1) 构造完整调色板 =====
        pal = QtGui.QPalette()
        fg = QtGui.QColor(conf["fg"])
        bg = QtGui.QColor(conf["bg"])
        bar = QtGui.QColor(conf["bar"])

        # 窗口 & 文本
        pal.setColor(QtGui.QPalette.ColorRole.Window, bg)
        pal.setColor(QtGui.QPalette.ColorRole.WindowText, fg)
        pal.setColor(QtGui.QPalette.ColorRole.Text, fg)
        pal.setColor(QtGui.QPalette.ColorRole.BrightText, fg)

        # 输入区（QTextEdit 等）：Base 用透明，让背景图可见
        pal.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(0, 0, 0, 0))
        pal.setColor(QtGui.QPalette.ColorRole.AlternateBase, bg)

        # 按钮/菜单
        pal.setColor(QtGui.QPalette.ColorRole.Button, bar)
        pal.setColor(QtGui.QPalette.ColorRole.ButtonText, fg)
        pal.setColor(QtGui.QPalette.ColorRole.ToolTipBase, bar)
        pal.setColor(QtGui.QPalette.ColorRole.ToolTipText, fg)

        # 选中高亮
        pal.setColor(QtGui.QPalette.ColorRole.Highlight, fg)
        pal.setColor(QtGui.QPalette.ColorRole.HighlightedText, bg)

        # 禁用态也给可见颜色
        dis_fg = QtGui.QColor(fg);
        dis_fg.setAlpha(160)
        pal.setColor(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Text, dis_fg)
        pal.setColor(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.ButtonText, dis_fg)
        pal.setColor(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.WindowText, dis_fg)

        # ===== 2) 应用到整 app、主窗体和中央小部件 =====
        QtWidgets.QApplication.setPalette(pal)  # ★ 应用级，菜单也吃到
        self.setPalette(pal)
        self.central.setPalette(pal)  # ★ 关键：BgCentralWidget 用它来 paintEvent 填充底色
        self.central.setAutoFillBackground(True)

        # ===== 3) 样式表（作用在整窗，未着色文字随主题变色） =====
        self.setStyleSheet(f"""
            QWidget#topbar {{
                background: {conf['bar']};
                color: {conf['fg']};
            }}
            QMenuBar, QMenu {{
                background: {conf['bar']};
                color: {conf['fg']};
            }}
            QMenu::item:selected {{
                background: rgba(255,255,255,0.15);
            }}
            QPushButton, QLabel {{
                color: {conf['fg']};
            }}
            QTextEdit {{
                background: transparent;
                border: none;
                color: {conf['fg']};
                selection-background-color: {conf['fg']};
                selection-color: {conf['bg']};
            }}
        """)

        # 触发重绘
        self.central.update()
        self.menuBar().update()
        self.editor.viewport().update()

    # ---------- 文件 ----------
    def new_file(self):
        if self._confirm_discard():
            self.editor.clear()
            self.current_file = DEFAULT_SAVE
            self.setWindowTitle("FocusCat 🐱 - Untitled")
            self._update_word_status()
            self._last_colored_pos = 0

    def open_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open", "", "Text (*.txt);;All files (*)")
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.editor.setPlainText(f.read())
            self.current_file = path
            self.setWindowTitle(f"FocusCat 🐱 - {os.path.basename(path)}")
            self._update_word_status()
            self._last_colored_pos = 0
            self._colorize_all_sentences_once()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Open failed", str(e))

    def save_file(self, save_as=False):
        path = self.current_file
        if save_as or path == DEFAULT_SAVE:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save As", "", "Text (*.txt);;All files (*)")
            if not path: return
            self.current_file = path
            self.setWindowTitle(f"FocusCat 🐱 - {os.path.basename(path)}")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.editor.toPlainText())
            self._set_quote(self._random_quote())
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Save failed", str(e))

    def _load_if_exists(self, path):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.editor.setPlainText(f.read())
                self.setWindowTitle(f"FocusCat 🐱 - {os.path.basename(path)}")
                self._update_word_status()
            except Exception:
                pass

    def _confirm_discard(self):
        if not self.editor.toPlainText().strip():
            return True
        ret = QtWidgets.QMessageBox.question(self, "New file", "Discard current content?")
        return ret == QtWidgets.QMessageBox.StandardButton.Yes

    # ---------- 背景 ----------
    def _set_background_image(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Choose Background Image", "",
                                                        "Images (*.png *.jpg *.jpeg *.bmp *.gif);;All files (*)")
        if not path: return
        try:
            self.central.set_background_image(path)
            self.status.showMessage(f"Background set: {os.path.basename(path)}", 4000)
            QtWidgets.QMessageBox.information(self, "Background Set", f"已成功设置背景图：\n{os.path.basename(path)}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Set Background Failed", str(e))

    def _clear_background(self):
        self.central.clear_background()
        self.status.showMessage("Background cleared", 3000)
        QtWidgets.QMessageBox.information(self, "Background Cleared", "已清除背景图。")

    # ---------- 状态/字数 ----------
    def _update_word_status(self):
        words = len(self.editor.toPlainText().split())
        self.status.showMessage(f"Words: {words}", 2000)

    # ---------- 渐变色工具 ----------
    def _stable_gradient(self, base_hex: str, length: int, seed: int):
        base_hex = base_hex.lstrip("#")
        r = int(base_hex[0:2], 16)/255.0
        g = int(base_hex[2:4], 16)/255.0
        b = int(base_hex[4:6], 16)/255.0
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        rnd = random.Random(seed)
        hue_jitter = (rnd.random() * 0.06) - 0.03
        cols = []
        for i in range(max(1, length)):
            t  = i / max(1, length-1)
            vv = max(0.55, min(1.0, v + 0.18 * (t*2-1)))
            hh = (h + hue_jitter * (t*2-1)) % 1.0
            rr, gg, bb = colorsys.hsv_to_rgb(hh, s, vv)
            cols.append(QtGui.QColor(int(rr*255), int(gg*255), int(bb*255)))
        return cols

    # ---------- 句子着色 ----------
    def _doc_text(self):
        return self.editor.toPlainText()

    # def _apply_color_to_range(self, start_pos: int, end_pos: int):
    #     txt = self._doc_text()[start_pos:end_pos]
    #     if not txt.strip():
    #         return
    #     # 稳定种子 & 基色
    #     seed = int(hashlib.md5(txt.encode("utf-8")).hexdigest(), 16)
    #     base = PALETTE[seed % len(PALETTE)]
    #     grad = self._stable_gradient(base, end_pos - start_pos, seed)
    #
    #     cur = self.editor.textCursor()
    #     # 一次性逐字符上色
    #     for i, qc in enumerate(grad):
    #         cur.setPosition(start_pos + i, QtGui.QTextCursor.MoveAnchor)
    #         cur.setPosition(start_pos + i + 1, QtGui.QTextCursor.KeepAnchor)
    #         fmt = QtGui.QTextCharFormat()
    #         fmt.setForeground(QtGui.QBrush(qc))
    #         cur.mergeCharFormat(fmt)
    #
    # def _colorize_all_sentences_once(self):
    #     # 清理：保证后续重新着色时不会残留默认色问题（无需清除已有彩色）
    #     full = self._doc_text()
    #     self._last_colored_pos = 0
    #     start = 0
    #     for m in re.finditer(SENT_END_RE, full):
    #         end = m.end()
    #         self._apply_color_to_range(start, end)
    #         start = end
    #         self._last_colored_pos = end
    #     # 尾部未完成句保留默认主题色（不着色）
    #
    # def _scan_and_color_new_sentences(self):
    #     full = self._doc_text()
    #     if self._last_colored_pos >= len(full):
    #         return
    #     seg = full[self._last_colored_pos:]
    #     for m in re.finditer(SENT_END_RE, seg):
    #         end = self._last_colored_pos + m.end()
    #         self._apply_color_to_range(self._last_colored_pos, end)
    #         self._last_colored_pos = end

    def _normalize_span(self, start: int, end: int):
        """对 [start,end) 句子范围做起止对齐并返回 (new_start,new_end,clean_text)。"""
        full = self._doc_text()
        seg = full[start:end]

        # 去掉句首空白、句末空白（不改变文档，只用于定位/取色）
        ltrim = len(seg) - len(seg.lstrip())
        rtrim = len(seg) - len(seg.rstrip())
        new_start = start + ltrim
        new_end = end - rtrim

        # 规范化文本用于稳定取色：小写、去多空格、去末尾句末标点
        clean = full[new_start:new_end]
        clean = clean.lower()
        clean = re.sub(r"\s+", " ", clean).strip()
        clean = re.sub(SENT_END_RE + r"$", "", clean).strip()

        return new_start, new_end, clean

    def _clear_format_range(self, start_pos: int, end_pos: int):
        """将范围内前景色重置为主题默认色，避免残留颜色叠加。"""
        cur = self.editor.textCursor()
        cur.setPosition(start_pos, QtGui.QTextCursor.MoveAnchor)
        cur.setPosition(end_pos, QtGui.QTextCursor.KeepAnchor)
        fmt = QtGui.QTextCharFormat()
        default_fg = self.palette().color(QtGui.QPalette.ColorRole.Text)
        fmt.setForeground(QtGui.QBrush(default_fg))
        cur.mergeCharFormat(fmt)

    def _apply_color_to_range(self, start_pos: int, end_pos: int):
        """对一个句子区间做左到右的渐变着色（跳过前导空白，句末标点包含在内）。"""
        # 先做起止对齐 & 拿到稳定种子文本
        start_pos, end_pos, clean = self._normalize_span(start_pos, end_pos)
        if not clean:
            return

        # 先清掉旧色，再着色（避免残留）
        self._clear_format_range(start_pos, end_pos)

        # 稳定种子 & 基色
        seed = int(hashlib.md5(clean.encode("utf-8")).hexdigest(), 16)
        base = PALETTE[seed % len(PALETTE)]
        grad = self._stable_gradient(base, end_pos - start_pos, seed)

        # 逐字符上色
        cur = self.editor.textCursor()
        for i, qc in enumerate(grad):
            cur.setPosition(start_pos + i, QtGui.QTextCursor.MoveAnchor)
            cur.setPosition(start_pos + i + 1, QtGui.QTextCursor.KeepAnchor)
            fmt = QtGui.QTextCharFormat()
            fmt.setForeground(QtGui.QBrush(qc))
            cur.mergeCharFormat(fmt)

    # def _colorize_all_sentences_once(self):
    #     """打开文件或切主题后，对已完成的全部句子统一上色。"""
    #     full = self._doc_text()
    #     self._last_colored_pos = 0
    #     start = 0
    #     for m in re.finditer(SENT_END_RE, full):
    #         end = m.end()
    #         self._apply_color_to_range(start, end)
    #         start = end
    #         self._last_colored_pos = end
    #     # 末尾未完成的句子保持默认主题色

    def _colorize_all_sentences_once(self):
        """打开文件或切主题后，对已完成的全部句子统一上色。"""
        full = self._doc_text()
        self._last_colored_pos = 0
        spans = []
        start = 0
        for end in self._iter_sentence_ends(full, 0):
            spans.append((start, end))
            start = end
        self._colorize_by_spans(spans)
        # 尾部未完成句保持默认主题色

    def _scan_and_color_new_sentences(self):
        """实时扫描新增的句末并上色，保证输入到句末符立即统一着色。"""
        full = self._doc_text()
        if self._last_colored_pos >= len(full):
            return
        spans = []
        start = self._last_colored_pos
        for end in self._iter_sentence_ends(full, start):
            spans.append((start, end))
            start = end
        self._colorize_by_spans(spans)

    # def _scan_and_color_new_sentences(self):
    #     """实时扫描新增的句末并上色，保证输入到句末符立即统一着色。"""
    #     full = self._doc_text()
    #     if self._last_colored_pos >= len(full):
    #         return
    #     seg = full[self._last_colored_pos:]
    #     for m in re.finditer(SENT_END_RE, seg):
    #         end = self._last_colored_pos + m.end()
    #         self._apply_color_to_range(self._last_colored_pos, end)
    #         self._last_colored_pos = end

    def _is_abbrev_end(self, text: str, dot_idx: int) -> bool:
        """
        当前 dot_idx 指向 '.'；判断这个点是否属于缩写的结尾，
        例如 ... 'e.g.' 里的最后一个点。
        """
        # 最长缩写长度大概 6~8，这里取 10 做保险
        window = text[max(0, dot_idx - 10): dot_idx + 1].lower()
        for abbr in ABBREVIATIONS:
            if window.endswith(abbr):
                return True
        return False

    def _iter_sentence_ends(self, text: str, start_idx: int = 0):
        """
        线性扫描给出“句末”位置（end 索引，包含标点），
        规则：括号未闭合时不结句；缩写的点不结句；中英句末符都支持。
        """
        if start_idx >= len(text):
            return
        paren = 0  # 括号层级：遇 '(' +1，遇 ')' -1
        i = start_idx
        N = len(text)
        while i < N:
            ch = text[i]
            if ch == "(":
                paren += 1
            elif ch == ")":
                paren = max(0, paren - 1)

            # 句末候选：英文 .?! 或 中文 。！？…
            if ch in ".?!" or ch in "。！？…":
                # 缩写 => 跳过
                if ch == "." and self._is_abbrev_end(text, i):
                    i += 1
                    continue
                # 括号内 => 跳过（把句末延迟到括号闭合之后）
                if paren > 0:
                    i += 1
                    continue

                # 向右吞掉紧跟的右括号/引号作为“句尾装饰”，一起算进句子
                j = i + 1
                while j < N and text[j] in [")", "”", "’", '"', "'"]:
                    j += 1

                yield j  # 句子结束位置（右开区间 end）
                i = j
                continue

            i += 1

    def _colorize_by_spans(self, spans):
        """给一组 (start,end) 句子区间统一着色。"""
        for start, end in spans:
            self._apply_color_to_range(start, end)
            self._last_colored_pos = end

    # ---------- 喵喵话 ----------
    def _random_quote(self):
        pool = QUOTES_ZH if self.quote_lang == "zh" else QUOTES_EN
        return random.choice(pool) if pool else ""

    def _set_quote(self, text):
        self.lbl_quote.setText(text)

    def _set_quote_lang(self, lang):
        self.quote_lang = lang
        self._set_quote(self._random_quote())
        self._schedule_quote_rotation(reset=True)

    def _schedule_quote_rotation(self, immediate=False, reset=False):
        if reset:
            self._quote_timer.stop()
        if immediate:
            self._set_quote(self._random_quote())
        delay = random.randint(QUOTE_ROTATE_MIN, QUOTE_ROTATE_MAX) * 1000
        self._quote_timer.start(delay)

    def _rotate_quote(self):
        self._set_quote(self._random_quote())
        self._schedule_quote_rotation()

    def _on_meow_clicked(self):
        """点击 Meow：计数 + 随机播放猫叫（若开启）"""
        # 计数
        self.meow_count += 1
        self.lbl_meow_count.setText(str(self.meow_count))

        # 声音关闭则不播
        if not self.sound_enabled:
            return

        # 无音效资源则提示一次
        if not self.meow_effects:
            self.status.showMessage("No meow sounds found in assets/sounds", 2000)
            return

        # 随机选择并播放
        eff = random.choice(self.meow_effects)
        eff.setLoopCount(1)
        eff.play()

    def _apply_meow_volume(self):
        """把全局音量应用到所有已加载的 QSoundEffect"""
        v = max(0.0, min(1.0, float(self.meow_volume)))
        for eff in self.meow_effects:
            eff.setVolume(v)

    def _load_meow_sounds(self):
        """
        预加载 ./assets/sounds 下的 .wav 音效到 QSoundEffect。
        推荐使用 WAV（Qt 更稳定）。如需批量转换，可先用 ffmpeg 转好再放入此目录。
        """
        base_dir = os.path.dirname(os.path.abspath(__file__))
        sounds_dir = os.path.join(base_dir, "assets", "sounds")

        self.meow_effects.clear()

        if not os.path.isdir(sounds_dir):
            # 若没有该目录，不报错；你把声音文件放进去即可
            return

        for name in os.listdir(sounds_dir):
            if not name.lower().endswith(".wav"):
                continue
            path = os.path.join(sounds_dir, name)
            eff = QSoundEffect(self)
            eff.setSource(QtCore.QUrl.fromLocalFile(path))
            eff.setVolume(0.85)  # 0.0~1.0
            # 懒加载：通过访问一次 source() 触发底层准备，减少首次播放延迟
            _ = eff.source()
            self.meow_effects.append(eff)
            self._apply_meow_volume()

    # ---------- 计时器 ----------
    def _fmt_time(self):
        m, s = divmod(self.time_left, 60)
        return f"⏰ {m:02d}:{s:02d}"

    def start_timer(self):
        if self.running: return
        self.running = True
        self._set_quote("专注开始喵～ 🐾" if self.quote_lang=="zh" else "Focus mode: meow on! 🐾")
        self._render_timer()
        QtCore.QTimer.singleShot(1000, self._tick_timer)

    def pause_timer(self):
        if not self.running: return
        self.running = False
        self._set_quote("先歇一歇，喝口水喵～" if self.quote_lang=="zh" else "Take a sip and a breath~")

    def reset_timer(self):
        self.running = False
        self.time_left = POMODORO_MIN * 60
        self._render_timer()
        self._set_quote("重置完成，随时开始~" if self.quote_lang=="zh" else "Reset done. Ready anytime!")

    def _tick_timer(self):
        if not self.running: return
        if self.time_left > 0:
            self.time_left -= 1
            self._render_timer()
            QtCore.QTimer.singleShot(1000, self._tick_timer)
        else:
            self.running = False
            self._set_quote("时间到啦！伸个懒腰再回来喵～ 😺" if self.quote_lang=="zh" else "Time! Stretch and come back meow~ 😺")

    def _render_timer(self):
        self.lbl_timer.setText(self._fmt_time())
        self.setWindowTitle(f"FocusCat 🐱 — {self._fmt_time()}")

    # ---------- 心跳：标题刷新 + 新句子着色 ----------
    def _heartbeat_tick(self):
        if self.running:
            self.setWindowTitle(f"FocusCat 🐱 — {self._fmt_time()}")
        # 扫描是否出现了新的句末符，如果有就给新句子上色
        self._scan_and_color_new_sentences()

    # ---------- 自动保存 ----------
    def _autosave(self):
        try:
            with open(DEFAULT_SAVE, "w", encoding="utf-8") as f:
                f.write(self.editor.toPlainText())
        except Exception:
            pass

def main():
    app = QtWidgets.QApplication([])
    QtWidgets.QApplication.setStyle("Fusion")
    w = FocusCat()
    w.show()
    app.exec()

if __name__ == "__main__":
    main()
