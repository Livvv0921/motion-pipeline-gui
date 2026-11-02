from __future__ import annotations

from PySide6.QtGui import QFontDatabase

# v0.5.7 final shared trace palettes from the user-selected reference image.
# Peak Lab and Compare Lab expose only these three named choices.
TRACE_PALETTES: dict[str, dict[str, object]] = {
    "coral_grove": {
        "name": "Coral Grove — Rose / Peach / Sage",
        "colors": ["#F14666", "#EE8980", "#FFCDAA", "#9CB998"],
    },
    "orchid_dusk": {
        "name": "Orchid Dusk — Indigo / Violet / Pink",
        "colors": ["#313866", "#50409A", "#964EC2", "#FF7BBF"],
    },
    "aqua_current": {
        "name": "Aqua Current — Cobalt / Cyan / Mint",
        "colors": ["#3E54D3", "#4F80E2", "#15CDCA", "#4FE0B6"],
    },
}

# The palette reference image uses #212226 as its dominant dark canvas.
NIGHT = {
    "background": "#212226",
    "panel": "#292B31",
    "panel_alt": "#30323A",
    "text": "#F6F4F2",
    "muted": "#B9BBC2",
    "indigo": "#313866",
    "violet": "#50409A",
    "purple": "#964EC2",
    "pink": "#FF7BBF",
}


def trace_palette_items() -> list[tuple[str, str]]:
    return [(key, str(spec["name"])) for key, spec in TRACE_PALETTES.items()]


def trace_palette_colors(key: str = "coral_grove", theme: str = "dark") -> list[str]:
    # Palette colors remain exact in both themes; only the plot canvas changes.
    spec = TRACE_PALETTES.get(key, TRACE_PALETTES["coral_grove"])
    return list(spec["colors"])  # type: ignore[arg-type]


def comparison_palette(key: str = "coral_grove", theme: str = "dark") -> list[str]:
    return trace_palette_colors(key, theme)


def movement_trace_colors(theme: str) -> dict[str, str]:
    """Theme-aware Movement Lab colors without another palette selector."""
    if theme == "light":
        # Darker indigo/violet plus a deepened cyan are crisp on white.
        return {"x": "#313866", "y": "#50409A", "z": "#0E8F91"}
    # Brighter Aqua Current colors read cleanly on #212226.
    return {"x": "#4F80E2", "y": "#15CDCA", "z": "#4FE0B6"}


def preferred_control_font() -> str:
    """Use Futura when installed, with sensible UI fallbacks otherwise."""
    try:
        families = set(QFontDatabase.families())
    except Exception:
        families = set()
    for candidate in ("Futura", "Futura PT", "Futura Std", "Avenir Next", "Segoe UI"):
        if candidate in families:
            return candidate
    return "Segoe UI"


def plot_palette(theme: str, trace_palette: str = "coral_grove") -> dict[str, str]:
    colors = trace_palette_colors(trace_palette, theme)
    while len(colors) < 3:
        colors.append(colors[-1] if colors else "#F14666")
    x, y, z = colors[:3]

    if theme == "light":
        return {
            "paper": "#FFFFFF",
            "plot": "#FFFFFF",
            "text": "#292529",
            "muted": "#6D686C",
            "grid": "#E6E2E1",
            "x": x,
            "y": y,
            "z": z,
            "peak": "#F14666",
            "peak_outline": "#FFFFFF",
            "peak_max": z,
            "peak_min": x,
            "peak_manual": "#50409A",
        }
    return {
        "paper": NIGHT["background"],
        "plot": NIGHT["background"],
        "text": NIGHT["text"],
        "muted": NIGHT["muted"],
        "grid": "#3A3C43",
        "x": x,
        "y": y,
        "z": z,
        "peak": colors[-1],
        "peak_outline": NIGHT["text"],
        "peak_max": z,
        "peak_min": x,
        "peak_manual": y,
    }


