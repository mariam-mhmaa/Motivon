from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QRadialGradient


class JoystickWidget(QWidget):
    joystickMoved = Signal(float, float)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(300, 300)
        self.knob_radius = 34
        self.base_radius = 105
        self.center = QPointF(150, 150)
        self.knob_pos = QPointF(150, 150)
        self.dragging = False

    def resizeEvent(self, event):
        self.center = QPointF(self.width() / 2, self.height() / 2)
        if not self.dragging:
            self.knob_pos = QPointF(self.center)
        super().resizeEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Transparent base
        p.setPen(Qt.NoPen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(self.rect())

        # Outer glow ring
        p.setPen(QPen(QColor(70, 170, 255, 70), 3))
        p.setBrush(QBrush(QColor(8, 19, 34, 220)))
        p.drawEllipse(self.center, self.base_radius + 8, self.base_radius + 8)

        # Main joystick base
        p.setPen(QPen(QColor(90, 190, 255, 90), 2))
        p.setBrush(QBrush(QColor(12, 28, 46, 230)))
        p.drawEllipse(self.center, self.base_radius, self.base_radius)

        # Inner circle
        p.setPen(QPen(QColor(60, 140, 210, 50), 1))
        p.setBrush(QBrush(QColor(15, 36, 58, 140)))
        p.drawEllipse(self.center, self.base_radius * 0.62, self.base_radius * 0.62)

        # Crosshair
        p.setPen(QPen(QColor(100, 190, 255, 55), 1))
        p.drawLine(
            int(self.center.x() - self.base_radius), int(self.center.y()),
            int(self.center.x() + self.base_radius), int(self.center.y())
        )
        p.drawLine(
            int(self.center.x()), int(self.center.y() - self.base_radius),
            int(self.center.x()), int(self.center.y() + self.base_radius)
        )

        # Knob gradient
        grad = QRadialGradient(self.knob_pos, self.knob_radius)
        grad.setColorAt(0.0, QColor(180, 235, 255, 245))
        grad.setColorAt(0.45, QColor(66, 170, 255, 240))
        grad.setColorAt(1.0, QColor(18, 88, 165, 245))

        p.setPen(QPen(QColor(180, 230, 255, 130), 2))
        p.setBrush(QBrush(grad))
        p.drawEllipse(self.knob_pos, self.knob_radius, self.knob_radius)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.update_knob(event.position())

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.update_knob(event.position())

    def mouseReleaseEvent(self, event):
        self.dragging = False
        self.knob_pos = QPointF(self.center)
        self.joystickMoved.emit(0.0, 0.0)
        self.update()

    def update_knob(self, pos):
        dx = pos.x() - self.center.x()
        dy = pos.y() - self.center.y()

        dist = (dx**2 + dy**2) ** 0.5
        if dist > self.base_radius:
            scale = self.base_radius / dist
            dx *= scale
            dy *= scale

        self.knob_pos = QPointF(self.center.x() + dx, self.center.y() + dy)
        self.joystickMoved.emit(dx / self.base_radius, -dy / self.base_radius)
        self.update()