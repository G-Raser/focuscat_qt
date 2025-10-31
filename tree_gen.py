from __future__ import annotations
import os, sys, argparse, re
from pathlib import Path

DEFAULT_IGNORES = {
    ".git", ".idea", ".vscode", ".venv", "__pycache__", "node_modules",
    ".pytest_cache", "dist", "build", ".DS_Store"
}

def build_tree(root: Path, ignores: set[str], max_depth: int = 10) -> list[str]:
    lines: list[str] = []
    def walk(dir_path: Path, prefix: str = "", depth: int = 0):
        if depth > max_depth:
            return
        entries = sorted([e for e in dir_path.iterdir()
                          if e.name not in ignores and not e.name.startswith(".gitmodules")],
                         key=lambda p: (p.is_file(), p.name.lower()))
        for i, p in enumerate(entries):
            is_last = (i == len(entries) - 1)
            branch = "└── " if is_last else "├── "
            lines.append(f"{prefix}{branch}{p.name}")
            if p.is_dir():
                extension = "    " if is_last else "│   "
                walk(p, prefix + extension, depth + 1)
    lines.append(f"{root.name}/")
    walk(root, "", 0)
    return lines

def write_markdown_block(lines: list[str]) -> str:
    return "```\n" + "\n".join(lines) + "\n```\n"

def patch_readme(readme_path: Path, block_md: str,
                 start="<!-- PROJECT_STRUCTURE_START -->",
                 end="<!-- PROJECT_STRUCTURE_END -->") -> None:
    text = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    pattern = re.compile(
        re.escape(start) + r".*?" + re.escape(end),
        flags=re.DOTALL
    )
    replacement = f"{start}\n{block_md}{end}"
    if pattern.search(text):
        text = pattern.sub(replacement, text)
    else:
        # 若无标记，追加到文末
        if text and not text.endswith("\n"):
            text += "\n"
        text += "\n" + replacement + "\n"
    readme_path.write_text(text, encoding="utf-8")

def main():
    ap = argparse.ArgumentParser(description="Generate project structure as Markdown.")
    ap.add_argument("--root", type=str, default=".", help="Project root directory.")
    ap.add_argument("--ignore", type=str, nargs="*", default=[],
                    help="Extra names to ignore (dirs/files).")
    ap.add_argument("--max-depth", type=int, default=10, help="Max depth of tree.")
    ap.add_argument("--out", type=str, default="", help="Write to file (Markdown).")
    ap.add_argument("--patch-readme", type=str, default="",
                    help="If set, patch README between markers.")
    ap.add_argument("--start-marker", type=str, default="<!-- PROJECT_STRUCTURE_START -->")
    ap.add_argument("--end-marker", type=str, default="<!-- PROJECT_STRUCTURE_END -->")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    ignores = set(DEFAULT_IGNORES) | set(args.ignore)
    tree_lines = build_tree(root, ignores, args.max_depth)
    md = write_markdown_block(tree_lines)

    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"Wrote: {args.out}")
    else:
        print(md)

    if args.patch_readme:
        patch_readme(Path(args.patch_readme), md, args.start_marker, args.end_marker)
        print(f"Patched README: {args.patch_readme}")

if __name__ == "__main__":
    main()
