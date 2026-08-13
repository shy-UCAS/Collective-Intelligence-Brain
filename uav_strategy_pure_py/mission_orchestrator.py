"""Pure Python mission orchestrator and trajectory export."""

from __future__ import annotations

import collections
import json
import os
import random
import time
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np


from uav_strategy_pure_py.planning_modules import basic_functions as bfunc

from uav_strategy_pure_py.behaviours import DT, SyncAPFStepEnhance
from uav_strategy_pure_py.uav_agent import (
    SIM_CLOCK_DT_KEY,
    SIM_CLOCK_START_KEY,
    PureBlueUAVAgent,
    simulation_time_ms,
)


def trajectory_timestamps_ms(extras: List[Dict[str, Any]]) -> List[int]:
    timestamps = []
    for extra in extras or []:
        value = extra.get("simTimeMs")
        if value is None:
            value = extra.get("timestamp")
            if value is None:
                raise ValueError("trajectory metadata is missing simTimeMs/timestamp")
            value = float(value)
            if abs(value) < 10_000_000_000:
                value *= 1000.0
        timestamps.append(int(round(float(value))))
    return timestamps


def _coerce_legacy_waiting(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"", "false", "0", "no", "none", "null"}
    return bool(value)


def is_analysis_ready_trajectory_point(extra: Dict[str, Any]) -> bool:
    if not isinstance(extra, dict):
        return False
    segment_key = extra.get("segment_key")
    frame_id = extra.get("frame_id")
    if segment_key in (None, "", "initializing"):
        return False
    if isinstance(frame_id, bool) or not isinstance(frame_id, int) or frame_id <= 0:
        return False

    flight_phase = extra.get("flight_phase")
    if flight_phase is not None:
        return flight_phase == "task_flight" and extra.get("is_waiting") is False

    if _coerce_legacy_waiting(extra.get("is_waiting")):
        return False
    lookahead = extra.get("lookahead", frame_id)
    return not isinstance(lookahead, bool) and isinstance(lookahead, int) and lookahead > 0


def build_segment_common_frames(
    raw_trajs: Dict[str, Tuple[List[List[float]], List[Dict[str, Any]]]]
) -> Dict[str, set]:
    segment_agents = collections.defaultdict(set)
    segment_frames = collections.defaultdict(lambda: collections.defaultdict(set))
    for name, (_, extras) in raw_trajs.items():
        for extra in extras or []:
            if not is_analysis_ready_trajectory_point(extra):
                continue
            segment_key = extra["segment_key"]
            segment_agents[segment_key].add(name)
            segment_frames[segment_key][name].add(extra["frame_id"])

    common_frames = {}
    for segment_key, agent_names in segment_agents.items():
        frame_sets = [segment_frames[segment_key][name] for name in agent_names]
        common_frames[segment_key] = set.intersection(*frame_sets) if frame_sets else set()
    return common_frames


def select_analysis_trajectory(
    trajectory: List[List[float]],
    extras: List[Dict[str, Any]],
    segment_common_frames: Dict[str, set],
) -> Tuple[List[List[float]], List[Dict[str, Any]]]:
    aligned_count = min(len(trajectory or []), len(extras or []))
    last_index = {}
    for index in range(aligned_count):
        extra = extras[index]
        if is_analysis_ready_trajectory_point(extra):
            last_index[(extra["segment_key"], extra["frame_id"])] = index

    selected_trajectory = []
    selected_extras = []
    for index in range(aligned_count):
        extra = extras[index]
        if not is_analysis_ready_trajectory_point(extra):
            continue
        key = (extra["segment_key"], extra["frame_id"])
        if last_index.get(key) != index:
            continue
        if extra["frame_id"] not in segment_common_frames.get(extra["segment_key"], set()):
            continue
        selected_trajectory.append(trajectory[index])
        selected_extras.append(extra)
    return selected_trajectory, selected_extras


