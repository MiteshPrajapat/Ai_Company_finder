"""
Modern Dark Theme QSS stylesheet and aesthetic styling tokens for Job Finder AI.
Optimized for 1366x768, 1536x864, 1920x1080 and fluid dynamic resizing without clipping.
"""

DARK_THEME_QSS = """
/* Global Application Style */
QWidget {
    background-color: #0F172A;
    color: #F8FAFC;
    font-family: 'Segoe UI', 'Inter', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 12px;
    selection-background-color: #0284C7;
    selection-color: #FFFFFF;
}

/* Main Window & Dialogs */
QMainWindow, QDialog {
    background-color: #0B0F19;
}

QScrollArea {
    background-color: transparent;
    border: none;
}

/* Container Cards */
QFrame#cardFrame {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 8px;
}

QFrame#compactCard {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 8px;
}

/* Headers & Typography */
QLabel#headerTitle {
    font-size: 18px;
    font-weight: 800;
    color: #38BDF8;
    letter-spacing: 0.5px;
}

QLabel#headerSubtitle {
    font-size: 11px;
    color: #94A3B8;
    font-weight: 500;
}

QLabel#sectionTitle {
    font-size: 13px;
    font-weight: 700;
    color: #F1F5F9;
    letter-spacing: 0.3px;
}

QLabel#metricValue {
    font-size: 16px;
    font-weight: 700;
    color: #38BDF8;
}

QLabel#metricLabel {
    font-size: 10px;
    color: #94A3B8;
    text-transform: uppercase;
    font-weight: 600;
    letter-spacing: 0.5px;
}

/* Sidebar Navigation */
QListWidget#navSidebar {
    background-color: #0B0F19;
    border: none;
    border-right: 1px solid #1E293B;
    padding: 8px 6px;
}

QListWidget#navSidebar::item {
    padding: 10px 14px;
    border-radius: 6px;
    color: #94A3B8;
    font-weight: 600;
    font-size: 12px;
    margin-bottom: 4px;
}

QListWidget#navSidebar::item:hover {
    background-color: #1E293B;
    color: #F8FAFC;
}

QListWidget#navSidebar::item:selected {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284C7, stop:1 #0EA5E9);
    color: #FFFFFF;
}

/* Form Inputs */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #162032;
    color: #F8FAFC;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 12px;
    min-height: 28px;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #38BDF8;
    background-color: #1E293B;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left-width: 0px;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}

QComboBox QAbstractItemView {
    background-color: #1E293B;
    border: 1px solid #334155;
    selection-background-color: #0284C7;
    selection-color: #FFFFFF;
    border-radius: 6px;
    padding: 4px;
}

/* Checkboxes */
QCheckBox {
    color: #CBD5E1;
    font-weight: 500;
    font-size: 12px;
    spacing: 6px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #475569;
    background-color: #162032;
}

QCheckBox::indicator:hover {
    border-color: #38BDF8;
}

QCheckBox::indicator:checked {
    background-color: #0284C7;
    border-color: #38BDF8;
}

/* Buttons */
QPushButton {
    background-color: #334155;
    color: #F8FAFC;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
    font-size: 12px;
    min-height: 28px;
}

QPushButton:hover {
    background-color: #475569;
    border-color: #64748B;
}

QPushButton:pressed {
    background-color: #1E293B;
}

QPushButton:disabled {
    background-color: #1E293B;
    color: #64748B;
    border-color: #334155;
}

QPushButton#btnPrimary {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284C7, stop:1 #0EA5E9);
    border: 1px solid #38BDF8;
    color: #FFFFFF;
    font-size: 12px;
    font-weight: 700;
    padding: 6px 16px;
    border-radius: 6px;
    min-height: 30px;
}

QPushButton#btnPrimary:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369A1, stop:1 #0284C7);
}

QPushButton#btnDanger {
    background-color: #991B1B;
    border: 1px solid #DC2626;
    color: #FFFFFF;
    font-weight: 700;
    padding: 6px 14px;
    border-radius: 6px;
    min-height: 30px;
}

QPushButton#btnDanger:hover {
    background-color: #DC2626;
}

QPushButton#btnSuccess {
    background-color: #065F46;
    border: 1px solid #059669;
    color: #FFFFFF;
    font-weight: 700;
    padding: 6px 14px;
    border-radius: 6px;
    min-height: 30px;
}

QPushButton#btnSuccess:hover {
    background-color: #059669;
}

QPushButton#btnAction {
    background-color: #1E293B;
    color: #38BDF8;
    border: 1px solid #334155;
    font-weight: 600;
    font-size: 11px;
    padding: 3px 10px;
    border-radius: 4px;
    min-height: 22px;
}

QPushButton#btnAction:hover {
    background-color: #0284C7;
    color: #FFFFFF;
    border-color: #38BDF8;
}

/* Tables */
QTableWidget, QTableView {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 6px;
    gridline-color: #283548;
    color: #F8FAFC;
    alternate-background-color: #162032;
    font-size: 12px;
}

QTableWidget::item, QTableView::item {
    padding: 4px 8px;
    border-bottom: 1px solid #233044;
}

QTableWidget::item:selected, QTableView::item:selected {
    background-color: #1E3A5F;
    color: #38BDF8;
}

QHeaderView::section {
    background-color: #0B0F19;
    color: #94A3B8;
    padding: 6px 8px;
    border: none;
    border-bottom: 2px solid #334155;
    border-right: 1px solid #1E293B;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.4px;
}

/* Progress Bar */
QProgressBar {
    background-color: #162032;
    border: 1px solid #334155;
    border-radius: 4px;
    text-align: center;
    color: #FFFFFF;
    font-weight: 700;
    font-size: 11px;
    min-height: 16px;
    max-height: 16px;
}

QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284C7, stop:1 #38BDF8);
    border-radius: 3px;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #334155;
    border-radius: 6px;
    background-color: #1E293B;
    top: -1px;
}

QTabBar::tab {
    background-color: #0F172A;
    color: #94A3B8;
    padding: 7px 16px;
    margin-right: 3px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid #334155;
    border-bottom: none;
    font-size: 12px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background-color: #1E293B;
    color: #38BDF8;
}

/* Scrollbars */
QScrollBar:vertical {
    background-color: #0B0F19;
    width: 8px;
    border-radius: 4px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #334155;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background-color: #475569;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: #0B0F19;
    height: 8px;
    border-radius: 4px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background-color: #334155;
    min-width: 20px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #475569;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Status Bar */
QStatusBar {
    background-color: #0B0F19;
    color: #94A3B8;
    border-top: 1px solid #1E293B;
    font-size: 11px;
    padding: 3px 10px;
}
"""


