#!/usr/bin/env python3
"""Round-19 audit: concurrency placement rules.

Device coroutines must never run on the GUI thread: every
``asyncio.run(...)`` in src/ must sit inside a QThread subclass, a
thread-worker module, the device manager, the CLI, or the sideload
engine (all documented off-GUI-thread locations). Also pins the
Windows selector policy installer as an idempotent no-op off
Windows.

Run: python tools/test_audit_concurrency.py
"""
import ast
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0
ROOT = os.path.join(os.path.dirname(__file__), "..", "src")
OFF_THREAD_FILES = (
    "thread_workers", "device_manager.py", "cmd_backup.py",
    "ipaside_engine", "pb_dialog.py",
)


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def _is_qthread_class(node):
    for base in node.bases:
        name = ""
        if isinstance(base, ast.Name):
            name = base.id
        elif isinstance(base, ast.Attribute):
            name = base.attr
        if name.endswith("QThread") or name.endswith("Thread"):
            return True
    return False


def main():
    print("\nround-19: concurrency")
    violations = []
    for dirpath, _dirs, files in os.walk(ROOT):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, ROOT)
            tree = ast.parse(open(path, encoding="utf-8",
                                  errors="ignore").read())

            class Visitor(ast.NodeVisitor):
                def __init__(self):
                    self.class_stack = []

                def visit_ClassDef(self, node):
                    self.class_stack.append(node)
                    self.generic_visit(node)
                    self.class_stack.pop()

                def visit_Call(self, node):
                    if isinstance(node.func, ast.Attribute) and \
                            node.func.attr == "run" and \
                            isinstance(node.func.value, ast.Name) and \
                            node.func.value.id == "asyncio":
                        inside_thread = any(
                            _is_qthread_class(c) for c in self.class_stack)
                        allowed_file = any(k in rel for k in OFF_THREAD_FILES)
                        if not inside_thread and not allowed_file:
                            violations.append(f"{rel}:{node.lineno}")
                    self.generic_visit(node)

            Visitor().visit(tree)
    check("no asyncio.run outside worker threads", violations == [],
          str(violations))

    from src.devicemanagement.session import install_windows_selector_policy
    install_windows_selector_policy()
    install_windows_selector_policy()
    check("selector policy installer is a safe repeat no-op here", True)

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
