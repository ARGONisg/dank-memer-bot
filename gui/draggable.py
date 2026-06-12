"""
Draggable UI Cards — Drag-reorderable group boxes with position persistence.

Provides two main classes for the GUI's card-based layout system:

  ``DraggableGroupBox``
      A QGroupBox that the user can drag by its title bar. It excludes
      interactive child widgets (line edits, combo boxes, spin boxes,
      push buttons, check boxes) from initiating the drag — clicking
      those works normally.

  ``DraggableCanvas``
      A QWidget that serves as the drag surface. It manages initial
      vertical stacking of child DraggableGroupBoxes and persists
      their layout to a JSON file so positions survive app restarts.

Position Persistence
====================
  On every mouse release (drop), ``DraggableCanvas.save_positions()``
  writes each visible card's (x, y, w, h) to a JSON file named after
  the canvas object name, e.g. ``data/settings_tab_positions.json``.

  On first ``showEvent``, the canvas tries ``_restore_positions()``.
  If a saved layout exists, it restores each card's position and size.
  Otherwise it runs ``arrange_initially()`` to stack cards vertically.

Usage
=====
  In a tab widget's ``__init__``:
      self.canvas = DraggableCanvas(self)
      self.setLayout(QVBoxLayout())
      self.layout().addWidget(self.canvas)

      # Then create cards:
      general_card = DraggableGroupBox("General Settings", parent=self.canvas)
      # ... populate with form controls ...
      general_card.positions_key = "general_settings"
"""

import os
import json
import time
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import (
    QWidget, QGroupBox, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QPushButton, QCheckBox
)

# Global override for the directory where position JSON files live.
# Defaults to data/ relative to project root.
_POSITIONS_DIR = None


def set_positions_dir(path: str):
    """Override the default directory for position JSON files."""
    global _POSITIONS_DIR
    _POSITIONS_DIR = path


class DraggableGroupBox(QGroupBox):
    """A QGroupBox that can be dragged by its title bar area.

    Interactive child widgets (QLineEdit, QComboBox, QSpinBox, etc.)
    are excluded from drag initiation so the user can interact with
    them normally.

    Attributes:
        positions_key (str): Unique key used for saving/restoring
            this card's position in the JSON file. Defaults to the
            title (lowercased, spaces → underscores).
    """

    def __init__(self, title, parent=None, positions_key=None):
        super().__init__(title, parent)
        self.dragging = False
        self.drag_start_pos = QPoint(0, 0)
        self.positions_key = positions_key or title.replace(" ", "_").lower()
        self.setCursor(Qt.SizeAllCursor)

    def mousePressEvent(self, event):
        """Start dragging on left click, but only if the click is NOT on
        an interactive child widget (line edits, buttons, etc.)."""
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            child = self.childAt(pos)
            if child and isinstance(child, (QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPushButton, QCheckBox)):
                super().mousePressEvent(event)
                return

            self.dragging = True
            if hasattr(event, "globalPosition"):
                self.drag_start_pos = event.globalPosition().toPoint() - self.pos()
            else:
                self.drag_start_pos = event.globalPos() - self.pos()

            event.accept()
            self.raise_()  # Bring this card to visual front
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Drag the card, clamped to the parent canvas boundaries."""
        if self.dragging and event.buttons() & Qt.LeftButton:
            if hasattr(event, "globalPosition"):
                current_global = event.globalPosition().toPoint()
            else:
                current_global = event.globalPos()

            new_pos = current_global - self.drag_start_pos

            if self.parentWidget():
                parent_w = self.parentWidget().width()
                parent_h = self.parentWidget().height()
                new_pos.setX(max(10, min(new_pos.x(), parent_w - self.width() - 10)))
                new_pos.setY(max(10, min(new_pos.y(), parent_h - self.height() - 10)))

            self.move(new_pos)

            if hasattr(self.parentWidget(), "update_canvas_size"):
                self.parentWidget().update_canvas_size()

            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """On drop, save positions to the parent canvas."""
        if self.dragging:
            self.dragging = False
            if hasattr(self.parentWidget(), "save_positions"):
                self.parentWidget().save_positions()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class DraggableCanvas(QWidget):
    """A surface widget that holds and manages DraggableGroupBox cards.

    Provides:
      - Auto-expanding canvas size based on card positions.
      - Initial vertical stacking via ``arrange_initially()``.
      - Automatic save/restore of card positions to a JSON file.

    Args:
        parent: Parent widget.
        positions_file: Optional explicit path to the positions JSON.
                        If not provided, derived from ``objectName()``
                        and ``_POSITIONS_DIR`` (default: data/).
    """

    def __init__(self, parent=None, positions_file=None):
        super().__init__(parent)
        self.setMinimumSize(850, 950)
        self._initialized_layout = False
        self._positions_file = positions_file

    def update_canvas_size(self):
        """Expand the canvas minimum size to accommodate all visible cards
        with a 40px margin."""
        max_x = 850
        max_y = 950
        for child in self.findChildren(QGroupBox):
            if child.isVisible():
                max_x = max(max_x, child.x() + child.width() + 40)
                max_y = max(max_y, child.y() + child.height() + 40)
        self.setMinimumSize(max_x, max_y)

    def showEvent(self, event):
        """On first show, restore saved positions or arrange cards vertically.

        Uses ``showEvent`` rather than ``resizeEvent`` so the initial layout
        fires reliably every time the tab is shown (e.g. tab switch).
        """
        super().showEvent(event)
        if not self._initialized_layout:
            if not self._restore_positions():
                self.arrange_initially()
            self._initialized_layout = True

    def resizeEvent(self, event):
        """Override only to preserve base behaviour; layout is done in showEvent."""
        super().resizeEvent(event)

    def arrange_initially(self):
        """Stack all visible DraggableGroupBox cards vertically with 20px gaps."""
        y = 20
        card_width = min(810, self.width() - 40)
        for child in self.findChildren(QGroupBox):
            if child.isVisible():
                child.resize(card_width, child.sizeHint().height())
                child.move(20, y)
                y += child.height() + 20
        self.update_canvas_size()

    def _positions_path(self):
        """Resolve the path to the positions JSON file."""
        if self._positions_file:
            return self._positions_file
        base = _POSITIONS_DIR or os.path.join(os.path.dirname(__file__), '..', 'data')
        name = self.objectName() or "canvas"
        return os.path.join(base, f"{name}_positions.json")

    def save_positions(self):
        """Save all visible card positions (x, y, w, h) to the JSON file.

        Called automatically on every mouse release (drop) event.
        """
        path = self._positions_path()
        positions = {}
        for child in self.findChildren(DraggableGroupBox):
            if child.isVisible():
                positions[child.positions_key] = {
                    'x': child.x(), 'y': child.y(),
                    'w': child.width(), 'h': child.height(),
                }
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(positions, f, indent=2)

    def _restore_positions(self) -> bool:
        """Restore all saved card positions from the JSON file.

        Returns True if positions were loaded and applied, False otherwise
        (file missing, unparseable, or empty).
        """
        path = self._positions_path()
        if not os.path.exists(path):
            return False
        try:
            with open(path) as f:
                positions = json.load(f)
        except (json.JSONDecodeError, OSError):
            return False
        if not positions:
            return False
        for child in self.findChildren(DraggableGroupBox):
            if not child.isVisible():
                continue
            saved = positions.get(child.positions_key)
            if saved:
                child.resize(saved['w'], saved['h'])
                child.move(saved['x'], saved['y'])
        self.update_canvas_size()
        return True