def get_status_badge_style(status: str) -> str:
    """Returns clean CSS background/color for status badges."""
    status_upper = (status or "").upper().strip()

    colors = {
        "LIVE": ("#064E3B", "#34D399", "#059669"),          # Deep Green, Light Emerald
        "OFFLINE": ("#7F1D1D", "#FCA5A5", "#DC2626"),       # Deep Red, Soft Red
        "TIMEOUT": ("#78350F", "#FDE68A", "#D97706"),       # Amber
        "BLOCKED": ("#581C87", "#F0ABFC", "#9333EA"),       # Purple
        "COMPLETED": ("#064E3B", "#34D399", "#059669"),     # Emerald
        "ENRICHING": ("#0C4A6E", "#7DD3FC", "#0284C7"),     # Cyan Blue
        "SEARCHING": ("#0C4A6E", "#7DD3FC", "#0284C7"),     # Cyan Blue
        "PENDING": ("#1E293B", "#94A3B8", "#334155"),       # Muted Slate
        "STOPPED": ("#78350F", "#FDE68A", "#D97706"),       # Amber
        "FAILED": ("#7F1D1D", "#FCA5A5", "#DC2626"),        # Red
        "FOUND": ("#064E3B", "#34D399", "#059669"),         # Green
        "NOT_FOUND": ("#1E293B", "#94A3B8", "#334155"),     # Slate
        "READY": ("#064E3B", "#34D399", "#059669"),         # Green
        "IDLE": ("#1E293B", "#94A3B8", "#334155"),          # Slate
        "HR": ("#0C4A6E", "#38BDF8", "#0284C7"),            # Blue
        "CAREERS": ("#064E3B", "#34D399", "#059669"),       # Green
        "JOBS": ("#064E3B", "#34D399", "#059669"),          # Green
        "SALES": ("#581C87", "#F0ABFC", "#9333EA"),         # Purple
        "SUPPORT": ("#78350F", "#FDE68A", "#D97706"),       # Amber
        "GENERAL": ("#1E293B", "#CBD5E1", "#334155"),       # Slate
        "DRAFT": ("#1E293B", "#94A3B8", "#334155"),         # Muted Slate
        "READY_TO_SEND": ("#0C4A6E", "#38BDF8", "#0284C7"), # Sky Blue
        "BROWSER_OPENED": ("#581C87", "#F0ABFC", "#9333EA"),# Purple
        "SENT": ("#064E3B", "#34D399", "#059669"),           # Emerald Green
        "INTERVIEW": ("#065F46", "#6EE7B7", "#10B981"),      # Bright Mint
        "REJECTED": ("#7F1D1D", "#FCA5A5", "#DC2626"),       # Red
    }

    bg, fg, border = colors.get(status_upper, ("#1E293B", "#CBD5E1", "#334155"))
    return f"background-color: {bg}; color: {fg}; border: 1px solid {border}; font-weight: 600; font-size: 11px; padding: 2px 8px; border-radius: 4px; text-align: center;"


