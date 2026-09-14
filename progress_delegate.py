#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Custom Qt item delegate for rendering modern, smooth progress bars
inside QTableWidget cells without the overhead of QWidget instances.
"""

from qt.core import (
    QStyledItemDelegate,
    QPainter,
    QColor,
    QRect,
    Qt,
    QFont,
    QPen,
)


class ProgressBarDelegate(QStyledItemDelegate):
    """
    Renders a modern, sleek progress bar directly in a QTableWidget cell.
    Reads progress integer (0-100) from Qt.ItemDataRole.UserRole.
    Reads status string from Qt.ItemDataRole.UserRole + 1 (or displays percentage).
    """

    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        data = index.data(Qt.ItemDataRole.UserRole)
        status = index.data(Qt.ItemDataRole.UserRole + 1)
        
        # Fallback to parsing text if UserRole not set
        if data is None:
            text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
            if "%" in text:
                try:
                    pct_str = text.split("%")[0].split()[-1].replace("[", "").replace("]", "")
                    percent = max(0, min(100, int(pct_str)))
                except Exception:
                    percent = 0
            else:
                percent = 0
        else:
            try:
                percent = max(0, min(100, int(data)))
            except (ValueError, TypeError):
                percent = 0

        status_str = str(status or "").strip().lower()

        # Detect dark mode from palette background lightness
        is_dark = option.palette.window().color().lightness() < 128

        # Track background color
        track_color = QColor("#22272e") if is_dark else QColor("#e5e7eb")
        border_color = QColor("#374151") if is_dark else QColor("#d1d5db")

        # Accent color depending on status
        if "fail" in status_str or "err" in status_str or "skip" in status_str:
            fill_color = QColor("#dc2626")  # Red
            label_text = "Failed"
        elif "downloaded" in status_str or "added" in status_str or percent >= 100:
            fill_color = QColor("#16a34a")  # Green
            label_text = "✓ Done"
        elif percent > 0:
            fill_color = QColor("#2563eb")  # Blue
            label_text = f"{percent}%"
        else:
            fill_color = QColor("#475569")  # Muted slate
            label_text = "Queued"

        # Calculate bounding box with padding
        rect = option.rect
        pad_x = 8
        pad_y = 6
        bar_rect = QRect(
            rect.x() + pad_x,
            rect.y() + pad_y,
            max(0, rect.width() - (pad_x * 2)),
            max(0, rect.height() - (pad_y * 2)),
        )

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Draw track background
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(track_color)
        radius = 4.0
        painter.drawRoundedRect(bar_rect, radius, radius)

        # Draw filled progress
        if percent > 0 and bar_rect.width() > 0:
            fill_w = int(bar_rect.width() * (percent / 100.0))
            if fill_w > 0:
                fill_rect = QRect(bar_rect.x(), bar_rect.y(), fill_w, bar_rect.height())
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(fill_color)
                painter.drawRoundedRect(fill_rect, radius, radius)

        # Draw centered text label
        font = QFont(option.font)
        font.setPointSize(max(8, font.pointSize() - 1))
        font.setBold(True)
        painter.setFont(font)

        text_color = QColor("#ffffff") if (is_dark or percent > 30) else QColor("#1f2937")
        painter.setPen(text_color)
        painter.drawText(bar_rect, Qt.AlignmentFlag.AlignCenter, label_text)

        painter.restore()

