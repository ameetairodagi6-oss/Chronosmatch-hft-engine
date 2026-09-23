"""
setup.py
--------
Build script that compiles order_book.pyx into a native C-extension.

Run with:
    python engine/setup.py build_ext --inplace

(Run this from inside the engine/ folder, or adjust the path in
Extension() below if running from the project root.)

Requires a C compiler on your system:
  - Windows: Microsoft C++ Build Tools (Visual Studio Build Tools)
  - Mac: Xcode Command Line Tools (xcode-select --install)
  - Linux: gcc (usually already installed, or `sudo apt install build-essential`)
"""

from setuptools import setup
from Cython.Build import cythonize

setup(
    ext_modules=cythonize("order_book.pyx", language_level=3),
    zip_safe=False,
)