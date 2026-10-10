from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame
)

from view.kinova3DWidget import Kinova3DWidget


class HomePage(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Home Page")

        # ==========================================
        # MAIN LAYOUT
        # ==========================================

        main_layout = QHBoxLayout(self)

        main_layout.setContentsMargins(50,50,50,50)
        main_layout.setSpacing(50)


        # ==========================================
        # LEFT SIDE
        # ==========================================

        left_widget = QWidget()

        left_layout = QVBoxLayout(
            left_widget
        )

        left_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        left_layout.setSpacing(
            15
        )


        # ==========================================
        # TEXT
        # ==========================================

        title = QLabel(
            "KINOVA GEN3"
        )

        subtitle = QLabel(
            "Kinova — Monitoring and visualization"
        )

        description = QLabel(
            "An application for visualizing the movement of the "
            "Kinova Gen3 robot arm and analyzing data collected "
            "from its six joints."
        )

        description.setWordWrap(
            True
        )


        # Optional styling

        title.setStyleSheet("""
            font-size: 36px;
            font-weight: 700;
        """)

        subtitle.setStyleSheet("""
            font-size: 18px;
            font-weight: 500;
        """)

        description.setStyleSheet("""
            font-size: 14px;
        """)


        # ==========================================
        # LEFT LAYOUT
        # ==========================================

        left_layout.addStretch()

        left_layout.addWidget(
            title
        )

        left_layout.addWidget(
            subtitle
        )

        left_layout.addWidget(
            description
        )

        left_layout.addStretch()


        # ==========================================
        # RIGHT SIDE - KINOVA 3D
        # ==========================================

        self.kinova_view = Kinova3DWidget()
        self.robot_frame = QFrame()
        self.robot_frame.setObjectName("homeRobotFrame")
        self.robot_frame.setStyleSheet("""
            QFrame#homeRobotFrame {
                background-color: white;
                border: 1px solid #dde3ec;
                border-radius: 16px;
            }
        """)
        robot_frame_layout = QVBoxLayout(self.robot_frame)
        robot_frame_layout.setContentsMargins(8, 8, 8, 8)
        robot_frame_layout.setSpacing(0)
        robot_frame_layout.addWidget(self.kinova_view)


        # ==========================================
        # MAIN
        # ==========================================

        main_layout.addWidget(
            left_widget,
            40
        )

        main_layout.addWidget(
            self.robot_frame,
            60
        )
