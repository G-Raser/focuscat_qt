# -*- coding: utf-8 -*-
"""
Automated unit tests for FocusCat (headless-friendly).
FocusCat 自动化单元测试（无界面可运行）。
Run:
  python -m unittest -v test_focuscat.py
"""

import os, re, tempfile, unittest, contextlib
from unittest import mock

# ===== Headless Qt environment / 无界面 Qt 环境 =====
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets
import focuscat_qt as app


# ===== Base setup / 基础设置 =====
class WithQtAndWidget(unittest.TestCase):
    """Base test class that provides QApplication and FocusCat instance.
       为测试提供 QApplication 与 FocusCat 实例的基类。"""
    @classmethod
    def setUpClass(cls):
        cls._qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        # Each test gets a fresh FocusCat instance / 每个测试用例独立实例
        self.w = app.FocusCat()


# ===== Sentence splitting / 句子切分测试 =====
class TestSentenceSplitting(WithQtAndWidget):
    """Verify sentence boundary detection logic.
       验证句末检测逻辑是否正确。"""
    def test_abbrev_not_split(self):
        """Abbreviations should not break sentences.
           缩写词（如 e.g.）不应被当作句末。"""
        txt = "We test e.g., i.e., and etc. inside a sentence. Next ends here."
        ends = list(self.w._iter_sentence_ends(text=txt, start_idx=0))
        self.assertEqual(len(ends), 2, msg=f"ends={ends}")

    def test_decimal_not_split(self):
        """Decimals like 3.14 should not trigger sentence end.
           小数点如 3.14 不应触发句末识别。"""
        txt = "Value is 3.14 in math. Done."
        ends = list(self.w._iter_sentence_ends(text=txt, start_idx=0))
        self.assertEqual(len(ends), 2)

    def test_inside_parentheses_not_split(self):
        """Dots inside parentheses should be ignored.
           括号内的点不应被判定为句末。"""
        txt = "This sentence has dots (ver. 1.2.3 ... ok?) and continues. End."
        ends = list(self.w._iter_sentence_ends(text=txt, start_idx=0))
        self.assertEqual(len(ends), 2)


# ===== Normalize & Gradient / 归一化与渐变测试 =====
class TestNormalizeAndGradient(WithQtAndWidget):
    """Validate normalization and gradient generation.
       验证文本归一化与渐变生成的正确性。"""
    def test_normalize_span_trims_and_drops_ending_punct(self):
        """Should trim spaces and strip trailing punctuation.
           应去除空白并移除末尾标点。"""
        s = "  Hello world!  "
        self.w.editor.setPlainText(s)
        start, end = 0, len(s)
        ns, ne, clean = self.w._normalize_span(start=start, end=end)
        self.assertEqual(s[ns:ne], "Hello world!")
        self.assertEqual(clean, "hello world")

    def test_stable_gradient_is_deterministic(self):
        """Gradient generation must be deterministic.
           渐变生成应保持确定性。"""
        base = "#4D96FF"
        g1 = self.w._stable_gradient(base_hex=base, length=12, seed=123)
        g2 = self.w._stable_gradient(base_hex=base, length=12, seed=123)
        self.assertEqual([c.rgba() for c in g1], [c.rgba() for c in g2])


# ===== Quotes / Theme / Persistence / 喵语、主题与持久化测试 =====
class TestQuotesAndTheme(WithQtAndWidget):
    """Check quote rotation, theme switching, and language settings.
       检查喵语轮换、主题切换与语言设置。"""
    def test_quote_language_switch(self):
        """Switching between ZH and EN should produce correct quote sets.
           切换中英文后应输出对应语言的喵语。"""
        self.w._set_quote_lang("zh")
        q1 = self.w._random_quote()
        self.assertTrue(any('\u4e00' <= ch <= '\u9fff' for ch in q1))
        self.w._set_quote_lang("en")
        q2 = self.w._random_quote()
        self.assertRegex(q2, r"[A-Za-z]")

    def test_apply_theme_no_crash(self):
        """Applying any theme should not raise an error.
           应用任意主题均不应报错。"""
        for key in app.THEMES.keys():
            self.w._apply_theme(key)


# ===== Meow counter / 喵叫计数测试 =====
class TestMeowCounterPersistence(WithQtAndWidget):
    """Test saving and loading of meow count file.
       测试喵叫计数文件的保存与读取。"""
    def test_meow_count_save_and_load(self):
        """Count should persist correctly between sessions.
           计数应在不同会话间保持一致。"""
        with tempfile.TemporaryDirectory() as td:
            fake_count = os.path.join(td, "meow_count.txt")
            with mock.patch.object(self.w, "_count_path", return_value=fake_count):
                self.w.meow_count = 0
                self.w._save_meow_count()
                self.assertTrue(os.path.exists(fake_count))

                self.w.meow_count = 42
                self.w._save_meow_count()

                w2 = app.FocusCat()
                with mock.patch.object(w2, "_count_path", return_value=fake_count):
                    w2._load_meow_count()
                    self.assertEqual(w2.meow_count, 42)
                    self.assertEqual(w2.lbl_meow_count.text(), "42")


# ===== Smoke test / 冒烟测试 =====
class TestSmokyEditor(WithQtAndWidget):
    """Ensure basic construction and coloring functions run without errors.
       确保基本构建与着色流程无报错。"""
    def test_construct_and_colorize_once(self):
        """Should colorize sentences without crashing.
           应能顺利完成句子上色。"""
        sample = "Hello world. e.g., test inside. Done!"
        self.w.editor.setPlainText(sample)
        self.w._colorize_all_sentences_once()
        self.assertGreaterEqual(self.w._last_colored_pos, len("Hello world."))


# ===== Main entry / 主执行入口 =====
if __name__ == "__main__":
    unittest.main(verbosity=2)
