from __future__ import annotations

from pathlib import Path

import pandas as pd
from jinja2 import Template

HTML_TEMPLATE = Template(
    """
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8">
      <title>US Swing Scanner Report</title>
      <style>
        body { font-family: Georgia, "Noto Serif SC", serif; background: linear-gradient(180deg, #f2eee6, #ffffff); color: #1f2430; margin: 32px; }
        h1 { letter-spacing: 0.04em; }
        table { border-collapse: collapse; width: 100%; background: rgba(255,255,255,0.9); }
        th, td { border-bottom: 1px solid #d5cfbf; padding: 10px 12px; text-align: left; vertical-align: top; }
        th { background: #f5e8c7; }
        .muted { color: #6b7280; }
      </style>
    </head>
    <body>
      <h1>US Swing Scanner (Longbridge Edition)</h1>
      <p class="muted">Top {{ top_n }} candidates</p>
      {{ table_html }}
    </body>
    </html>
    """
)


def export_html(candidates: pd.DataFrame, path: Path, top_n: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    html = HTML_TEMPLATE.render(
        top_n=top_n,
        table_html=candidates.head(top_n).to_html(index=False, classes="candidates"),
    )
    path.write_text(html, encoding="utf-8")
    return path

