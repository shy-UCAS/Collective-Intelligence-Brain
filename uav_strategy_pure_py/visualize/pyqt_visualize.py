"""Optimized PyQt replay visualizer for the pure Python agents02 export.

The original visualizer redrew every trajectory and all facilities from
scratch on every frame.  This copy keeps the static map as a background layer
and uses persistent Matplotlib artists for the moving UAVs.  It also drops the
large per-frame ``logs`` and ``cur_siblings_ids`` fields from the in-memory
data so replay memory usage stays low.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from uav_strategy_pure_py.planning_modules import basic_functions as bfunc


_DEFAULT_FACILITIES_FILE = "data/facilities_shaoxing.json"


def _format_epoch_ms(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000.0).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    except (TypeError, ValueError, OSError, OverflowError):
        return str(ms)


class UAVVisualizer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("UAV Trajectory Visualization")
        self.setGeometry(100, 100, 1200, 800)

        self._lnglat2utm_convertor = bfunc.LngLat2UTM()

        self.data = {}
        self.uav_ids = []
        self.current_step = 0
        self.max_steps = 0
        self.is_playing = False
        self.is_utm = False
        self.facilities = None

        self.simulation_meta = {}
        self.mission_meta = {}
        self.planned_routes = {}
        self.swarm_by_member = {}

        self._dynamic_ready = False
        self._dynamic_artists = {}

        self.timer = QTimer()
        self.timer.timeout.connect(self.next_step)

        self.init_ui()
        self._load_default_map()

    def _load_default_map(self):
        try:
            with open(_DEFAULT_FACILITIES_FILE, "r", encoding="utf-8") as f:
                map_data = json.load(f)
            self.load_map_data(map_data)
            print(f"Loaded default map: {_DEFAULT_FACILITIES_FILE}")
        except FileNotFoundError:
            print(f"Default map file not found: {_DEFAULT_FACILITIES_FILE}")
        except Exception as exc:
            print(f"Failed to load default map: {exc}")

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)

        left_layout = QVBoxLayout()
        left_splitter = QSplitter(Qt.Vertical)

        upper_left_widget = QWidget()
        upper_left_layout = QVBoxLayout(upper_left_widget)
        upper_left_layout.setContentsMargins(0, 0, 0, 0)

        top_bar = QHBoxLayout()
        self.btn_load = QPushButton("上传可视化文件")
        self.btn_load.clicked.connect(self.open_file)
        self.btn_map = QPushButton("切换地图数据文件")
        self.btn_map.clicked.connect(self.open_map_file)
        self.cb_utm = QCheckBox("UTM 坐标")
        self.cb_utm.stateChanged.connect(lambda _: self.toggle_coord_system())
        top_bar.addWidget(self.btn_load)
        top_bar.addWidget(self.btn_map)
        top_bar.addWidget(self.cb_utm)
        top_bar.addStretch()
        upper_left_layout.addLayout(top_bar)

        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        upper_left_layout.addWidget(self.toolbar)

        self.ax = self.figure.add_subplot(111)
        self.ax.set_title("UAV Trajectory Visualization")
        self.ax.set_xlabel("Longitude")
        self.ax.set_ylabel("Latitude")
        self.ax.grid(True)
        upper_left_layout.addWidget(self.canvas, stretch=1)

        controls = QHBoxLayout()
        self.btn_prev = QPushButton("后退")
        self.btn_play = QPushButton("播放")
        self.btn_next = QPushButton("前进")
        self.btn_prev.clicked.connect(self.prev_step)
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_next.clicked.connect(self.next_step)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(self.slider_moved)
        self.step_label = QLabel("Step: 0/0")

        controls.addWidget(self.btn_prev)
        controls.addWidget(self.btn_play)
        controls.addWidget(self.btn_next)
        controls.addWidget(self.slider)
        controls.addWidget(self.step_label)
        upper_left_layout.addLayout(controls)

        lower_left_widget = QWidget()
        self.log_panel = QVBoxLayout(lower_left_widget)
        self.log_panel.setContentsMargins(0, 0, 0, 0)
        self.log_label = QLabel("当前帧日志输出 (Log)")
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setPlaceholderText("等待加载数据...")
        self.log_panel.addWidget(self.log_label)
        self.log_panel.addWidget(self.log_display)

        left_splitter.addWidget(upper_left_widget)
        left_splitter.addWidget(lower_left_widget)
        left_splitter.setSizes([650, 150])
        left_layout.addWidget(left_splitter)
        layout.addLayout(left_layout, stretch=4)

        self.info_panel = QVBoxLayout()
        self.info_label = QLabel("无人机状态与任务语义信息")
        self.info_display = QTextEdit()
        self.info_display.setReadOnly(True)
        self.info_display.setPlaceholderText("等待数据加载...")
        self.info_panel.addWidget(self.info_label)
        self.info_panel.addWidget(self.info_display)
        layout.addLayout(self.info_panel, stretch=1)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择轨迹数据", "", "JSON Files (*.json)"
        )
        if file_path:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            self.load_data(raw_data)
            self.update_info_display()

    def open_map_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择地图数据", "", "JSON Files (*.json)"
        )
        if file_path:
            with open(file_path, "r", encoding="utf-8") as f:
                self.load_map_data(json.load(f))

    def load_map_data(self, json_data):
        if "facilities_str" not in json_data or "defence_rings" not in json_data:
            print("错误：地图数据格式不匹配")
            return
        self.facilities = bfunc.Facilities(
            json_data["facilities_str"],
            json_data["defence_rings"],
            convert_to_utm=False,
        )
        self._dynamic_ready = False
        self.init_draw_map()

    def load_data(self, json_data):
        if "uavs_coords_raw" not in json_data:
            print("错误：数据格式不匹配")
            return

        self.data = json_data["uavs_coords_raw"]
        self.uav_ids = list(self.data.keys())
        self.simulation_meta = json_data.get("simulationMeta") or {}
        self.mission_meta = json_data.get("missionMeta") or {}
        self.planned_routes = json_data.get("plannedRoutes") or {}

        self.swarm_by_member = {}
        for swarm in self.mission_meta.get("swarms") or []:
            if not isinstance(swarm, dict):
                continue
            for member in swarm.get("memberIds") or []:
                self.swarm_by_member[str(member)] = swarm

        # Drop the largest per-frame fields.  The replay view does not need the
        # complete AgentSpeak logs or the repeated sibling-id list.
        for uid, info in self.data.items():
            for extra in info.get("extras") or []:
                extra.pop("logs", None)
                extra.pop("cur_siblings_ids", None)

        self.max_steps = 0
        for uid in self.uav_ids:
            self.max_steps = max(self.max_steps, len(self.data[uid]["lats"]))

        self.current_step = 0
        self._force_autoscale = True
        self._dynamic_ready = False
        self.slider.blockSignals(True)
        self.slider.setRange(0, self.max_steps - 1)
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self.update_ui_state()
        self.draw_plot()

    # ------------------------------------------------------------------
    # Playback controls
    # ------------------------------------------------------------------
    def toggle_play(self):
        if not self.data:
            return
        self.is_playing = not self.is_playing
        if self.is_playing:
            self.btn_play.setText("暂停")
            self.timer.start(200)
        else:
            self.btn_play.setText("播放")
            self.timer.stop()

    def next_step(self):
        if self.current_step < self.max_steps - 1:
            self.current_step += 1
            self.slider.setValue(self.current_step)
        else:
            self.is_playing = False
            self.timer.stop()
            self.btn_play.setText("播放")

    def prev_step(self):
        if self.current_step > 0:
            self.current_step -= 1
            self.slider.setValue(self.current_step)

    def slider_moved(self, value):
        self.current_step = value
        self.update_ui_state()
        self.draw_plot()
        # Throttle the expensive text panel during scrubbing.
        if value % 5 == 0:
            self.update_info_display()

    def update_ui_state(self):
        self.step_label.setText(f"Step: {self.current_step}/{self.max_steps - 1}")

    def toggle_coord_system(self):
        self.is_utm = self.cb_utm.isChecked()
        self._force_autoscale = True
        self._dynamic_ready = False
        self.init_draw_map()
        self.draw_plot()
        self.update_info_display()

    # ------------------------------------------------------------------
    # Static map background
    # ------------------------------------------------------------------
    def init_draw_map(self):
        self.ax.clear()
        self.ax.set_title("UAV Trajectory Visualization")
        if self.is_utm:
            self.ax.set_xlabel("UTM X")
            self.ax.set_ylabel("UTM Y")
        else:
            self.ax.set_xlabel("Longitude")
            self.ax.set_ylabel("Latitude")

        if self.facilities:
            for fac, lnglat_xy in self.facilities.antiairs.items():
                x, y = self._point_xy(lnglat_xy)
                self.ax.plot(x, y, "ro", label=f"{fac} Antiair")
            for fac, lnglat_xy in self.facilities.headquartors.items():
                x, y = self._point_xy(lnglat_xy)
                self.ax.plot(x, y, "go", label=f"{fac} Headquarters")
            for fac, lnglat_xy in self.facilities.probers.items():
                x, y = self._point_xy(lnglat_xy)
                self.ax.plot(x, y, "bo", label=f"{fac} Prober")
            for fac, lnglat_xy in self.facilities.facilities_info.items():
                if fac in self.facilities.antiairs or fac in self.facilities.headquartors or fac in self.facilities.probers:
                    continue
                x, y = self._point_xy(lnglat_xy)
                self.ax.plot(x, y, "ko", markersize=6, label=f"{fac} Facility")
            for fac, lnglat_xy in self.facilities.defend_rings.items():
                if self.is_utm:
                    utm_xy = self._lnglat2utm_convertor.lng_lat_to_utm_array(lnglat_xy)
                    self.ax.fill(utm_xy[:, 0], utm_xy[:, 1], alpha=0.2, label=f"{fac} Defence Ring")
                else:
                    self.ax.fill(lnglat_xy[:, 0], lnglat_xy[:, 1], alpha=0.2, label=f"{fac} Defence Ring")

        if not self.data:
            self.ax.autoscale(True)
        self.ax.legend(loc="upper right", fontsize="small")
        self.ax.grid(True, linestyle="--", alpha=0.5)
        self._dynamic_ready = False
        self.canvas.draw()

    def _point_xy(self, lnglat_xy):
        if self.is_utm:
            return self._lnglat2utm_convertor.lon_lat_to_utm(lnglat_xy[0], lnglat_xy[1])
        return lnglat_xy

    # ------------------------------------------------------------------
    # Incremental trajectory rendering
    # ------------------------------------------------------------------
    def _build_dynamic_artists(self):
        self._dynamic_artists = {}
        for uid in self.uav_ids:
            line, = self.ax.plot([], [], alpha=0.6, label=f"Path {uid}")
            point = self.ax.scatter([], [], marker="^", s=100)
            text = self.ax.text(0, 0, "", fontsize=9)
            lookahead_point = self.ax.scatter([], [], marker="x", s=50)
            lookahead_line, = self.ax.plot([], [], linestyle=":", alpha=0.5)
            self._dynamic_artists[uid] = {
                "line": line,
                "point": point,
                "text": text,
                "lookahead_point": lookahead_point,
                "lookahead_line": lookahead_line,
            }
        self._dynamic_ready = True

    def draw_plot(self):
        if not self.data:
            return
        if not self._dynamic_ready:
            self._build_dynamic_artists()

        for uid in self.uav_ids:
            uav_info = self.data[uid]
            lats = uav_info["lats"]
            lngs = uav_info["lngs"]
            idx = min(self.current_step, len(lats) - 1)
            artists = self._dynamic_artists[uid]

            if self.is_utm:
                coords = self._lnglat2utm_convertor.lng_lat_to_utm_array(
                    np.array([lngs[: idx + 1], lats[: idx + 1]]).T
                )
                xs, ys = coords[:, 0], coords[:, 1]
                cur_x, cur_y = xs[-1], ys[-1]
            else:
                xs, ys = lngs[: idx + 1], lats[: idx + 1]
                cur_x, cur_y = lngs[idx], lats[idx]

            artists["line"].set_data(xs, ys)
            artists["point"].set_offsets([[cur_x, cur_y]])
            artists["text"].set_position((cur_x, cur_y))
            artists["text"].set_text(uid)

            extra = uav_info["extras"][idx] if idx < len(uav_info.get("extras", [])) else {}
            lookahead_coord = extra.get("lookahead_coord")
            if lookahead_coord and len(lookahead_coord) >= 2:
                if self.is_utm:
                    lh_x, lh_y = lookahead_coord[0], lookahead_coord[1]
                else:
                    lh_x, lh_y = self._lnglat2utm_convertor.utm_to_lng_lat(
                        lookahead_coord[0], lookahead_coord[1]
                    )
                artists["lookahead_point"].set_offsets([[lh_x, lh_y]])
                artists["lookahead_line"].set_data([cur_x, lh_x], [cur_y, lh_y])
            else:
                artists["lookahead_point"].set_offsets(np.empty((0, 2)))
                artists["lookahead_line"].set_data([], [])

        if getattr(self, "_force_autoscale", False):
            self.ax.autoscale(True)
            self._force_autoscale = False

        self.canvas.draw_idle()

    # ------------------------------------------------------------------
    # Text panels
    # ------------------------------------------------------------------
    def update_info_display(self):
        if not self.data:
            return

        info_text = f"--- Step {self.current_step} 实时状态 ---\n\n"

        if self.simulation_meta:
            info_text += "== 仿真元信息 (simulationMeta) ==\n"
            start_ms = self.simulation_meta.get("startTimeMs")
            info_text += f"仿真起点: {_format_epoch_ms(start_ms) if start_ms is not None else 'N/A'}\n"
            info_text += (
                f"时间基准: {self.simulation_meta.get('timeBasis', 'N/A')} "
                f"dt={self.simulation_meta.get('dtMs', 'N/A')}ms\n"
            )
            kinematics = self.simulation_meta.get("kinematics") or {}
            if kinematics:
                info_text += (
                    f"运动学上限: 水平{kinematics.get('maxHorizontalSpeedMps', 'N/A')}m/s "
                    f"爬升{kinematics.get('maxClimbRateMps', 'N/A')}m/s "
                    f"下降{kinematics.get('maxDescentRateMps', 'N/A')}m/s\n"
                )

        swarms = self.mission_meta.get("swarms") or []
        if swarms:
            info_text += "\n== 集群任务语义 (missionMeta) ==\n"
            for swarm in swarms:
                if not isinstance(swarm, dict):
                    continue
                members = swarm.get("memberIds") or []
                info_text += (
                    f"[{swarm.get('swarmId', '?')}] 任务类型={swarm.get('orderType', 'N/A')} "
                    f"目标={swarm.get('target', 'N/A')} 航段={swarm.get('segmentKey', 'N/A')} "
                    f"编队={swarm.get('fleetNo', 'N/A')} 领队={swarm.get('leaderId', 'N/A')}\n"
                )
                info_text += f"  成员({len(members)}): {', '.join(str(m) for m in members)}\n"
        else:
            info_text += "== 集群任务语义 (missionMeta) ==\n导出未包含 missionMeta\n"

        info_text += "\n" + "-" * 40 + "\n\n"

        for uid in self.uav_ids:
            uav_info = self.data[uid]
            if self.current_step >= len(uav_info.get("extras", [])):
                continue
            extra = uav_info["extras"][self.current_step]
            info_text += f"【无人机: {uid}】\n"

            swarm = self.swarm_by_member.get(uid)
            if swarm:
                info_text += (
                    f"所属集群: {swarm.get('swarmId', '?')} "
                    f"(任务={swarm.get('orderType', 'N/A')}, 目标={swarm.get('target', 'N/A')})\n"
                )

            if self.is_utm:
                cur_x, cur_y = self._lnglat2utm_convertor.lon_lat_to_utm(
                    uav_info["lngs"][self.current_step],
                    uav_info["lats"][self.current_step],
                )
                info_text += f"位置 (UTM): ({cur_x:.2f}, {cur_y:.2f})\n"
            else:
                info_text += (
                    f"位置: ({uav_info['lngs'][self.current_step]:.6f}, "
                    f"{uav_info['lats'][self.current_step]:.6f})\n"
                )

            if "alts" in uav_info and self.current_step < len(uav_info["alts"]):
                alt = uav_info["alts"][self.current_step]
                if alt is not None:
                    info_text += f"高度: {alt:.2f} m\n"

            sim_time_ms = extra.get("simTimeMs")
            if sim_time_ms is not None:
                info_text += f"仿真时间: {_format_epoch_ms(sim_time_ms)} (round={extra.get('round_id', 'N/A')})\n"

            plan = self.planned_routes.get(uid) or {}
            if plan:
                segments = [seg.get("segmentKey") for seg in plan.get("flightPlan") or []]
                info_text += (
                    f"计划航迹: {plan.get('segmentCount', '?')}段"
                    f"{plan.get('routePointCount', '?')}点 "
                    f"complete={plan.get('complete', '?')} segments={segments or 'N/A'}\n"
                )

            info_text += f"编队类型: {extra.get('formation_type', 'N/A')}\n"
            info_text += f"航段Key: {extra.get('segment_key', 'N/A')}\n"
            info_text += f"等待状态: {extra.get('is_waiting', 'N/A')}\n"
            info_text += f"领队ID: {extra.get('leader_id', 'N/A')}\n"
            info_text += f"等待原因: {extra.get('waiting_reason', extra.get('wait_message', 'N/A'))}\n"
            info_text += f"frame_id/lookahead: {extra.get('frame_id', 'N/A')}/{extra.get('lookahead', 'N/A')}\n"
            info_text += f"距离目标: {extra.get('dist_to_target', 'N/A')}\n"
            info_text += f"飞行阶段: {extra.get('flight_phase', 'N/A')}\n"
            info_text += f"global_id: {extra.get('global_id', 'N/A')}\n"
            info_text += "-" * 25 + "\n"

        self.info_display.setText(info_text)
        self.log_display.setText(f"Step {self.current_step} 没有输出日志。")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = UAVVisualizer()
    window.show()
    sys.exit(app.exec_())
