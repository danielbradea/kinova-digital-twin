import numpy as np
import pyvista as pv
from pathlib import Path

from PySide6.QtWidgets import QWidget, QVBoxLayout
from pyvistaqt import QtInteractor
from yourdfpy import URDF


URDF_PATH = str(Path(__file__).resolve().parents[1] / "resources/kortex_description/arms/gen3/6dof/urdf/GEN3-6DOF_NO-VISION_URDF_ARM_V01.urdf")


class Kinova3DWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        # =========================================================
        # LAYOUT
        # =========================================================

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        layout.setSpacing(0)

        # =========================================================
        # PYVISTA
        # =========================================================

        self.plotter = QtInteractor(self)

        layout.addWidget(
            self.plotter.interactor
        )

        # =========================================================
        # URDF
        # =========================================================

        self.robot = URDF.load(
            URDF_PATH,
            load_meshes=True
        )

        print("Kinova GEN3 loaded")

        # =========================================================
        # INITIAL POSITION
        # =========================================================

        self.robot.update_cfg({

            "joint_1": np.deg2rad(0),

            "joint_2": np.deg2rad(20),

            "joint_3": np.deg2rad(100),

            "joint_4": np.deg2rad(0),

            "joint_5": np.deg2rad(60),

            "joint_6": np.deg2rad(0),

        })

        # =========================================================
        # LOAD ROBOT
        # =========================================================

        self.load_robot()

        # =========================================================
        # CONFIGURE VIEWER
        # =========================================================

        self.setup_view()

    # =============================================================
    # LOAD ROBOT
    # =============================================================

    def load_robot(self):

        scene = self.robot.scene
        self.robot_actors = {}

        print(
            "Geometries:",
            len(scene.geometry)
        )

        for node_name in scene.graph.nodes_geometry:

            transform, geometry_name = (
                scene.graph[node_name]
            )

            geometry = scene.geometry[
                geometry_name
            ]

            # =====================================================
            # VERTICES
            # =====================================================

            vertices = np.asarray(
                geometry.vertices
            )

            # =====================================================
            # FACES
            # =====================================================

            faces = np.asarray(
                geometry.faces
            )

            # PyVista:
            #
            # 3, p1, p2, p3
            # 3, p1, p2, p3
            # ...

            pv_faces = np.hstack(

                [

                    np.full(
                        (
                            faces.shape[0],
                            1
                        ),
                        3
                    ),

                    faces

                ]

            ).astype(
                np.int64
            )

            # =====================================================
            # CREATE MESH
            # =====================================================

            mesh = pv.PolyData(
                vertices,
                pv_faces
            )

            # =====================================================
            # APPLY URDF TRANSFORM
            # =====================================================


            # =====================================================
            # ADD TO VIEWER
            # =====================================================

            actor = self.plotter.add_mesh(

                mesh,

                smooth_shading=True,

                # Satin white housing, matching the Gen3 arm.
                color="#f0f0ed",

                show_edges=False,

                split_sharp_edges=True,

                pbr=True,

                metallic=0.0,

                roughness=0.55

            )
            actor.user_matrix = transform
            self.robot_actors[node_name] = actor

    # =============================================================
    # VIEW SETTINGS
    # =============================================================

    def setup_view(self):

        # =========================================================
        # BACKGROUND
        # =========================================================

        self.plotter.set_background(
            "#f9fafc"
        )

        # =========================================================
        # ANTI ALIASING
        # =========================================================

        self.plotter.enable_anti_aliasing(
            "ssaa"
        )

        # =========================================================
        # BASE GRID
        # =========================================================

        self.add_base_grid(
            step_m=0.10
        )

        # =========================================================
        # CALCULATE ROBOT CENTER
        # =========================================================

        scene = self.robot.scene

        bounds = scene.bounds

        min_x, min_y, min_z = bounds[0]
        max_x, max_y, max_z = bounds[1]

        center_x = (
            min_x + max_x
        ) / 2

        center_y = (
            min_y + max_y
        ) / 2

        center_z = (
            min_z + max_z
        ) / 2

        # =========================================================
        # ROBOT SIZE
        # =========================================================

        size_x = (
            max_x - min_x
        )

        size_y = (
            max_y - min_y
        )

        size_z = (
            max_z - min_z
        )

        robot_size = max(
            size_x,
            size_y,
            size_z
        )

        # =========================================================
        # CAMERA DISTANCE
        # =========================================================

        distance = (
            robot_size * 1.8
        )

        # =========================================================
        # CAMERA
        # =========================================================

        self.plotter.camera_position = [

            (
                center_x + distance,
                center_y - distance,
                center_z + distance * 0.30
            ),

            (
                center_x,
                center_y,
                center_z
            ),

            (
                0,
                0,
                1
            )

        ]

        # =========================================================
        # CLIPPING
        # =========================================================

        self.plotter.reset_camera_clipping_range()

        # =========================================================
        # RENDER
        # =========================================================

        self.plotter.render()

    # =============================================================
    # BASE GRID
    # =============================================================

    def add_base_grid(
        self,
        step_m=0.10
    ):

        scene = self.robot.scene

        bounds = scene.bounds

        min_x, min_y, min_z = bounds[0]
        max_x, max_y, max_z = bounds[1]

        # =========================================================
        # DIMENSIONS
        # =========================================================

        size_x = (
            max_x - min_x
        )

        size_y = (
            max_y - min_y
        )

        # =========================================================
        # MARGIN
        # =========================================================

        margin = 0.25

        plane_x = max(
            0.80,
            size_x + margin * 2
        )

        plane_y = max(
            0.80,
            size_y + margin * 2
        )

        # =========================================================
        # CENTER
        # =========================================================

        center_x = (
            min_x + max_x
        ) / 2

        center_y = (
            min_y + max_y
        ) / 2

        # Slightly below the robot base

        center_z = (
            min_z - 0.002
        )

        # =========================================================
        # CELL COUNT
        # =========================================================

        i_res = max(
            1,
            int(
                round(
                    plane_x / step_m
                )
            )
        )

        j_res = max(
            1,
            int(
                round(
                    plane_y / step_m
                )
            )
        )

        # =========================================================
        # BACKGROUND PLANE
        # =========================================================

        plane_fill = pv.Plane(

            center=(
                center_x,
                center_y,
                center_z
            ),

            direction=(
                0,
                0,
                1
            ),

            i_size=plane_x,

            j_size=plane_y,

            i_resolution=i_res,

            j_resolution=j_res

        )

        # =========================================================
        # GRID PLANE
        # =========================================================

        plane_grid = pv.Plane(

            center=(
                center_x,
                center_y,
                center_z + 0.0005
            ),

            direction=(
                0,
                0,
                1
            ),

            i_size=plane_x,

            j_size=plane_y,

            i_resolution=i_res,

            j_resolution=j_res

        )

        # =========================================================
        # GRID BACKGROUND
        # =========================================================

        self.plotter.add_mesh(

            plane_fill,

            color="#202020",

            opacity=0.35,

            smooth_shading=False

        )

        # =========================================================
        # GRID LINES
        # =========================================================

        self.plotter.add_mesh(

            plane_grid,

            style="wireframe",

            color="#505050",

            line_width=1

        )

    # =============================================================
    # SET JOINTS
    # =============================================================

    def set_joints(
        self,
        joint_1=0,
        joint_2=20,
        joint_3=100,
        joint_4=0,
        joint_5=60,
        joint_6=0
    ):

        positions = np.asarray([joint_1, joint_2, joint_3, joint_4, joint_5, joint_6], dtype=float)
        if not np.isfinite(positions).all():
            raise ValueError("Joint positions must be finite")
        self.robot.update_cfg({

            "joint_1":
                np.deg2rad(
                    joint_1
                ),

            "joint_2":
                np.deg2rad(
                    joint_2
                ),

            "joint_3":
                np.deg2rad(
                    joint_3
                ),

            "joint_4":
                np.deg2rad(
                    joint_4
                ),

            "joint_5":
                np.deg2rad(
                    joint_5
                ),

            "joint_6":
                np.deg2rad(
                    joint_6
                )

        })

        for node_name, actor in self.robot_actors.items():
            transform, _ = self.robot.scene.graph[node_name]
            actor.user_matrix = transform
        self.plotter.reset_camera_clipping_range()
        self.plotter.render()

    def recenter_camera(self):
        self.plotter.reset_camera()
        self.plotter.reset_camera_clipping_range()
        self.plotter.render()