def stylesheet(theme: str) -> str:
    control_font = preferred_control_font()
    if theme == "light":
        # Final light theme: true white canvas with soft warm accents from Coral Grove.
        bg = "#FFFFFF"
        main_bg = "#FFFFFF"
        panel = "#FAF7F4"
        panel_alt = "#FFF0E7"
        sidebar = "#F7F8F5"
        sidebar_border = "#D7DED4"
        text = "#2B2728"
        muted = "#6D6768"
        border = "#DDD8D5"
        input_bg = "#FFFFFF"
        selected = "#FDE7E4"
        header = "#F6E0D4"
        tooltip_bg = "#2B2728"
        tooltip_text = "#FFFFFF"
        run_bg = "#F14666"
        run_hover = "#D93D5B"
        peak_bg = "#9CB998"
        peak_hover = "#89AA85"
        accent_bg = "#FFCDAA"
        accent_text = "#2B2728"
        focus = "#EE8980"
        run_text = "#FFFFFF"
        peak_text = "#253126"
        title_color = "#B73850"
    else:
        # Final dark theme matches the #212226 background from the reference image.
        bg = NIGHT["background"]
        main_bg = NIGHT["background"]
        panel = NIGHT["panel"]
        panel_alt = NIGHT["panel_alt"]
        sidebar = "#1D1E22"
        sidebar_border = "#3A3C43"
        text = NIGHT["text"]
        muted = NIGHT["muted"]
        border = "#44464F"
        input_bg = "#292B31"
        selected = NIGHT["indigo"]
        header = "#30323A"
        tooltip_bg = NIGHT["text"]
        tooltip_text = NIGHT["background"]
        run_bg = NIGHT["purple"]
        run_hover = NIGHT["violet"]
        peak_bg = NIGHT["pink"]
        peak_hover = "#E868AE"
        accent_bg = NIGHT["indigo"]
        accent_text = NIGHT["text"]
        focus = NIGHT["pink"]
        run_text = "#FFFFFF"
        peak_text = "#212226"
        title_color = "#D7B8F0"

    return f'''
QWidget {{
    background: {bg};
    color: {text};
    font-family: "Courier New";
    font-size: 12px;
}}
QMainWindow {{ background: {main_bg}; }}
QFrame#utilityBar {{ background: {panel}; border-bottom: 1px solid {border}; }}
QFrame#sidebar {{ background: {sidebar}; border-right: 1px solid {sidebar_border}; }}
QFrame#consoleFrame {{ background: {main_bg}; border-top: 1px solid {border}; }}
QLabel#brandLabel {{ font-size: 18px; font-weight: bold; color: {text}; padding: 8px; }}
QLabel#pageTitle {{ font-family: "Courier New"; font-size: 24px; font-weight: bold; color: {text}; }}
QLabel#subtitle {{ font-family: "Courier New"; color: {muted}; font-size: 12px; }}
QLabel#hintLabel {{
    color: {muted}; background: {panel}; border: 1px solid {border};
    border-radius: 5px; padding: 7px;
}}
QLabel#sectionTitle {{ font-family: "Courier New"; font-size: 14px; font-weight: bold; color: {title_color}; }}
QLabel#plotTitle {{ font-family: "Courier New"; font-size: 15px; font-weight: bold; color: {title_color}; }}
QLabel#moveStatus {{
    font-family: "{control_font}"; color: {focus}; font-weight: bold;
    padding: 4px 0px;
}}
QLabel#moonStatus {{
    font-family: "{control_font}"; color: {focus}; font-weight: bold; padding: 4px 8px;
}}
QDockWidget {{ color: {text}; font-family: "Courier New"; }}
QDockWidget::title {{ background: {panel_alt}; padding: 6px; border-bottom: 1px solid {border}; }}
QGroupBox {{
    border: 1px solid {border}; border-radius: 6px; margin-top: 2px;
    padding: 10px; font-family: "Courier New"; color: {text};
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QLineEdit, QPlainTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox, QTableWidget {{
    background: {input_bg}; border: 1px solid {border}; border-radius: 4px;
    padding: 5px; color: {text}; selection-background-color: {run_hover};
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ font-family: "{control_font}"; }}
QComboBox QAbstractItemView {{
    background: {panel}; color: {text}; selection-background-color: {run_hover};
    font-family: "{control_font}";
}}
QPushButton {{
    background: {panel_alt}; border: 1px solid {border}; border-radius: 5px;
    padding: 7px 11px; color: {text}; font-family: "{control_font}"; font-weight: 500;
}}
QPushButton:hover {{ border-color: {focus}; background: {selected}; }}
QPushButton:pressed {{ background: {panel}; }}
QPushButton:disabled {{ color: {muted}; background: {panel}; }}
QPushButton#utilityButton {{ background: transparent; border: none; padding: 7px 10px; color: {title_color}; }}
QPushButton#utilityButton:hover {{ background: {selected}; border: none; }}
QPushButton#navButton {{ text-align: left; border: none; background: transparent; padding: 8px; }}
QPushButton#navButton[selected="true"] {{ background: {selected}; border-left: 3px solid {focus}; }}
QPushButton#browseButton {{ padding: 5px 8px; }}
QPushButton#runButton {{
    background: {run_bg}; color: {run_text}; border: 1px solid {focus};
    border-radius: 6px; padding: 9px 16px; font-family: "{control_font}"; font-weight: 700;
}}
QPushButton#runButton:hover {{ background: {run_hover}; border-color: {focus}; }}
QPushButton#peakButton {{
    background: {peak_bg}; color: {peak_text}; border: 1px solid {focus};
    border-radius: 6px; padding: 10px 14px; font-family: "{control_font}"; font-weight: 700;
}}
QPushButton#peakButton:hover {{ background: {peak_hover}; }}
QPushButton#accentButton {{
    background: {accent_bg}; color: {accent_text}; border: 1px solid {focus};
    font-weight: 650;
}}
QPushButton#dangerButton {{ border-color: {focus}; }}
QToolButton#sectionToggle {{
    background: {panel}; color: {text}; border: 1px solid {focus}; border-radius: 6px;
    padding: 8px 10px; text-align: left; font-family: "Courier New"; font-weight: bold;
}}
QToolButton#sectionToggle:hover {{ border-color: {focus}; background: {selected}; }}
QCheckBox {{ spacing: 5px; font-family: "{control_font}"; }}
QCheckBox::indicator {{ width: 15px; height: 15px; }}
QTabWidget::pane {{ border: 1px solid {border}; border-radius: 4px; }}
QTabBar::tab {{
    background: {panel}; color: {muted}; padding: 8px 16px; border: 1px solid {border};
    font-family: "{control_font}";
}}
QTabBar::tab:selected {{ background: {selected}; color: {text}; border-bottom: 2px solid {focus}; }}
QHeaderView::section {{
    background: {header}; color: {text}; border: 1px solid {border}; padding: 5px;
    font-family: "{control_font}";
}}
QTableWidget {{ gridline-color: {border}; alternate-background-color: {input_bg}; }}
QTableWidget::item {{ background: {input_bg}; color: {text}; }}
QTableWidget::item:selected {{ background: {accent_bg}; color: {accent_text}; }}
QProgressBar {{ background: {panel}; border: 1px solid {border}; border-radius: 4px; text-align: center; }}
QProgressBar::chunk {{ background: {run_bg}; }}
QProgressBar#navProgress {{ min-height: 5px; max-height: 5px; border: none; background: {panel_alt}; }}
QProgressBar#navProgress::chunk {{ background: {focus}; border-radius: 2px; }}
QSplitter::handle {{ background: {border}; width: 2px; height: 2px; }}
QToolTip {{ background: {tooltip_bg}; color: {tooltip_text}; border: 1px solid {border}; padding: 5px; }}
QScrollBar:vertical {{ background: {panel}; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {border}; min-height: 28px; border-radius: 5px; }}
QScrollBar:horizontal {{ background: {panel}; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {border}; min-width: 28px; border-radius: 5px; }}
'''
