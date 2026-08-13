"""Pure Python planning library, adapted from the original ``PlanningLib``.

The original module imported ``agentspeak`` only for registering ASL actions.
This copy keeps the pure planning methods and drops the AgentSpeak/BDI layer.
The pure geometry modules from the original package are reused read-only.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import numpy as np
import random


from uav_strategy_pure_py.planning_modules import basic_functions as bfunc
from uav_strategy_pure_py.planning_modules import quick_path_planners as qpp
from uav_strategy_pure_py.planning_modules import math_curves_generators as curve_gen


class PlanningLib:
    """Trajectory planning and height-interpolation helpers."""

    def __init__(self, self_agent: Any) -> None:
        self.self_agent = self_agent
        self.VERBOSE = False

    @property
    def agent(self) -> Any:
        return self.self_agent

    def log(self, msg: str) -> None:
        if self.VERBOSE:
            print(msg)

    def _is_coordinate_target(self, target: Any) -> bool:
        if not isinstance(target, (list, tuple)):
            return False
        if len(target) < 2:
            return False
        try:
            return all(isinstance(v, (int, float)) and np.isfinite(v) for v in target[:2])
        except TypeError:
            return False

    def _coordinate_to_utm(self, target: Any) -> List[float]:
        lng, lat = float(target[0]), float(target[1])
        if not (-180.0 <= lng <= 180.0 and -90.0 <= lat <= 90.0):
            raise ValueError("coordinate target out of range: {}".format(target))
        x, y = self.agent.facilities.lnglat_converter.lon_lat_to_utm(lng, lat)
        return [x, y]

    def insert_height_val(
        self,
        order_type: str,
        traj: List[List[float]],
        start_height: int,
        end_height: int,
    ) -> List[List[float]]:
        default_range = self.agent.height_range_set[order_type]
        alt_start_rand = random.randint(default_range[0][0], default_range[0][1])
        alt_end_rand = random.randint(default_range[1][0], default_range[1][1])

        if len(traj[0]) == 2:
            traj[0].append(start_height if start_height != -1 else alt_start_rand)
        if len(traj[-1]) == 2:
            traj[-1].append(end_height if end_height != -1 else alt_end_rand)

        traj_3d = curve_gen.interpolate_z_coordinates(traj)
        if order_type == "detour":
            return curve_gen.linear_densify_3d(traj_3d)
        if order_type in ("orbit", "loiter"):
            return curve_gen.cubic_interpolation_3d(traj_3d)
        return curve_gen.generate_breakthrough_flight(traj_3d)

    def plan_breakthrough_targettype(
        self,
        start_location,
        facility_type: str,
        utm: bool = True,
    ) -> List[List[float]]:
        target_info = self.agent.facilities.pick_random_target(facility_type, utm)
        loc = target_info["location"]
        return [
            list(start_location) if not isinstance(start_location, list) else start_location,
            list(loc) if isinstance(loc, tuple) else loc,
        ]

    def plan_breakthrough_target(
        self,
        start_location,
        target: str,
        utm: bool = True,
    ) -> List[List[float]]:
        target_loc = self.agent.facilities.get_target_location(target, utm)
        return [
            list(start_location) if not isinstance(start_location, list) else start_location,
            list(target_loc) if isinstance(target_loc, tuple) else target_loc,
        ]

    def planbreakthrough_target_location(
        self,
        start_location,
        target_location: List[float],
        utm: bool = True,
    ) -> List[List[float]]:
        return [
            list(start_location) if not isinstance(start_location, list) else start_location,
            list(target_location) if isinstance(target_location, tuple) else target_location,
        ]

    def plan_detour(
        self,
        start_location,
        target: str,
        detour_steps: int = 10,
        utm: bool = True,
    ) -> List[List[float]]:
        fac = self.agent.facilities

        if self._is_coordinate_target(target):
            detour_polygon_xys = fac.get_spec_facility_polyborder(
                [float(target[0]), float(target[1])],
                bfunc.GlobalBasicConfigs.AVOID_AVERAGE_DISTANCE,
                ll2utm=utm,
            )
        elif isinstance(target, (list, tuple)):
            raise ValueError(f"Unknown detour target: {target}")
        elif target in fac.facilities_info.keys() or target in fac.defend_rings.keys():
            if target in fac.antiairs:
                detour_polygon_xys = fac.get_spec_facility_polyborder(
                    fac.facilities_info[target],
                    bfunc.GlobalBasicConfigs.AVOID_ANTIAIR_DISTANCE,
                    ll2utm=utm,
                )
            elif target in fac.headquartors:
                detour_polygon_xys = fac.get_spec_facility_polyborder(
                    fac.facilities_info[target],
                    bfunc.GlobalBasicConfigs.AVOID_HQ_DISTANCE,
                    ll2utm=utm,
                )
            elif target in fac.probers:
                detour_polygon_xys = fac.get_spec_facility_polyborder(
                    fac.facilities_info[target],
                    bfunc.GlobalBasicConfigs.AVOID_RADAR_DISTANCE,
                    ll2utm=utm,
                )
            elif target in fac.defend_rings.keys():
                detour_polygon_xys = fac.get_defence_rings_polyborder()
            else:
                detour_polygon_xys = fac.get_spec_facility_polyborder(
                    fac.facilities_info[target],
                    bfunc.GlobalBasicConfigs.AVOID_AVERAGE_DISTANCE,
                    ll2utm=utm,
                )
        elif target == "defence_rings":
            detour_polygon_xys = fac.get_defence_rings_polyborder()
        elif target == "probe_facilities":
            detour_polygon_xys = fac.get_probe_facilities_polyborder()
        elif target == "antiair_facilities":
            detour_polygon_xys = fac.get_defence_facilities_polyborder()
        else:
            raise ValueError(f"Unknown detour target: {target}")

        border = qpp.SimpleBorders(detour_polygon_xys[0])
        xy_start = start_location if len(start_location) == 2 else start_location[:2]
        traj_locations = border.move_along_border(
            xy_start,
            steps=detour_steps,
            direction=np.random.choice(["clockwise", "anticlockwise"]),
        )
        return [list(item) if isinstance(item, tuple) else list(item) for item in traj_locations]

    def plan_escape(
        self,
        start_location,
        target: str = "defence_rings",
        utm: bool = True,
    ) -> List[List[float]]:
        fac = self.agent.facilities

        if self._is_coordinate_target(target):
            escape_polygon_xys = fac.get_spec_facility_polyborder(
                [float(target[0]), float(target[1])],
                bfunc.GlobalBasicConfigs.AVOID_AVERAGE_DISTANCE,
                ll2utm=utm,
            )
        elif isinstance(target, (list, tuple)):
            raise ValueError(f"Unknown escape target: {target}")
        elif target in fac.facilities_info.keys() or target in fac.defend_rings.keys():
            if target in fac.antiairs:
                escape_polygon_xys = fac.get_spec_facility_polyborder(
                    fac.facilities_info[target],
                    bfunc.GlobalBasicConfigs.AVOID_ANTIAIR_DISTANCE,
                    ll2utm=utm,
                )
            elif target in fac.headquartors:
                escape_polygon_xys = fac.get_spec_facility_polyborder(
                    fac.facilities_info[target],
                    bfunc.GlobalBasicConfigs.AVOID_HQ_DISTANCE,
                    ll2utm=utm,
                )
            elif target in fac.probers:
                escape_polygon_xys = fac.get_spec_facility_polyborder(
                    fac.facilities_info[target],
                    bfunc.GlobalBasicConfigs.AVOID_RADAR_DISTANCE,
                    ll2utm=utm,
                )
            elif target in fac.defend_rings.keys():
                escape_polygon_xys = fac.get_defence_rings_polyborder()
            else:
                escape_polygon_xys = fac.get_spec_facility_polyborder(
                    fac.facilities_info[target],
                    bfunc.GlobalBasicConfigs.AVOID_AVERAGE_DISTANCE,
                    ll2utm=utm,
                )
        elif target == "defence_rings":
            escape_polygon_xys = fac.get_defence_rings_polyborder()
        elif target == "probe_facilities":
            escape_polygon_xys = fac.get_probe_facilities_polyborder()
        elif target == "antiair_facilities":
            escape_polygon_xys = fac.get_defence_facilities_polyborder()
        else:
            raise ValueError(f"Unknown escape target: {target}")

        border = qpp.SimpleBorders(escape_polygon_xys[0])
        if not border.is_inside_border(start_location):
            border_traj = [start_location, start_location]
            return [list(p) if isinstance(p, tuple) else list(p) for p in border_traj]

        xy = start_location if len(start_location) == 2 else start_location[:2]
        nearest_point = border.get_nearest_border_vertex(xy).coords[0]
        border_traj = [
            start_location,
            list(nearest_point) if isinstance(nearest_point, tuple) else nearest_point,
        ]
        return [list(p) if isinstance(p, tuple) else list(p) for p in border_traj]

    def execute_path_planning_from_digraph(
        self,
        digraph: Dict[str, Any],
        start_h: int,
        end_h: int,
    ):
        digraph_attr = digraph["attrs"]
        cur_target = digraph_attr["target"]

        action_class = digraph_attr.get("action_class")
        if action_class == "recon":
            return self.execute_orbit(cur_target, start_h, end_h)
        if action_class == "support":
            if digraph_attr.get("action") == "standby":
                return self.execute_loiter(start_h, end_h)
            return self.execute_orbit(cur_target, start_h, end_h)
        if action_class in ("assault", "maneuver"):
            return self.execute_breakthrough(cur_target, start_h, end_h)

        order_type = digraph_attr["order_type"]
        if order_type in ("breakthrough", "singleton"):
            return self.execute_breakthrough(cur_target, start_h, end_h)
        if order_type == "escape":
            return self.execute_escape(cur_target, start_h, end_h)
        if order_type == "detour":
            return self.execute_detour(cur_target, start_h, end_h)
        if order_type == "routine":
            return self.execute_routine(cur_target, start_h, end_h)

        self.log(f"[{self.agent.name}] Unknown order_type: {order_type}")
        return []

    def _plan_point_target(self, target: Any) -> List[List[float]]:
        if self._is_coordinate_target(target):
            return self.planbreakthrough_target_location(
                self.agent.traj[-1],
                self._coordinate_to_utm(target),
            )
        if target in bfunc.GlobalBasicConfigs.PLANNING_BREAKTHROUGH_FACILITY_TYPES:
            return self.plan_breakthrough_targettype(self.agent.traj[-1], target)
        if target in self.agent.facilities.get_facilities_names():
            return self.plan_breakthrough_target(self.agent.traj[-1], target)
        if target == "aggregate_point":
            rendezvous_pos = self.agent.io.get_rendezvous_point(self.agent.merge_peers)
            return self.planbreakthrough_target_location(self.agent.traj[-1], rendezvous_pos)
        return [self.agent.traj[-1], self.agent.traj[-1]]

    def execute_breakthrough(self, target: str, start_h: int, end_h: int):
        traj_2d = self._plan_point_target(target)
        return self.insert_height_val("breakthrough", traj_2d, start_h, end_h)

    def execute_routine(self, target: str, start_h: int, end_h: int):
        traj_2d = self._plan_point_target(target)
        return self.insert_height_val("routine", traj_2d, start_h, end_h)

    def execute_escape(self, target: str, start_h: int, end_h: int):
        traj_2d = self.plan_escape(self.agent.traj[-1], target)
        return self.insert_height_val("escape", traj_2d, start_h, end_h)

    def execute_detour(self, target: str, start_h: int, end_h: int):
        traj_2d = self.plan_detour(self.agent.traj[-1], target)
        traj_2d[0].append(self.agent.traj[-1][2])
        return self.insert_height_val("detour", traj_2d, start_h, end_h)

    def execute_orbit(
        self,
        target: str,
        start_h: int,
        end_h: int,
        radius: float = 80.0,
        steps: int = 8,
    ):
        if self._is_coordinate_target(target):
            cx, cy = self._coordinate_to_utm(target)
        elif isinstance(target, (list, tuple)):
            raise KeyError(f"Unknown orbit target: {target}")
        else:
            tgt = self.agent.facilities.get_target_location(target, utm=True)
            cx, cy = tgt[0], tgt[1]

        start = self.agent.traj[-1]
        orbit = [
            [cx + radius * np.cos(2 * np.pi * k / steps),
             cy + radius * np.sin(2 * np.pi * k / steps)]
            for k in range(steps + 1)
        ]
        traj_2d = [list(start[:2])] + orbit
        return self.insert_height_val("orbit", traj_2d, start_h, end_h)

    def execute_loiter(self, start_h: int, end_h: int):
        pos = self.agent.traj[-1]
        traj_2d = [list(pos[:2]), list(pos[:2])]
        return self.insert_height_val("loiter", traj_2d, start_h, end_h)

    def execute_attack(self, target: str) -> None:
        self.log(f"{self.agent.name} is attacking {target} ...")

    def execute_join_formation(
        self,
        leader_id: str,
        off_x: float,
        off_y: float,
        off_z: float,
    ) -> None:
        self.agent.formation_state["role"] = "follower"
        self.agent.formation_state["leader_id"] = leader_id
        self.agent.formation_state["offset"] = np.array([off_x, off_y, off_z])

    def execute_leave_formation(self) -> None:
        self.agent.formation_state["role"] = "independent"
        self.agent.formation_state["leader_id"] = None
        if hasattr(self.agent, "io") and hasattr(self.agent, "self_uid"):
            curr_pos = self.agent.io.get_pos(self.agent.self_uid, blue=True)
            if curr_pos:
                self.agent.traj = [[curr_pos["x"], curr_pos["y"], curr_pos["z"]]]
                self.agent.io.set_lookahead(self.agent.self_uid, 0)
