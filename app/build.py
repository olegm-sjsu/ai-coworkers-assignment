#!/usr/bin/env python3
"""Inline the coach engine into the page, because a published artifact is one self-contained file."""
from pathlib import Path

here = Path(__file__).parent
page = (here / "page.html").read_text().replace("/*CORE*/", (here / "core.js").read_text())
out = here.parent / "dist" / "coworkers.html"
out.parent.mkdir(exist_ok=True)
out.write_text(page)
print(out, len(page), "bytes")
