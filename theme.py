"""Shared look and feel for the clinic app (colors, fonts, ttk styles, helpers).

Every screen gets its styling from here, so the whole app stays consistent.
Nothing at import time touches a real Tk window, which keeps the screens
importable (and testable) on machines without a display.
"""

from tkinter import ttk

# -- palette -------------------------------------------------------------------
APP_BG = "#F4F7FA"        # page background
WHITE = "#FFFFFF"
TEXT = "#1B2A3A"
MUTED = "#5F7080"
BORDER = "#D5DEE7"
ACCENT = "#0F7B83"        # clinic teal: primary actions, selection accents
ACCENT_HOVER = "#0C666D"
ACCENT_DARK = "#0A545A"
ACCENT_SOFT = "#DDF1F2"   # selected rows, selected day
SIDEBAR = "#14283B"
SIDEBAR_HOVER = "#1D3850"
SIDEBAR_ACTIVE = "#22435F"
SIDEBAR_TEXT = "#C5D3E0"
DANGER = "#B3362B"
DANGER_HOVER = "#942B22"

OPEN_BG, OPEN_FG = "#E0F2E8", "#1E6B45"       # open / available
BOOKED_BG, BOOKED_FG = "#FBE3E0", "#9B2C20"   # booked / unavailable
OFF_BG, OFF_FG = "#EDF1F5", "#6B7C8C"         # outside working hours
ZEBRA = "#F8FAFC"

FONT_CHOICES = (
    "Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter", "Noto Sans",
    "Ubuntu", "DejaVu Sans", "Arial",
)

_state = {"family": "TkDefaultFont"}


def font(size=10, weight="normal"):
    """A font tuple in the app's chosen family."""
    return (_state["family"], size, weight)


def _pick_family(root) -> str:
    import tkinter.font as tkfont

    available = set(tkfont.families(root))
    for name in FONT_CHOICES:
        if name in available:
            return name
    return tkfont.nametofont("TkDefaultFont").actual("family")