def _flight_plan_segment_nodes(segment: Any) -> Tuple[str, str]:
    raw_pair = segment.get("segment") if isinstance(segment, dict) else segment
    if not isinstance(raw_pair, (list, tuple)) or len(raw_pair) < 2:
        raise ValueError("flight_plan segment must contain from/to nodes")
    return str(raw_pair[0]), str(raw_pair[1])


def _route_points_from_utm(
    trajectory: List[List[float]],
    lnglat_converter: Any,
    segment_key: str,
) -> List[Dict[str, float]]:
    trajectory_np = np.asarray(trajectory, dtype=float)
    if trajectory_np.ndim != 2 or trajectory_np.shape[0] == 0 or trajectory_np.shape[1] < 3:
        raise ValueError("{} requires non-empty [x,y,z] reference points".format(segment_key))
    if not np.isfinite(trajectory_np[:, :3]).all():
        raise ValueError("{} contains non-finite reference points".format(segment_key))

    lnglat = np.asarray(lnglat_converter.utm_to_lng_lat_array(trajectory_np), dtype=float)
    if lnglat.ndim != 2 or lnglat.shape[0] != trajectory_np.shape[0] or lnglat.shape[1] < 2:
        raise ValueError("{} UTM conversion returned an invalid shape".format(segment_key))
    return [
        {
            "lng": float(lnglat[index, 0]),
            "lat": float(lnglat[index, 1]),
            "alt": float(trajectory_np[index, 2]),
        }
        for index in range(trajectory_np.shape[0])
    ]


def build_complete_flight_plan_export(
    flight_plan: Iterable[Any],
    member_id: str,
    segment_trajectory_getter: Callable[[str, str, str], List[List[float]]],
    lnglat_converter: Any,
) -> Dict[str, Any]:
    ordered_plan = []
    exported_segments = []
    missing_segments = []
    complete_utm: List[List[float]] = []

    for order, raw_segment in enumerate(flight_plan or []):
        from_node, to_node = _flight_plan_segment_nodes(raw_segment)
        segment_key = "{}_{}".format(from_node, to_node)
        ordered_plan.append(
            {
                "order": order,
                "segmentKey": segment_key,
                "fromNode": from_node,
                "toNode": to_node,
            }
        )
        try:
            raw_trajectory = segment_trajectory_getter(from_node, to_node, member_id)
            if not raw_trajectory:
                missing_segments.append(
                    {"segmentKey": segment_key, "reason": "member reference trajectory is missing"}
                )
                continue
            trajectory_np = np.asarray(raw_trajectory, dtype=float)
            route_points = _route_points_from_utm(raw_trajectory, lnglat_converter, segment_key)
        except (TypeError, ValueError) as exc:
            missing_segments.append({"segmentKey": segment_key, "reason": str(exc)})
            continue

        segment_utm = trajectory_np[:, :3].tolist()
        exported_segments.append(
            {
                "order": order,
                "segmentKey": segment_key,
                "fromNode": from_node,
                "toNode": to_node,
                "routePointCount": len(route_points),
                "flightRoute": route_points,
            }
        )

        start_index = 0
        if complete_utm and np.allclose(
            np.asarray(complete_utm[-1], dtype=float),
            np.asarray(segment_utm[0], dtype=float),
            rtol=0.0,
            atol=1e-6,
        ):
            start_index = 1
        complete_utm.extend(segment_utm[start_index:])

    complete_route = (
        _route_points_from_utm(complete_utm, lnglat_converter, "complete_flight_plan")
        if complete_utm
        else []
    )
    return {
        "source": "nodes_pair_member_traj",
        "altitudeReference": "AMSL",
        "complete": bool(ordered_plan) and not missing_segments,
        "flightPlan": ordered_plan,
        "segmentCount": len(ordered_plan),
        "routePointCount": len(complete_route),
        "flightRoute": complete_route,
        "segments": exported_segments,
        "missingSegments": missing_segments,
    }


