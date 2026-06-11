import time
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import (
    QWidget, QGroupBox, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QPushButton, QCheckBox
)

class DraggableGroupBox(QGroupBox):
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.dragging = False
        self.drag_start_pos = QPoint(0, 0)
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
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class DraggableCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(850, 950)
        self._initialized_layout = False

    def update_canvas_size(self):
        max_x = 850
        max_y = 950
        for child in self.findChildren(QGroupBox):
            if child.isVisible():
                max_x = max(max_x, child.x() + child.width() + 40)
                max_y = max(max_y, child.y() + child.height() + 40)
        self.setMinimumSize(max_x, max_y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._initialized_layout:
            self.arrange_initially()
            self._initialized_layout = True

    def arrange_initially(self):
        # Stack group boxes neatly in a vertical card arrangement
        y = 20
        card_width = 810
        for child in self.findChildren(QGroupBox):
            if child.isVisible():
                child.resize(card_width, child.sizeHint().height())
                child.move(20, y)
                y += child.height() + 20
        self.update_canvas_size()
