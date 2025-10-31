# -*- coding: utf-8 -*-
"""
Core tests for FocusCat (headless-friendly).
Run:
  python -m unittest -v test_focuscat.py
"""

import os
import re
import tempfile
import unittest
import contextlib
from unittest import mock

# Headless Qt
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets
import focuscat_qt as app


# ---------- Base mixin: create one QApplication & one widget per test ----------
class WithQtAndWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        # 每个用例一个 FocusCat 实例，避免状态相互影响
        self.w = app.FocusCat()


# ----------------------- Sentence splitting tests ----------------------------
class TestSentenceSplitting(WithQtAndWidget):
    def test_abbrev_not_split(self):
        # e.g., i.e., etc. 不应被当作句末
        txt = "We test e.g., i.e., and etc. inside a sentence. Next ends here."
        ends = list(self.w._iter_sentence_ends(text=txt, start_idx=0))
        self.assertEqual(len(ends), 2, msg=f"ends={ends}")

    def test_decimal_not_split(self):
        txt = "Value is 3.14 in math. Done."
        ends = list(self.w._iter_sentence_ends(text=txt, start_idx=0))
        self.assertEqual(len(ends), 2)

    def test_inside_parentheses_not_split(self):
        txt = "This sentence has dots (ver. 1.2.3 ... ok?) and continues. End."
        ends = list(self.w._iter_sentence_ends(text=txt, start_idx=0))
        self.assertEqual(len(ends), 2)


# ------------------- Normalize & gradient related tests ----------------------
class TestNormalizeAndGradient(WithQtAndWidget):
    def test_normalize_span_trims_and_drops_ending_punct(self):
        s = "  Hello world!  "
        # 把文本放入编辑器，_normalize_span 内部会取 _doc_text()
        self.w.editor.setPlainText(s)
        start, end = 0, len(s)
        ns, ne, clean = self.w._normalize_span(start=start, end=end)
        self.assertEqual(s[ns:ne], "Hello world!")
        self.assertEqual(clean, "hello world")

    def test_stable_gradient_is_deterministic(self):
        base = "#4D96FF"
        g1 = self.w._stable_gradient(base_hex=base, length=12, seed=123)
        g2 = self.w._stable_gradient(base_hex=base, length=12, seed=123)
        self.assertEqual([c.rgba() for c in g1], [c.rgba() for c in g2])


# ---------------------- Quotes / Themes / Persistence ------------------------
class TestQuotesAndTheme(WithQtAndWidget):
    def test_quote_language_switch(self):
        self.w._set_quote_lang("zh")
        q1 = self.w._random_quote()
        self.assertTrue(any('\u4e00' <= ch <= '\u9fff' for ch in q1))  # CJK 存在
        self.w._set_quote_lang("en")
        q2 = self.w._random_quote()
        self.assertRegex(q2, r"[A-Za-z]")

    def test_apply_theme_no_crash(self):
        for key in app.THEMES.keys():
            self.w._apply_theme(key)  # 不应报错


class TestMeowCounterPersistence(WithQtAndWidget):
    def test_meow_count_save_and_load(self):
        with tempfile.TemporaryDirectory() as td:
            fake_count = os.path.join(td, "meow_count.txt")

            # 将计数文件路径替换为临时文件，避免污染真实数据
            with mock.patch.object(self.w, "_count_path", return_value=fake_count):
                self.w.meow_count = 0
                self.w._save_meow_count()
                self.assertTrue(os.path.exists(fake_count))

                self.w.meow_count = 42
                self.w._save_meow_count()

                # 新实例应能读回 42
                w2 = app.FocusCat()
                with mock.patch.object(w2, "_count_path", return_value=fake_count):
                    w2._load_meow_count()
                    self.assertEqual(w2.meow_count, 42)
                    self.assertEqual(w2.lbl_meow_count.text(), "42")


# ----------------------------- Smoke test -----------------------------------
class TestSmokyEditor(WithQtAndWidget):
    def test_construct_and_colorize_once(self):
        sample = "Hello world. e.g., test inside. Done!"
        self.w.editor.setPlainText(sample)
        self.w._colorize_all_sentences_once()
        # 至少应已上色到第一个句末之后
        self.assertGreaterEqual(self.w._last_colored_pos, len("Hello world."))


if __name__ == "__main__":
    unittest.main(verbosity=2)