def build_mission_meta(digraph_attrs, planned_routes, raw_trajs) -> Dict[str, Any]:
    member_by_segment = {}
    for name, route in (planned_routes or {}).items():
        for segment in (route or {}).get("flightPlan") or []:
            segment_key = segment.get("segmentKey")
            if segment_key:
                member_by_segment.setdefault(segment_key, []).append(name)

    def _leader_of(members):
        for name in sorted(members):
            _, traj_extra = (raw_trajs or {}).get(name, ([], []))
            for extra in traj_extra or []:
                if not isinstance(extra, dict):
                    continue
                leader = extra.get("leader_id")
                if isinstance(leader, str) and leader and leader != "initializing":
                    return leader
        return sorted(members)[0] if members else None

    swarms = []
    seen_members = set()
    for index, edge in enumerate(digraph_attrs or []):
        if not isinstance(edge, dict):
            continue
        attrs = edge.get("attrs") or {}
        segment_key = "{}_{}".format(edge.get("from"), edge.get("to"))
        members = sorted(set(member_by_segment.get(segment_key, [])))
        swarms.append(
            {
                "swarmId": "swarm%d" % (index + 1),
                "fleetNo": attrs.get("fleet_no"),
                "orderType": attrs.get("order_type"),
                "target": attrs.get("target"),
                "segmentKey": segment_key,
                "leaderId": _leader_of(members),
                "memberIds": members,
            }
        )
        seen_members.update(members)

    unassigned = sorted(set((planned_routes or {}).keys()) - seen_members)
    if unassigned:
        swarms.append(
            {
                "swarmId": "swarm%d" % (len(swarms) + 1),
                "fleetNo": None,
                "orderType": None,
                "target": None,
                "segmentKey": None,
                "leaderId": _leader_of(unassigned),
                "memberIds": unassigned,
                "note": "targets without a matching digraph edge",
            }
        )
    return {"source": "digraph_attrs", "swarms": swarms}


