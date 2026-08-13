"""Pure Python UAV agent.

This class replaces ``BlueUAVAgent`` from ``uav_dynamic_agents02.py``.  The
original class inherited ``spade_bdi.bdi.BDIAgent`` and used an ASL file plus
AgentSpeak goals to sequence segments.  Here the same sequencing is expressed
with two ordinary methods: ``request_planning`` and ``plan_current_segment``.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

import numpy as np
import random


from uav_strategy_pure_py.planning_modules import basic_functions as bfunc
from uav_strategy_pure_py.planning_modules.formation_generator import (
    Formation_Elements,
    FormationGenerator3D,
)

from uav_strategy_pure_py.planning_lib import PlanningLib


SIM_CLOCK_START_KEY = "sim_start_time_ms"
SIM_CLOCK_DT_KEY = "sim_dt_ms"


def simulation_time_ms(start_time_ms: int, round_id: int, dt_ms: int) -> int:
    return int(start_time_ms) + int(round_id) * int(dt_ms)


class PureBlueUAVAgent:
    VERBOSE = False

    def __init__(
        self,
        uid: str,
        flight_plan: List[tuple],
        siblings_ref: Dict[tuple, Dict[str, Any]],
        orchestrator: Any,
        io: Any,
        facilities_file: str,
        digraph_attrs: List[Dict[str, Any]],
        init_pos: Optional[List[float]] = None,
    ) -> None:
        self.self_uid = uid
        self.name = uid
        self.jid = uid
        self.flight_plan = flight_plan
        self.siblings_ref = siblings_ref
        self.orchestrator = orchestrator
        self.io = io
        self.digraph_attrs = digraph_attrs
        self.step_logs: List[str] = []

        self.path_index = 0
        self.is_finished = False
        self._need_wait_siblings = False
        self._is_alive = True
        self.is_final_task = False
        self.waiting_next_segment = True

        if self.flight_plan:
            self.current_node = self.flight_plan[0][0]
            self.next_node = self.flight_plan[0][1]
        else:
            self.current_node = None
            self.next_node = None

        self.facilities = self._default_facilities(facilities_file)
        self.position = init_pos
        self._lnglat2utm_convertor = bfunc.LngLat2UTM()

        if self.position is None:
            _start_pair = (init_loc3, init_loc4)
            _rdm_init_pos = bfunc.generate_circle_positions_from_diameter(
                1, _start_pair[0], _start_pair[1]
            )
            self.position = _rdm_init_pos[0]
            self.log(f"{self.self_uid} no initial position provided, generated random position")

        self.merge_peers: List[str] = []
        self.traj = self._lnglat2utm_convertor.lng_lat_to_utm_array(
            np.array([self.position])
        ).tolist()
        self.traj[0].append(self.position[2])
        self.log(f"{self.self_uid} initialized at position: {self.position}")

        self.io.add_uav_id(self.self_uid, blue=True)
        initial_time_fields = self.simulation_time_fields(round_id=0)
        self.io.set_pos(
            self.self_uid,
            self.traj[0][0],
            self.traj[0][1],
            self.position[2],
            ts_ms=initial_time_fields["simTimeMs"],
            recorded_at_ms=initial_time_fields["recordedAtMs"],
        )
        self.io.set_traj(self.self_uid, [[self.traj[0][0], self.traj[0][1], self.position[2]]])
        self.io.set_lookahead(self.self_uid, 0)

        self.io.set_uav_state(self.self_uid, "round_done", "-1")
        self.io.set_uav_state(self.self_uid, "current_segment_sync", "")
        self.io.set_uav_state(self.self_uid, "current_frame_sync", "")
        self.io.set_uav_state(self.self_uid, "can_task_start", "false")

        self.current_segment_siblings: List[str] = []
        self.current_segment_key: Optional[str] = None
        self.has_synced_segment = False
        self.io.set_uav_sync_state(self.self_uid, False)

        self.current_segment_id = None
        self.current_depends_on: List[Any] = []
        self._waiting_for_deps = False

        self.planning_lib = PlanningLib(self)
        self.cur_reference_traj: List[List[float]] = []
        self.members_cur_reference_traj: List[List[List[float]]] = []
        self.height_range_set = height_range_value_set
        self.direction_range_set = direction_range_set

        self.can_task_start = True
        self.if_set_ref_traj = False
        self.my_id = self.self_uid

        self.formation_type = "unknown"
        self.global_step_id = 0
        self.segment_step_id = 0
        self.my_ack = -1
        self.formation_state: Dict[str, Any] = {
            "role": "independent",
            "leader_id": None,
            "offset": None,
        }

        extra_info = {
            "cur_siblings_ids": "initializing",
            "formation_type": "unknown",
            "my_ack": f"{self.my_ack} initializing",
            "frame_id": f"{self.segment_step_id} initializing",
            "lookahead": "0",
            "global_id": f"{self.global_step_id} initializing",
            "segment_key": "initializing",
            "is_waiting": True,
            "waiting_reason": "initializing",
            "flight_phase": "initializing",
            "dist_to_target": "initializing",
            "lookahead_coord": None,
            "phase_state": "initializing",
            "leader_id": "initializing",
            "logs": self.step_logs.copy(),
            **initial_time_fields,
        }
        self.step_logs.clear()
        self.io.set_traj_extra(self.self_uid, [extra_info])

    def log(self, msg: str) -> None:
        if self.VERBOSE:
            print(msg)
        self.step_logs.append(msg)

    def _default_facilities(self, facilities_file: str) -> Any:
        with open(facilities_file, "r", encoding="utf-8") as f:
            facilities_info = json.load(f)
        return bfunc.Facilities(
            facilities_info["facilities_str"],
            facilities_info["defence_rings"],
        )

    def simulation_time_fields(self, round_id: Optional[int] = None) -> Dict[str, Any]:
        if round_id is None:
            raw_round = self.io.get_world_state("sim_round")
            if raw_round is None:
                raise RuntimeError("sim_round is not initialized")
            round_id = int(raw_round)

        raw_start = self.io.get_world_state(SIM_CLOCK_START_KEY)
        raw_dt = self.io.get_world_state(SIM_CLOCK_DT_KEY)
        if raw_start is None or raw_dt is None:
            raise RuntimeError("simulation clock is not initialized")

        sim_time_ms = simulation_time_ms(int(raw_start), int(round_id), int(raw_dt))
        return {
            "timestamp": sim_time_ms / 1000.0,
            "simTimeMs": sim_time_ms,
            "recordedAtMs": int(time.time() * 1000),
            "round_id": int(round_id),
        }

    def request_planning(self) -> None:
        if getattr(self, "can_task_start", False):
            self.plan_current_segment()

    def plan_current_segment(self) -> None:
        if self.is_finished:
            return

        cur_start_node = str(self.current_node)
        cur_end_node = str(self.next_node)

        self.has_synced_segment = False
        self.io.set_uav_state(self.self_uid, "current_segment_sync", "")
        self.io.set_uav_state(self.self_uid, "current_frame_sync", "")
        self.io.set_uav_state(self.self_uid, "can_task_start", "false")
        self.io.set_lookahead(self.self_uid, 0)
        self.current_segment_key = f"{cur_start_node}_{cur_end_node}"

        for digraph_attr in self.digraph_attrs:
            if str(digraph_attr["from"]) == cur_start_node and str(digraph_attr["to"]) == cur_end_node:
                attrs = digraph_attr["attrs"]
                self.current_segment_id = attrs.get("segment_id")
                self.current_depends_on = attrs.get("depends_on") or []
                break

        unmet = [
            d for d in self.current_depends_on if self.io.get_flag(f"seg_done:{d}") != "1"
        ]
        if unmet:
            self.log(
                f"[{self.self_uid}] segment {self.current_segment_id} waiting on deps {unmet}"
            )
            self._waiting_for_deps = True
            return
        self._waiting_for_deps = False

        self.log(
            f"[{self.self_uid}] Planning path from node {cur_start_node} to node {cur_end_node}"
        )

        _formation_type = "unknown"
        for digraph_attr in self.digraph_attrs:
            if str(digraph_attr["from"]) != cur_start_node or str(digraph_attr["to"]) != cur_end_node:
                continue

            _order_mode = digraph_attr["attrs"]["order_mode"]
            _order_target = digraph_attr["attrs"]["target"]

            if _order_mode == "aggregate" and _order_target == "aggregate_point":
                self._merge_ready_flag = False
                all_merge_peers: List[str] = []
                for edge, value in self.siblings_ref.items():
                    if edge[1] == cur_end_node:
                        peers = [uav for uav in value["uav_ids"] if uav != self.self_uid]
                        all_merge_peers.extend(peers)
                self.merge_peers = sorted(set(all_merge_peers))
            else:
                self.merge_peers = []

            cur_siblings_ids = self.siblings_ref.get(
                (cur_start_node, cur_end_node), {}
            ).get("uav_ids", [])
            self.current_segment_siblings = cur_siblings_ids
            self.log(f"[{self.self_uid}] Current segment siblings: {cur_siblings_ids}")

            base_ref_traj = self.io.get_nodes_pair_base_ref_traj(cur_start_node, cur_end_node)
            if not base_ref_traj or len(base_ref_traj) == 0:
                self.log(
                    f"[{self.self_uid}] No base reference traj found for segment "
                    f"{cur_start_node}->{cur_end_node}. Now generate it."
                )
                base_ref_traj = self.planning_lib.execute_path_planning_from_digraph(
                    digraph_attr, -1, -1
                )
                self.io.set_nodes_pair_base_ref_traj(cur_start_node, cur_end_node, base_ref_traj)

                _member_num = digraph_attr["members_num"]
                _radius = random.randint(20, 30)
                _angle = random.randint(30, 60)
                _max_offset = random.uniform(30, 50)
                _noise_scale = random.uniform(0.00001, 0.00005)
                _angle_noise_scale = random.uniform(1.0, 5.0)
                _formation_type = random.choice(
                    ["circular", "vertical", "horizontal", "vshape", "arc"]
                )
                self.io.set_flag(
                    f"formation_type:{cur_start_node}:{cur_end_node}", _formation_type
                )

                fleet_formation_config = Formation_Elements(
                    member_num=_member_num + 1,
                    radius=_radius,
                    angle=_angle,
                    traj=base_ref_traj,
                    max_offset=_max_offset,
                    noise_scale=_noise_scale,
                    angle_noise_scale=_angle_noise_scale,
                    formation_type=_formation_type,
                )
                members_traj_map = FormationGenerator3D(
                    formation_elements=fleet_formation_config
                ).generate_members_formation_map(cur_siblings_ids)

                for m_uid, m_traj in members_traj_map.items():
                    self.io.set_nodes_pair_member_traj(
                        cur_start_node, cur_end_node, m_uid, m_traj
                    )
                self.log(
                    f"[{self.self_uid}] Generated and saved trajectories for "
                    f"{len(members_traj_map)} members."
                )
            else:
                self.log(
                    f"[{self.self_uid}] Found existing base reference trajectory for "
                    f"segment {cur_start_node} -> {cur_end_node}."
                )
                _formation_type = self.io.get_flag(
                    f"formation_type:{cur_start_node}:{cur_end_node}"
                ) or "unknown"

            self.formation_type = _formation_type
            my_traj = self.io.get_nodes_pair_member_traj(
                cur_start_node, cur_end_node, self.self_uid
            )

            if my_traj:
                self.log(
                    f"[{self.self_uid}] Successfully retrieved my formation trajectory "
                    f"(len={len(my_traj)})."
                )
                self.cur_reference_traj = my_traj
                if not self.traj:
                    self.traj.extend(my_traj)
                else:
                    self.traj.extend(my_traj[1:])

                self.io.set_ref_traj(self.self_uid, self.cur_reference_traj)
                self.io.set_lookahead(self.self_uid, 0)
                self.io.set_uav_state(self.self_uid, "can_task_start", "false")
                self.if_set_ref_traj = False
                self.waiting_next_segment = False
                self.log(f"[{self.self_uid}] Trajectory synced to memory.")
                self.my_ack = -1
                self.segment_step_id = 0
                self.io.set_uav_state(
                    self.self_uid,
                    f"{self.current_segment_key}_segment_step_id",
                    f"{self.segment_step_id}",
                )
                self.io.set_uav_state(
                    self.self_uid,
                    f"{self.current_segment_key}_ack",
                    f"{self.my_ack}",
                )
            else:
                self.log(
                    f"[{self.self_uid}] FAILED to retrieve formation trajectory after retries!"
                )

        current_idx = self.path_index
        if current_idx + 1 < len(self.flight_plan):
            next_idx = current_idx + 1
            next_start = self.flight_plan[next_idx][0]
            next_end = self.flight_plan[next_idx][1]
            self.log(
                f"[{self.self_uid}] Segment planned. Prepared next segment: "
                f"{next_start}->{next_end}"
            )
            self.current_node = next_start
            self.next_node = next_end
            self.path_index = next_idx
        else:
            self.log(
                f"[{self.self_uid}] All segments in flight plan are planned. "
                f"Marking as final task."
            )
            self.is_final_task = True

        self.can_task_start = False


init_loc1 = [122.18105710089186, 37.51299467977935, 200.0]
init_loc2 = [122.16096051695042, 37.497235513573486, 200.0]
init_loc3 = [116.3480, 39.8720, 200.0]
init_loc4 = [116.3680, 39.8840, 200.0]


height_range_value_set = {
    "breakthrough": [[250, 400], [0, 100]],
    "escape": [[0, 100], [250, 400]],
    "detour": [[0, 100], [200, 400]],
    "orbit": [[150, 300], [150, 300]],
    "loiter": [[200, 350], [200, 350]],
    "routine": [[200, 300], [200, 300]],
}


direction_range_set = {
    "breakthrough": [-20, 20],
    "escape": [-20, 20],
    "detour": [0, 360],
}