def get_relevance_badge_style(score: int) -> str:
    """Returns color styling based on relevance score 0-100."""
    if score >= 80:
        return "background-color: #064E3B; color: #34D399; border: 1px solid #059669; font-weight: 700; font-size: 11px; padding: 2px 8px; border-radius: 4px;"
    elif score >= 60:
        return "background-color: #0C4A6E; color: #38BDF8; border: 1px solid #0284C7; font-weight: 700; font-size: 11px; padding: 2px 8px; border-radius: 4px;"
    elif score >= 40:
        return "background-color: #78350F; color: #FDE68A; border: 1px solid #D97706; font-weight: 700; font-size: 11px; padding: 2px 8px; border-radius: 4px;"
    else:
        return "background-color: #7F1D1D; color: #FCA5A5; border: 1px solid #DC2626; font-weight: 700; font-size: 11px; padding: 2px 8px; border-radius: 4px;"


def get_source_badge_style(source: str) -> str:
    """Returns distinct colorful styling tokens for multi-source badges."""
    s = (source or "").lower().strip().replace(" ", "_")
    source_colors = {
        "career_portal": ("#064E3B", "#34D399", "#059669"),   # Emerald (Primary)
        "career": ("#064E3B", "#34D399", "#059669"),
        "indeed": ("#1E1B4B", "#818CF8", "#4338CA"),          # Indigo
        "unstop": ("#451A03", "#FBBF24", "#D97706"),          # Amber/Gold
        "linkedin": ("#082F49", "#38BDF8", "#0284C7"),        # Sky Blue
        "glassdoor": ("#042F2E", "#2DD4BF", "#0D9488"),       # Teal
    }
    bg, fg, border = source_colors.get(s, ("#1E293B", "#CBD5E1", "#334155"))
    return f"background-color: {bg}; color: {fg}; border: 1px solid {border}; font-weight: 700; font-size: 10px; padding: 2px 6px; border-radius: 4px; text-transform: uppercase;"

