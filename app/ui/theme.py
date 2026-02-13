from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    name: str
    bg: str
    panel_bg: str
    sidebar_bg: str
    activity_bg: str
    editor_bg: str
    input_bg: str
    border_subtle: str
    border_strong: str
    text: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_pressed: str
    selection: str
    focus_ring: str
    danger: str
    success: str
    status_bg: str
    status_text: str
    tab_bg: str
    tab_active_bg: str
    hover_bg: str
    code_bg: str


DARK_TOKENS = ThemeTokens(
    name="dark",
    bg="#1e1e1e",
    panel_bg="#252526",
    sidebar_bg="#252526",
    activity_bg="#333333",
    editor_bg="#1e1e1e",
    input_bg="#2d2d30",
    border_subtle="#3e3e42",
    border_strong="#5a5d62",
    text="#cccccc",
    text_muted="#8d9094",
    accent="#0e639c",
    accent_hover="#1177bb",
    accent_pressed="#0a4f7a",
    selection="#264f78",
    focus_ring="#3794ff",
    danger="#f14c4c",
    success="#4ec9b0",
    status_bg="#007acc",
    status_text="#ffffff",
    tab_bg="#2d2d30",
    tab_active_bg="#1e1e1e",
    hover_bg="#2a2d2e",
    code_bg="#2a2d31",
)

LIGHT_TOKENS = ThemeTokens(
    name="light",
    bg="#f5f5f5",
    panel_bg="#ffffff",
    sidebar_bg="#f3f3f3",
    activity_bg="#e8e8e8",
    editor_bg="#ffffff",
    input_bg="#ffffff",
    border_subtle="#d4d4d4",
    border_strong="#b5b5b5",
    text="#1f1f1f",
    text_muted="#616161",
    accent="#005fb8",
    accent_hover="#0a72d5",
    accent_pressed="#00498d",
    selection="#add6ff",
    focus_ring="#005fb8",
    danger="#c72e0f",
    success="#0f7b0f",
    status_bg="#007acc",
    status_text="#ffffff",
    tab_bg="#ececec",
    tab_active_bg="#ffffff",
    hover_bg="#e9eef6",
    code_bg="#eef2f8",
)


def get_theme_tokens(theme_name: str) -> ThemeTokens:
    if theme_name == "light":
        return LIGHT_TOKENS
    return DARK_TOKENS


def build_app_stylesheet(tokens: ThemeTokens) -> str:
    return f"""
    QWidget {{
        color: {tokens.text};
        background: {tokens.bg};
        font-family: "Segoe UI Variable", "Segoe UI", "Noto Sans", sans-serif;
        font-size: 16px;
    }}
    QMainWindow {{
        background: {tokens.bg};
    }}
    QFrame#workbenchRoot {{
        background: {tokens.bg};
    }}
    QFrame#activityBar {{
        background: {tokens.activity_bg};
        border-right: 1px solid {tokens.border_subtle};
    }}
    QFrame#sideBar {{
        background: {tokens.sidebar_bg};
        border-right: 1px solid {tokens.border_subtle};
    }}
    QFrame#editorSurface {{
        background: {tokens.editor_bg};
    }}
    QFrame#sectionCard {{
        background: {tokens.panel_bg};
        border: 1px solid {tokens.border_subtle};
        border-radius: 6px;
    }}
    QToolBar#titleToolbar {{
        background: {tokens.panel_bg};
        border: none;
        border-bottom: 1px solid {tokens.border_subtle};
        spacing: 4px;
        padding: 4px;
    }}
    QToolButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 5px;
        padding: 4px 8px;
        color: {tokens.text};
    }}
    QToolButton:hover {{
        background: {tokens.hover_bg};
        border-color: {tokens.border_subtle};
    }}
    QToolButton:pressed {{
        background: {tokens.accent_pressed};
        border-color: {tokens.accent_pressed};
    }}
    QPushButton {{
        background: {tokens.input_bg};
        border: 1px solid {tokens.border_subtle};
        border-radius: 5px;
        padding: 5px 10px;
    }}
    QPushButton:hover {{
        background: {tokens.hover_bg};
        border-color: {tokens.border_strong};
    }}
    QPushButton:pressed {{
        background: {tokens.selection};
    }}
    QLineEdit, QPlainTextEdit, QTextBrowser, QListWidget, QComboBox, QTabBar::tab {{
        background: {tokens.input_bg};
        border: 1px solid {tokens.border_subtle};
        border-radius: 5px;
        selection-background-color: {tokens.selection};
        selection-color: {tokens.text};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QListWidget:focus, QComboBox:focus {{
        border: 1px solid {tokens.focus_ring};
    }}
    QListWidget {{
        padding: 2px;
        outline: none;
    }}
    QListWidget::item {{
        border: none;
        border-radius: 4px;
        padding: 4px 6px;
        margin: 1px 0;
    }}
    QListWidget::item:hover {{
        background: {tokens.hover_bg};
    }}
    QListWidget::item:selected {{
        background: {tokens.selection};
        color: {tokens.text};
    }}
    QTabWidget::pane {{
        border: none;
        background: {tokens.editor_bg};
    }}
    QTabBar::tab {{
        background: {tokens.tab_bg};
        color: {tokens.text_muted};
        padding: 6px 12px;
        margin-right: 2px;
        border-top-left-radius: 5px;
        border-top-right-radius: 5px;
    }}
    QTabBar::tab:selected {{
        background: {tokens.tab_active_bg};
        color: {tokens.text};
        border-color: {tokens.border_subtle};
    }}
    QSplitter::handle {{
        background: {tokens.border_subtle};
    }}
    QSplitter::handle:hover {{
        background: {tokens.focus_ring};
    }}
    QStatusBar {{
        background: {tokens.status_bg};
        color: {tokens.status_text};
        border-top: 1px solid {tokens.border_subtle};
    }}
    QStatusBar QLabel {{
        color: {tokens.status_text};
        background: transparent;
        padding: 0 6px;
    }}
    QLabel#muted {{
        color: {tokens.text_muted};
    }}
    """