def configure_styles(root) -> None:
    """Apply the clinic theme to every ttk widget under ``root``."""
    import tkinter.font as tkfont

    family = _pick_family(root)
    _state["family"] = family
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(name).configure(family=family, size=10)

    root.configure(background=APP_BG)
    root.option_add("*TCombobox*Listbox.font", (family, 10))
    root.option_add("*TCombobox*Listbox.background", WHITE)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", WHITE)

    s = ttk.Style(root)
    s.theme_use("clam")

    s.configure(".", background=APP_BG, foreground=TEXT, font=(family, 10),
                bordercolor=BORDER, lightcolor=APP_BG, darkcolor=APP_BG,
                troughcolor="#E8EEF3")
    s.configure("TFrame", background=APP_BG)
    s.configure("TLabel", background=APP_BG, foreground=TEXT)
    s.configure("TCheckbutton", background=APP_BG, foreground=TEXT)
    s.map("TCheckbutton", background=[("active", APP_BG)])
    s.configure("TLabelframe", background=APP_BG, bordercolor=BORDER,
                lightcolor=BORDER, darkcolor=BORDER, relief="solid", borderwidth=1)
    s.configure("TLabelframe.Label", background=APP_BG, foreground=TEXT,
                font=(family, 10, "bold"))
    s.configure("TPanedwindow", background=APP_BG)

    # Buttons ----------------------------------------------------------------
    s.configure("TButton", padding=(14, 7), background=WHITE, foreground=TEXT,
                bordercolor=BORDER, lightcolor=WHITE, darkcolor=WHITE,
                focuscolor=WHITE, relief="flat", width=0)
    s.map("TButton",
          background=[("disabled", "#EEF1F4"), ("pressed", "#DCE6EE"), ("active", "#EAF1F6")],
          foreground=[("disabled", "#9AA8B5")],
          bordercolor=[("active", "#B8C7D4")])
    _solid_button(s, "Primary.TButton", ACCENT, ACCENT_HOVER, ACCENT_DARK, "#A9CFD2")
    _solid_button(s, "Danger.TButton", DANGER, DANGER_HOVER, "#7A221B", "#E3B1AC")
    s.configure("Clinic.Navigation.TButton", font=(family, 12), padding=(12, 8))

    s.configure("Sidebar.TButton", background=SIDEBAR, foreground=SIDEBAR_TEXT,
                bordercolor=SIDEBAR, lightcolor=SIDEBAR, darkcolor=SIDEBAR,
                focuscolor=SIDEBAR, borderwidth=0, anchor="w", padding=(18, 12),
                font=(family, 10))
    s.map("Sidebar.TButton", background=[("active", SIDEBAR_HOVER)],
          foreground=[("active", WHITE)], bordercolor=[("active", SIDEBAR_HOVER)])
    s.configure("SidebarActive.TButton", background=SIDEBAR_ACTIVE, foreground=WHITE,
                bordercolor=SIDEBAR_ACTIVE, lightcolor=SIDEBAR_ACTIVE,
                darkcolor=SIDEBAR_ACTIVE, focuscolor=SIDEBAR_ACTIVE, borderwidth=0,
                anchor="w", padding=(18, 12), font=(family, 10, "bold"))
    s.map("SidebarActive.TButton", background=[("active", SIDEBAR_ACTIVE)])

    s.configure("Day.TButton", padding=(6, 8), justify="center", background=WHITE)
    s.configure("DaySel.TButton", padding=(6, 8), justify="center",
                background=ACCENT_SOFT, bordercolor=ACCENT, lightcolor=ACCENT_SOFT,
                darkcolor=ACCENT_SOFT, foreground=ACCENT_DARK)
    s.map("DaySel.TButton", background=[("active", ACCENT_SOFT)])

    # Inputs -----------------------------------------------------------------
    s.configure("TEntry", fieldbackground=WHITE, foreground=TEXT, padding=(8, 6),
                bordercolor=BORDER, lightcolor=WHITE, darkcolor=WHITE)
    s.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
          fieldbackground=[("disabled", "#EEF1F4")], foreground=[("disabled", "#8795A3")])
    s.configure("TCombobox", fieldbackground=WHITE, background=WHITE, foreground=TEXT,
                padding=(8, 6), bordercolor=BORDER, lightcolor=WHITE, darkcolor=WHITE,
                arrowcolor=MUTED, arrowsize=14)
    s.map("TCombobox",
          fieldbackground=[("disabled", "#EEF1F4"), ("readonly", WHITE)],
          foreground=[("disabled", "#8795A3")],
          bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
          background=[("active", WHITE)])

    # Tables -----------------------------------------------------------------
    s.configure("Treeview", background=WHITE, fieldbackground=WHITE, foreground=TEXT,
                rowheight=30, borderwidth=1, bordercolor=BORDER,
                lightcolor=BORDER, darkcolor=BORDER)
    s.map("Treeview", background=[("selected", ACCENT_SOFT)],
          foreground=[("selected", TEXT)])
    s.configure("Treeview.Heading", background="#E8EEF3", foreground=TEXT,
                relief="flat", padding=(8, 8), font=(family, 10, "bold"),
                bordercolor="#E8EEF3", lightcolor="#E8EEF3", darkcolor="#E8EEF3")
    s.map("Treeview.Heading", background=[("active", "#DCE6EE")])
    for name in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        s.configure(name, background="#BCC9D5", troughcolor="#EEF2F6",
                    bordercolor="#EEF2F6", lightcolor="#BCC9D5", darkcolor="#BCC9D5",
                    arrowcolor=MUTED, relief="flat")
        s.map(name, background=[("active", "#9FB0BF")])

    # Tabs -------------------------------------------------------------------
    s.configure("TNotebook", background=APP_BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    s.configure("TNotebook.Tab", padding=(20, 10), background="#E3EAF0",
                foreground=MUTED, bordercolor=BORDER, lightcolor="#E3EAF0",
                darkcolor="#E3EAF0", font=(family, 10))
    s.map("TNotebook.Tab",
          background=[("selected", APP_BG), ("active", "#EAF0F5")],
          foreground=[("selected", ACCENT_DARK)],
          lightcolor=[("selected", APP_BG)], darkcolor=[("selected", APP_BG)],
          font=[("selected", (family, 10, "bold"))])

    # Text styles ------------------------------------------------------------
    s.configure("Clinic.Title.TLabel", font=(family, 26, "bold"))
    s.configure("Clinic.Subtitle.TLabel", font=(family, 12), foreground=MUTED)
    s.configure("Clinic.ScreenTitle.TLabel", font=(family, 20, "bold"))
    s.configure("Clinic.Field.TLabel", font=(family, 10, "bold"), foreground="#33475B")
    s.configure("Muted.TLabel", foreground=MUTED)
    s.configure("Status.TLabel", foreground=ACCENT_DARK, font=(family, 10))
    s.configure("Section.TLabel", font=(family, 12, "bold"))
    s.configure("Brand.TLabel", background=SIDEBAR, foreground=WHITE, font=(family, 15, "bold"))
    s.configure("BrandSub.TLabel", background=SIDEBAR, foreground="#8FA5B8", font=(family, 9))

    # Cards ------------------------------------------------------------------
    s.configure("Card.TFrame", background=WHITE, relief="solid", borderwidth=1,
                bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
    s.configure("Card.TLabel", background=WHITE, foreground=TEXT)
    s.configure("CardMuted.TLabel", background=WHITE, foreground=MUTED)
    s.configure("CardField.TLabel", background=WHITE, foreground="#33475B",
                font=(family, 10, "bold"))
    s.configure("CardTitle.TLabel", background=WHITE, foreground=TEXT, font=(family, 12, "bold"))
    s.configure("Stat.TLabel", background=WHITE, foreground=ACCENT_DARK, font=(family, 26, "bold"))
    s.configure("CardHover.TFrame", background="#F3FAFA", relief="solid", borderwidth=1,
                bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)
    s.configure("CardHover.TLabel", background="#F3FAFA", foreground=TEXT)
    s.configure("CardHoverTitle.TLabel", background="#F3FAFA", foreground=ACCENT_DARK,
                font=(family, 12, "bold"))
    s.configure("CardHoverMuted.TLabel", background="#F3FAFA", foreground=MUTED)

    # Banners ----------------------------------------------------------------
    for name, bg, fg in (
        ("BannerOpen.TLabel", OPEN_BG, OPEN_FG),
        ("BannerBooked.TLabel", BOOKED_BG, BOOKED_FG),
        ("BannerOff.TLabel", OFF_BG, "#44566A"),
    ):
        s.configure(name, background=bg, foreground=fg, padding=(14, 10),
                    font=(family, 10, "bold"))


def _solid_button(style, name, base, hover, pressed, disabled):
    style.configure(name, background=base, foreground=WHITE, bordercolor=base,
                    lightcolor=base, darkcolor=base, focuscolor=base,
                    padding=(16, 8), font=font(10, "bold"))
    style.map(name,
              background=[("disabled", disabled), ("pressed", pressed), ("active", hover)],
              foreground=[("disabled", WHITE)],
              bordercolor=[("disabled", disabled), ("active", hover)],
              lightcolor=[("active", hover)], darkcolor=[("active", hover)])


# -- helpers used by the screens -------------------------------------------------
def screen_header(parent, title: str, subtitle: str = ""):
    """Title (and optional one-line description) shown at the top of a screen."""
    frame = ttk.Frame(parent)
    ttk.Label(frame, text=title, style="Clinic.ScreenTitle.TLabel").pack(anchor="w")
    if subtitle:
        ttk.Label(frame, text=subtitle, style="Muted.TLabel").pack(anchor="w", pady=(2, 0))
    return frame


def style_tree(tree) -> None:
    """Row colors shared by every table: zebra rows and the booked/open tags."""
    tree.tag_configure("odd", background=ZEBRA)
    tree.tag_configure("open", background=OPEN_BG, foreground=OPEN_FG)
    tree.tag_configure("booked", background=BOOKED_BG, foreground=BOOKED_FG)
    tree.tag_configure("off", background=OFF_BG, foreground=OFF_FG)
    tree.tag_configure("muted", foreground=MUTED)


def make_table(parent, columns, height=8, selectmode="browse"):
    """A Treeview with a vertical scrollbar.

    ``columns`` is a sequence of ``(id, heading, width, anchor)``.
    Returns ``(frame, tree)``; grid or pack the frame.
    """
    frame = ttk.Frame(parent)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    tree = ttk.Treeview(
        frame, columns=[c[0] for c in columns], show="headings",
        height=height, selectmode=selectmode,
    )
    for column_id, heading, width, anchor in columns:
        tree.heading(column_id, text=heading, anchor=anchor)
        tree.column(column_id, width=width, minwidth=40, anchor=anchor)
    scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")
    style_tree(tree)
    return frame, tree


def style_text(widget) -> None:
    """Make a plain tk.Text match the ttk entries (border, font, padding)."""
    widget.configure(
        font="TkDefaultFont", relief="flat", borderwidth=0, highlightthickness=1,
        highlightbackground=BORDER, highlightcolor=ACCENT, background=WHITE,
        foreground=TEXT, insertbackground=TEXT, selectbackground=ACCENT_SOFT,
        selectforeground=TEXT, padx=10, pady=8,
    )
