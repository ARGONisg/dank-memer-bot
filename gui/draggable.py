import os
import json
import time
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import (
    QWidget, QGroupBox, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QPushButton, QCheckBox
)

_POSITIONS_DIR = None

def set_positions_dir(path: str):
    global _POSITIONS_DIR
    _POSITIONS_DIR = path

class DraggableGroupBox(QGroupBox):
    def __init__(self, title, parent=None, positions_key=None):
        super().__init__(title, parent)
        self.dragging = False
        self.drag_start_pos = QPoint(0, 0)
        self.positions_key = positions_key or title.replace(" ", "_").lower()
        self.setCursor(Qt.SizeAllCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Avoid hijacking drag if clicking directly on interactive controls
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
            # Bring this card to front
            self.raise_()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.LeftButton:
            if hasattr(event, "globalPosition"):
                current_global = event.globalPosition().toPoint()
            else:
                current_global = event.globalPos()
                
            new_pos = current_global - self.drag_start_pos
            
            # Clamp to parent boundaries to prevent dragging completely out of view
            if self.parentWidget():
                parent_w = self.parentWidget().width()
                parent_h = self.parentWidget().height()
                new_pos.setX(max(10, min(new_pos.x(), parent_w - self.width() - 10)))
                new_pos.setY(max(10, min(new_pos.y(), parent_h - self.height() - 10)))
                
            self.move(new_pos)
            
            # Notify canvas to update its scroll dimensions
            if hasattr(self.parentWidget(), "update_canvas_size"):
                self.parentWidget().update_canvas_size()
                
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.dragging:
            self.dragging = False
            # Save position on drop
            if hasattr(self.parentWidget(), "save_positions"):
                self.parentWidget().save_positions()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class DraggableCanvas(QWidget):
    def __init__(self, parent=None, positions_file=None):
        super().__init__(parent)
        self.setMinimumSize(850, 950)
        self._initialized_layout = False
        self._positions_file = positions_file

    def update_canvas_size(self):
        max_x = 850
        max_y = 950
        for child in self.findChildren(QGroupBox):
            if child.isVisible():
                max_x = max(max_x, child.x() + child.width() + 40)
                max_y = max(max_y, child.y() + child.height() + 40)
        self.setMinimumSize(max_x, max_y)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initialized_layout:
            if not self._restore_positions():
                self.arrange_initially()
            self._initialized_layout = True

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def arrange_initially(self):
        y = 20
        card_width = min(810, self.width() - 40)
        for child in self.findChildren(QGroupBox):
            if child.isVisible():
                child.resize(card_width, child.sizeHint().height())
                child.move(20, y)
                y += child.height() + 20
        self.update_canvas_size()

    def _positions_path(self):
        if self._positions_file:
            return self._positions_file
        base = _POSITIONS_DIR or os.path.join(os.path.dirname(__file__), '..', 'data')
        name = self.objectName() or "canvas"
        return os.path.join(base, f"{name}_positions.json")

    def save_positions(self):
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