def build_markdown_css(tokens: ThemeTokens) -> str:
    return build_notion_preview_css(tokens)


def build_notion_preview_css(tokens: ThemeTokens) -> str:
    return f"""
    :root {{
      --bg: {tokens.bg};
      --bg-elev-1: {tokens.panel_bg};
      --bg-elev-2: {tokens.input_bg};
      --text: {tokens.text};
      --text-muted: {tokens.text_muted};
      --border-subtle: {tokens.border_subtle};
      --accent: {tokens.accent};
      --selection: {tokens.selection};
      --code-bg: {tokens.code_bg};
      --shadow: {tokens.hover_bg};
    }}
    body {{
      font-family: "Segoe UI Variable", "Segoe UI", "Noto Sans", sans-serif;
      font-size: 17px;
      line-height: 1.75;
      color: var(--text);
      background: radial-gradient(circle at top right, var(--bg-elev-1), var(--bg));
      margin: 0;
      padding: 0;
    }}
    * {{
      box-sizing: border-box;
    }}
    ::selection {{
      background: var(--selection);
    }}
    .preview-root {{
      min-height: 100vh;
      background: radial-gradient(circle at 10% 10%, var(--bg-elev-1), var(--bg));
      padding: 0;
    }}
    .page-container {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px 28px 60px;
    }}
    .page-title-pill {{
      display: inline-flex;
      align-items: center;
      max-width: 60%;
      padding: 10px 20px;
      border-radius: 8px;
      background: var(--bg-elev-2);
      border: 1px solid var(--border-subtle);
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-weight: 700;
      font-size: 26px;
      line-height: 1.25;
      margin: 0 0 20px 0;
      box-shadow: 0 4px 14px var(--shadow);
    }}
    .situation-block {{
      background: var(--bg-elev-1);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 14px;
      margin: 0 0 14px 0;
    }}
    .situation-block h2 {{
      margin: 0 0 12px 0;
      font-size: 18px;
      line-height: 1.35;
      font-weight: 650;
      color: var(--text);
    }}
    .columns-2 {{
      display: grid;
      grid-template-columns: minmax(0, 58fr) minmax(0, 42fr);
      gap: 24px;
      align-items: start;
    }}
    .tf-panel {{
      background: var(--bg-elev-2);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 10px;
      min-height: 74px;
    }}
    .tf-panel-header {{
      display: flex;
      align-items: center;
      gap: 8px;
      min-height: 42px;
      border: 1px solid var(--border-subtle);
      border-radius: 9px;
      background: var(--bg-elev-1);
      padding: 8px 10px;
      font-weight: 600;
      margin-bottom: 10px;
      color: var(--text);
    }}
    .tf-panel-header .tf-icon {{
      color: var(--text-muted);
      font-size: 14px;
      line-height: 1;
    }}
    .tf-panel-body {{
      color: var(--text);
    }}
    .image-block {{
      max-width: 9.5%;
      border-radius: 8px;
      overflow: hidden;
      margin: 0 auto 10px auto;
      border: 1px solid var(--border-subtle);
      background: var(--bg);
    }}
    .image-block img {{
      display: block;
      width: 100%;
      height: auto;
      max-height: 28px;
      object-fit: contain;
      margin: 0;
    }}
    .placeholder-block {{
      height: 42px;
      border: 1px dashed var(--border-subtle);
      border-radius: 8px;
      background: var(--bg-elev-1);
      margin: 0 0 10px 0;
    }}
    .panel-text {{
      margin: 0;
      font-size: 17px;
      line-height: 1.75;
    }}
    .panel-text + .panel-text {{
      margin-top: 8px;
    }}
    .panel-label {{
      color: var(--text-muted);
      font-size: 12px;
      line-height: 1.35;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin: 0 0 4px 0;
    }}
    .panel-fixed {{
      margin-bottom: 10px;
    }}
    .panel-user {{
      margin-top: 0;
    }}
    .panel-muted {{
      color: var(--text-muted);
      font-size: 13px;
      line-height: 1.55;
    }}
    .kv-block {{
      margin: 0 0 10px 0;
    }}
    .kv-label {{
      color: var(--text);
      font-size: 17px;
      line-height: 1.45;
      font-weight: 650;
      margin: 0 0 4px 0;
    }}
    .kv-value {{
      color: var(--text);
      font-size: 17px;
      line-height: 1.75;
      margin: 0;
    }}
    .markdown-card {{
      background: var(--bg-elev-1);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 14px;
      margin: 0 0 14px 0;
    }}
    .markdown-card h2 {{
      margin: 0 0 10px 0;
    }}
    .markdown-card > :last-child {{
      margin-bottom: 0;
    }}
    h1, h2, h3, h4, h5, h6 {{
      margin: 10px 0 6px;
      color: var(--text);
      line-height: 1.35;
    }}
    h1 {{
      font-size: 28px;
      font-weight: 700;
    }}
    h2 {{
      font-size: 19px;
      font-weight: 650;
    }}
    h3 {{
      font-size: 17px;
      font-weight: 600;
    }}
    p {{
      margin: 8px 0;
      color: var(--text);
      font-size: 17px;
      line-height: 1.75;
    }}
    ul, ol {{
      margin: 6px 0 10px 22px;
      padding: 0;
    }}
    li {{
      margin: 3px 0;
    }}
    img {{
      display: block;
      max-width: 10%;
      height: auto;
      max-height: 33px;
      object-fit: contain;
      border-radius: 8px;
      margin: 8px auto;
    }}
    pre {{
      background: var(--bg-elev-2);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 10px;
      white-space: pre-wrap;
      word-wrap: break-word;
      margin: 8px 0 10px 0;
    }}
    code {{
      background: var(--code-bg);
      border: 1px solid var(--border-subtle);
      border-radius: 4px;
      padding: 1px 4px;
      font-size: 12px;
      font-family: "Cascadia Mono", "Consolas", "Fira Code", monospace;
    }}
    .inline-code {{
      background: var(--code-bg);
      border: 1px solid var(--border-subtle);
      border-radius: 4px;
      padding: 1px 4px;
      font-size: 12px;
      font-family: "Cascadia Mono", "Consolas", "Fira Code", monospace;
    }}
    table, th, td {{
      border: 1px solid var(--border-subtle);
      border-collapse: collapse;
      padding: 6px 8px;
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    @media (max-width: 1100px) {{
      .page-container {{
        padding: 24px 18px 44px;
      }}
      .page-title-pill {{
        max-width: 100%;
        font-size: 22px;
      }}
      .columns-2 {{
        grid-template-columns: 1fr;
        gap: 16px;
      }}
    }}
    """
