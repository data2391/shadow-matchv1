"""
cli/interface.py — Rich-powered CLI interface for SHADOW-MATCH
"""

from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich import box
from datetime import datetime

console = Console()

SHADOW_ASCII = r"""
 ██████╗██╗  ██╗ █████╗ ██████╗  ██████╗ ██╗    ██╗       ███╗   ███╗ █████╗ ████████╗ ██████╗██╗  ██╗
██╔════╝██║  ██║██╔══██╗██╔══██╗██╔═══██╗██║    ██║       ████╗ ████║██╔══██╗╚══██╔══╝██╔════╝██║  ██║
╚█████╗ ███████║███████║██║  ██║██║   ██║██║ █╗ ██║  ───  ██╔████╔██║███████║   ██║   ██║     ███████║
 ╚═══██╗██╔══██║██╔══██║██║  ██║██║   ██║██║███╗██║  ───  ██║╚██╔╝██║██╔══██║   ██║   ██║     ██╔══██║
██████╔╝██║  ██║██║  ██║██████╔╝╚██████╔╝╚███╔███╔╝       ██║ ╚═╝ ██║██║  ██║   ██║   ╚██████╗██║  ██║
╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝  ╚═════╝  ╚══╝╚══╝        ╚═╝     ╚═╝╚═╝  ╚═╝   ╚═╝    ╚═════╝╚═╝  ╚═╝
"""

VERSION_LINE = "  [ OSINT FACIAL RECOGNITION ENGINE v2.0 ]  ——  SHADOW-MATCH"
TAGLINE      = "  Powered by InsightFace · ArcFace · Yandex Visual Search · Playwright"

def splash_screen():
    console.print()
    ascii_text = Text(SHADOW_ASCII, style="bold bright_blue")
    console.print(ascii_text)

    version_text = Text(VERSION_LINE, style="bold cyan")
    tagline_text = Text(TAGLINE, style="dim cyan")
    console.print(version_text)
    console.print(tagline_text)

    info_table = Table(box=box.MINIMAL, show_header=False, padding=(0, 2))
    info_table.add_column(style="bright_black")
    info_table.add_column(style="bright_cyan")
    info_table.add_row("ENGINE",   "InsightFace · buffalo_l / buffalo_s")
    info_table.add_row("PIVOT",    "Yandex Visual Search (Playwright)")
    info_table.add_row("MATCHER",  "ArcFace Cosine Distance < 0.35")
    info_table.add_row("STEALTH",  "BytesIO · Zero disk traces (-S)")
    info_table.add_row("WEB UI",   "FastAPI + WebSocket Dashboard")

    panel = Panel(
        info_table,
        border_style="bright_blue",
        title="[bold bright_blue]◈ SYSTEM READY ◈[/bold bright_blue]",
        title_align="center",
        padding=(1, 4),
    )
    console.print(panel)
    console.print(
        f"  [bright_black]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bright_black]  "
        "[bright_green]● OPERATIONAL[/bright_green]\n"
    )

def print_status(message: str, level: str = "info"):
    ts = datetime.now().strftime("%H:%M:%S")
    styles = {
        "info":    ("bright_cyan",  "◆"),
        "success": ("bright_green", "✔"),
        "warning": ("yellow",       "⚠"),
        "error":   ("bright_red",   "✖"),
        "match":   ("bold magenta", "◉"),
    }
    color, icon = styles.get(level, styles["info"])
    console.print(f"  [bright_black][{ts}][/bright_black] [{color}]{icon} {message}[/{color}]")

def print_match(target_path: str, found_url: str, platform: str, confidence: float):
    confidence_pct = (1 - confidence) * 100
    color = "bright_green" if confidence_pct >= 95 else "yellow" if confidence_pct >= 85 else "white"
    alert  = " [bold red blink]⚡ HIGH-CONFIDENCE ALERT[/bold red blink]" if confidence_pct >= 98 else ""

    table = Table(box=box.ROUNDED, border_style="bright_blue", show_header=False, padding=(0, 2))
    table.add_column(style="bright_black", width=18)
    table.add_column(style="bright_white")
    table.add_row("TARGET",     target_path)
    table.add_row("FOUND",      found_url)
    table.add_row("PLATFORM",   platform.upper())
    table.add_row("ARCFACE",    f"[{color}]{confidence_pct:.1f}% confidence (dist={confidence:.3f})[/{color}]{alert}")

    console.print(Panel(
        table,
        title="[bold magenta]◉ MATCH CONFIRMED[/bold magenta]",
        border_style="magenta",
    ))
