"""Shared widget builders for the recorder components."""

from PySide6.QtWidgets import QFrame, QLabel, QLineEdit, QSizePolicy, QVBoxLayout


def connection_status(status="disconnected"):
    label = QLabel()
    update_connection_status(label, status)
    return label


def update_connection_status(label, status):
    """Update the existing label already displayed in the connection card."""

    statuses = {
        "disconnected": {
            "text": "● Disconnected",
            "color": "#bd4652"
        },

        "connecting": {
            "text": "● Connecting...",
            "color": "#d9a441"
        },

        "connected": {
            "text": "● Connected",
            "color": "#4caf78"
        },

        "failed": {
            "text": "● Connection failed",
            "color": "#bd4652"
        }
    }

    current = statuses.get(
        status,
        statuses["disconnected"]
    )

    label.setText(current["text"])

    label.setStyleSheet(
        f"""
        color: {current["color"]};
        font-weight: 600;
        font-size: 12px;
        """
    )



def input_field(placeholder, password=False, default_value=""):
    field = QLineEdit()
    field.setPlaceholderText(placeholder)
    field.setText(default_value)
    field.setMinimumHeight(38)
    field.setMinimumWidth(0)
    if password:
        field.setEchoMode(QLineEdit.EchoMode.Password)
    return field

def card(title_text, status):
    card = QFrame()
    card.setProperty("role", "card")
    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(12)
    title = QLabel(title_text)
    title.setProperty("role", "cardTitle")
    layout.addWidget(title)
    layout.addWidget(status)
    layout.addSpacing(4)
    return card, layout

def add_field(layout, label_text, input_widget, bottom_space=0):
    field = QVBoxLayout()
    field.setSpacing(6)
    field.addWidget(QLabel(label_text))
    field.addWidget(input_widget)
    layout.addLayout(field)
    if bottom_space:
        layout.addSpacing(bottom_space)