class MissionOrchestrator:
    def __init__(
        self,
        digraph_attrs: List[Dict[str, Any]],
        key_paths: List[List[Any]],
        facilities_file: str,
        io: Any,
        output_dir: Optional[str] = None,
    ) -> None:
        self.digraph_attrs = digraph_attrs
        self.key_paths = key_paths
        self.facilities_file = facilities_file
        self.io = io
        self.output_dir = output_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs"
        )

        self.uav_flight_plans, self.edge_attrs = self.extract_uav_trajectories(
            digraph_attrs, key_paths
        )
        print(f"Generated {len(self.uav_flight_plans)} flight plans.")
        print(json.dumps(self.uav_flight_plans, indent=2))
        print("Edge attributes with assigned UAV IDs:")
        print(json.dumps({f"{k[0]}->{k[1]}": v for k, v in self.edge_attrs.items()}, indent=2))

        self.active_agents: Dict[str, PureBlueUAVAgent] = {}
        self._lnglat2utm_convertor = bfunc.LngLat2UTM()
        self.all_trajectories = {}

    def extract_uav_trajectories(self, json_data, key_paths):
        edge_attrs = {}
        graph = collections.defaultdict(list)

        for item in json_data:
            u, v = str(item["from"]), str(item["to"])
            total_drones = item["members_num"] + 1
            edge_attrs[(u, v)] = {"count": total_drones, "uav_ids": []}
            graph[u].append(v)

        uav_trajectories = []
        remaining_flow = {edge: attr["count"] for edge, attr in edge_attrs.items()}
        starts = set(str(path[0]) for path in key_paths)

        for start_node in starts:
            start_edges = [e for e in remaining_flow if e[0] == start_node]
            total_at_start = sum(remaining_flow[e] for e in start_edges)

            for i in range(total_at_start):
                current_node = start_node
                single_uav_path = []
                while True:
                    possible_next = [
                        v
                        for v in graph[current_node]
                        if remaining_flow.get((current_node, v), 0) > 0
                    ]
                    if not possible_next:
                        break
                    next_node = random.choice(possible_next)
                    edge = (current_node, next_node)
                    single_uav_path.append(edge)
                    remaining_flow[edge] -= 1
                    current_node = next_node

                if single_uav_path:
                    sorted_starts = sorted(list(starts))
                    idx = sorted_starts.index(start_node)
                    uav_trajectories.append(
                        {"id": f"agent_{idx + 1}_{i}", "path": single_uav_path}
                    )

        for traj in uav_trajectories:
            for seg in traj["path"]:
                if (seg[0], seg[1]) in edge_attrs.keys():
                    edge_attrs[(seg[0], seg[1])]["uav_ids"].append(traj["id"])

        return uav_trajectories, edge_attrs

    def _spawn_agents(self) -> None:
        for plan in self.uav_flight_plans:
            agent = PureBlueUAVAgent(
                uid=plan["id"],
                flight_plan=plan["path"],
                siblings_ref=self.edge_attrs,
                orchestrator=self,
                io=self.io,
                facilities_file=self.facilities_file,
                digraph_attrs=self.digraph_attrs,
            )
            self.active_agents[plan["id"]] = agent

        for agent in self.active_agents.values():
            agent.request_planning()

    def run(self, max_rounds: int = 200000) -> None:
        print("Mission Orchestrator Started (Pure Python Memory Mode).")
        self.io.set_world_state("sim_round", 0)
        simulation_start_time_ms = int(time.time() * 1000)
        simulation_dt_ms = int(round(DT * 1000))
        self.io.set_world_state(SIM_CLOCK_START_KEY, simulation_start_time_ms)
        self.io.set_world_state(SIM_CLOCK_DT_KEY, simulation_dt_ms)
        print(
            "[System] Simulation clock initialized: "
            f"startTimeMs={simulation_start_time_ms}, dtMs={simulation_dt_ms}"
        )

        self._spawn_agents()
        behaviour = SyncAPFStepEnhance(period=DT)

        current_round = 0
        while self.active_agents and current_round < max_rounds:
            for agent in list(self.active_agents.values()):
                if agent.is_finished:
                    continue
                behaviour.agent = agent
                behaviour.run(current_round=current_round)

            current_round += 1
            self.io.set_world_state("sim_round", current_round)

            if all(agent.is_finished for agent in self.active_agents.values()):
                break

        print("All persistent missions completed.")
        self.save_trajectories()

    def save_trajectories(self) -> None:
        print("Collecting trajectories and facility info...")

        facilities_data = {}
        if os.path.exists(self.facilities_file):
            with open(self.facilities_file, "r", encoding="utf-8") as f:
                facilities_data = json.load(f)

        facilities_str = facilities_data.get("facilities_str", {})
        defence_rings = facilities_data.get("defence_rings", {})
        airspaces = facilities_data.get("airspaces", [])

        for ring_name, ring_llgs in defence_rings.items():
            flat = []
            for lng, lat in zip(ring_llgs["lngs"], ring_llgs["lats"]):
                flat.extend([lng, lat])
            facilities_str[ring_name.upper()] = flat

        raw_trajs = {}
        for name, agent in self.active_agents.items():
            traj_utm = agent.io.get_traj(agent.self_uid)
            traj_extra = agent.io.get_traj_extra(agent.self_uid)
            raw_trajs[name] = (traj_utm, traj_extra)

        planned_routes = {}
        for name, agent in self.active_agents.items():
            try:
                planned_routes[name] = build_complete_flight_plan_export(
                    agent.flight_plan,
                    agent.self_uid,
                    agent.io.get_nodes_pair_member_traj,
                    self._lnglat2utm_convertor,
                )
            except Exception as exc:
                planned_routes[name] = {
                    "source": "nodes_pair_member_traj",
                    "altitudeReference": "AMSL",
                    "complete": False,
                    "flightPlan": [],
                    "segmentCount": len(agent.flight_plan or []),
                    "routePointCount": 0,
                    "flightRoute": [],
                    "segments": [],
                    "missingSegments": [
                        {"segmentKey": None, "reason": "export failed: {}".format(exc)}
                    ],
                }

            if not planned_routes[name]["complete"]:
                print(
                    "[save_trajectories] Warning: incomplete planned route for {}: {}".format(
                        name, planned_routes[name]["missingSegments"]
                    )
                )

        mission_meta = build_mission_meta(self.digraph_attrs, planned_routes, raw_trajs)
        segment_common_frames = build_segment_common_frames(raw_trajs)
        print(
            "segment_common_frames: "
            + json.dumps(
                {key: sorted(value) for key, value in segment_common_frames.items()},
                indent=2,
            )
        )

        uavs_coords = {}
        for name, agent in self.active_agents.items():
            traj_utm, traj_extra = raw_trajs.get(name, ([], []))
            if traj_utm:
                traj_utm, traj_extra = select_analysis_trajectory(
                    traj_utm,
                    traj_extra or [],
                    segment_common_frames,
                )
                if not traj_utm:
                    print(f"[save_trajectories] Warning: no analysis-ready synced frames for {name}")
                    continue

                traj_np = np.array(traj_utm)
                if traj_np.shape[0] > 0:
                    ll = self._lnglat2utm_convertor.utm_to_lng_lat_array(traj_np)
                    lats = ll[:, 1].tolist()
                    lngs = ll[:, 0].tolist()
                    alts = traj_np[:, 2].tolist()
                    ts = trajectory_timestamps_ms(traj_extra)
                    uavs_coords[name] = {
                        "lats": lats,
                        "lngs": lngs,
                        "alts": alts,
                        "ts": ts,
                        "extras": traj_extra,
                    }

        uavs_coords_raw = {}
        for name, (traj_utm, traj_extra) in raw_trajs.items():
            if traj_utm:
                traj_np = np.array(traj_utm)
                if traj_np.shape[0] > 0:
                    ll = self._lnglat2utm_convertor.utm_to_lng_lat_array(traj_np)
                    lats = ll[:, 1].tolist()
                    lngs = ll[:, 0].tolist()
                    alts = traj_np[:, 2].tolist()
                    ts = trajectory_timestamps_ms(traj_extra)
                    uavs_coords_raw[name] = {
                        "lats": lats,
                        "lngs": lngs,
                        "alts": alts,
                        "ts": ts,
                        "extras": traj_extra,
                    }

        simulation_meta = {
            "startTimeMs": None,
            "dtMs": int(round(DT * 1000)),
            "timeBasis": "SIMULATION_ROUND",
            "kinematics": {
                "maxHorizontalSpeedMps": 16.0,
                "maxClimbRateMps": 5.0,
                "maxDescentRateMps": 5.0,
            },
        }
        if self.active_agents:
            raw_start = self.io.get_world_state(SIM_CLOCK_START_KEY)
            raw_dt = self.io.get_world_state(SIM_CLOCK_DT_KEY)
            if raw_start is not None:
                simulation_meta["startTimeMs"] = int(raw_start)
            if raw_dt is not None:
                simulation_meta["dtMs"] = int(raw_dt)

        final_data = {
            "simulationMeta": simulation_meta,
            "uavs_coords_str": uavs_coords,
            "uavs_coords_raw": uavs_coords_raw,
            "plannedRoutes": planned_routes,
            "facilities_str": facilities_str,
            "defence_rings": defence_rings,
            "airspaces": airspaces,
            "missionMeta": mission_meta,
        }

        os.makedirs(self.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(self.output_dir, f"uav_trajectories_pure_{timestamp}.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(final_data, f, indent=4)
        print(f"All data saved to {output_file}")
