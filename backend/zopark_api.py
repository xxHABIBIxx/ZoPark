from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from geo import bbox_of_geometry, geometry_contains, haversine_m

MODEL_PATH = os.environ.get("ZOPARK_MODEL", "zopark_melbourne_rf.pkl")
METRICS_PATH = os.environ.get("ZOPARK_METRICS", "zopark_melbourne_metrics.json")
GRAPH_CACHE = "halifax_graph.graphml"
POI_CACHE = "halifax_pois.json"

CENTER = (44.6476, -63.5728)

GRAPH_RADIUS_M = 6000

BUNDLE_PATH = os.environ.get("ZOPARK_BUNDLE", "../data/halifax_bundle.json")

FEATURE_ORDER = [
    "heure_sin",
    "heure_cos",
    "jour_semaine",
    "est_weekend",
    "duree_max",
]

def time_features(now: datetime) -> dict:
    hour = now.hour
    weekday = now.weekday()
    return {
        "heure_sin": math.sin(2 * math.pi * hour / 24),
        "heure_cos": math.cos(2 * math.pi * hour / 24),
        "jour_semaine": weekday,
        "est_weekend": 1 if weekday >= 5 else 0,
    }

def duree_max_from_hours(hours: float) -> float:
    return -1.0 if hours >= 24.0 else float(hours)

RULE_TO_HOURS = {"min30": 0.5, "hour1": 1.0, "hour2": 2.0, "hour3": 3.0}

def _duration_hours(rule) -> float:
    if isinstance(rule, dict):
        return RULE_TO_HOURS.get(rule.get("ruleType"), 24.0)
    return 24.0

class ZoParkRouter:
    def __init__(self) -> None:
        import joblib
        import networkx as nx
        import osmnx as ox

        self.nx = nx
        self.ox = ox
        self.degraded_reason: str | None = None
        self._spots: list[dict] | None = None

        if os.path.exists(GRAPH_CACHE):
            print(f"[INIT] lecture du graphe en cache : {GRAPH_CACHE}")
            self.graph = ox.load_graphml(GRAPH_CACHE)
        else:
            print("[INIT] telechargement du reseau routier via OSMnx...")
            self.graph = ox.graph_from_point(
                CENTER, dist=GRAPH_RADIUS_M, network_type="drive"
            )
            ox.save_graphml(self.graph, GRAPH_CACHE)
            print(f"[INIT] graphe mis en cache dans {GRAPH_CACHE}")

        self.model = None
        if os.path.exists(MODEL_PATH):
            self.model = joblib.load(MODEL_PATH)
            print(f"[INIT] modele appris charge : {MODEL_PATH}")
        else:
            print(f"[INIT] pas de {MODEL_PATH} — grille parametrique du bundle utilisee")
        self._grid: dict | None = None

        self._enrich_graph()
        print(
            f"[INIT] pret : {self.graph.number_of_nodes()} intersections, "
            f"{self.graph.number_of_edges()} rues"
        )

    def _enrich_graph(self) -> None:
        try:
            with open(BUNDLE_PATH, encoding="utf-8") as fh:
                raw = json.load(fh)["spots"]
        except (OSError, KeyError) as exc:
            print(f"[FEAT] bundle illisible ({exc}) — caracteristiques neutres")
            raw = []

        refs = [
            (
                s["lat"],
                s["lon"],
                float(s.get("maxHours") or 24.0),
                float(s.get("demandFactor") or 1.0),
            )
            for s in raw
            if s.get("status") == "installed"
        ]

        t0 = time.time()
        for u, v, key, data in self.graph.edges(keys=True, data=True):
            lat = (self.graph.nodes[u]["y"] + self.graph.nodes[v]["y"]) / 2
            lon = (self.graph.nodes[u]["x"] + self.graph.nodes[v]["x"]) / 2
            best_d, hours, factor = 1e9, 24.0, 1.0
            for rlat, rlon, h, f in refs:
                d = haversine_m(lat, lon, rlat, rlon)
                if d < best_d:
                    best_d, hours, factor = d, h, f

            near = best_d <= 150
            data["time_limit_hours"] = hours if near else 24.0
            data["demand_factor"] = factor if near else 1.0

        factors = sorted({d["demand_factor"] for _, _, _, d in self.graph.edges(keys=True, data=True)})
        durees = sorted({d["time_limit_hours"] for _, _, _, d in self.graph.edges(keys=True, data=True)})
        print(f"[FEAT] projete en {time.time()-t0:.1f} s")
        print(f"[FEAT] facteurs tarifaires : {factors}")
        print(f"[FEAT] durees maximales    : {durees}")

    def update_occupancy(self, now: datetime) -> dict:
        import pandas as pd

        edges = list(self.graph.edges(keys=True, data=True))

        if self.model is None:

            avail = {s["id"]: s["free"] for s in self.predict_availability(now)}
            spots = self.load_spots()
            values = []
            for u, v, key, d in edges:
                lat = (self.graph.nodes[u]["y"] + self.graph.nodes[v]["y"]) / 2
                lon = (self.graph.nodes[u]["x"] + self.graph.nodes[v]["x"]) / 2
                best_d, occ = 1e9, 0.5
                for sp in spots:
                    dist = haversine_m(lat, lon, sp["lat"], sp["lon"])
                    if dist < best_d:
                        best_d = dist
                        occ = 1.0 - avail.get(sp["id"], 0.5)
                if best_d > 250:
                    occ = 0.45
                value = min(1.0, occ * d.get("demand_factor", 1.0))
                self.graph[u][v][key]["predicted_occupancy"] = value
                values.append(value)
            lo, hi = min(values), max(values)
            return {
                "edges": len(edges),
                "min": round(lo, 4),
                "max": round(hi, 4),
                "mean": round(sum(values) / len(values), 4),
                "spread": round(hi - lo, 4),
            }

        base = time_features(now)
        rows = [
            {**base, "duree_max": duree_max_from_hours(d.get("time_limit_hours", 24.0))}
            for _, _, _, d in edges
        ]
        preds = self.model.predict_proba(pd.DataFrame(rows)[FEATURE_ORDER])[:, 1]
        adjusted = []
        for (u, v, key, d), p in zip(edges, preds):

            value = min(1.0, float(p) * d.get("demand_factor", 1.0))
            self.graph[u][v][key]["predicted_occupancy"] = value
            adjusted.append(value)
        preds = adjusted

        lo, hi = float(min(preds)), float(max(preds))
        return {
            "edges": len(edges),
            "min": round(lo, 4),
            "max": round(hi, 4),
            "mean": round(float(sum(preds) / len(preds)), 4),
            "spread": round(hi - lo, 4),
        }

    def load_spots(self) -> list[dict]:
        if self._spots is not None:
            return self._spots

        with open(BUNDLE_PATH, encoding="utf-8") as fh:
            bundle = json.load(fh)
        raw = [s for s in bundle["spots"] if s.get("status") == "installed"]

        lats = [s["lat"] for s in raw]
        lons = [s["lon"] for s in raw]
        edges = self.ox.distance.nearest_edges(self.graph, X=lons, Y=lats)

        out = []
        for spot, (u, v, key) in zip(raw, edges):
            out.append(
                {
                    "id": spot["id"],
                    "lat": spot["lat"],
                    "lon": spot["lon"],

                    "time_limit_hours": _duration_hours(spot.get("rule")),

                    "demand_factor": float(spot.get("demandFactor") or 1.0),
                }
            )
        self._spots = out
        print(f"[SPOT] {len(out)} places rattachees a une rue du graphe")
        return out

    def _load_grid(self) -> dict:
        if self._grid is None:
            with open(BUNDLE_PATH, encoding="utf-8") as fh:
                self._grid = json.load(fh)["occupancy"]
        return self._grid

    def predict_availability(self, now: datetime) -> list[dict]:
        spots = self.load_spots()

        if self.model is None:
            grid = self._load_grid()
            day, hour = now.weekday(), now.hour
            out = []
            for spot in spots:
                days = grid.get(spot["id"])
                if not days:
                    continue
                out.append({"id": spot["id"], "free": round(1.0 - days[day][hour], 4)})
            return out

        import pandas as pd

        base = time_features(now)
        rows = [
            {**base, "duree_max": duree_max_from_hours(s["time_limit_hours"])}
            for s in spots
        ]
        occ = self.model.predict_proba(pd.DataFrame(rows)[FEATURE_ORDER])[:, 1]
        out = []
        for spot, p in zip(spots, occ):

            value = min(1.0, float(p) * spot["demand_factor"])
            out.append({"id": spot["id"], "free": round(1.0 - value, 4)})
        return out

    def route(self, start_node: int, end_node: int, alpha: float):
        def weight(u, v, edge_dict):
            best = float("inf")
            for _, edge in edge_dict.items():
                dist = edge.get("length", 1.0)
                if alpha == 0:
                    cost = dist
                else:

                    occ = edge.get("predicted_occupancy", 0.5)
                    cost = dist * (1 + alpha * occ)
                if cost < best:
                    best = cost
            return best

        def heuristic(u, _v):
            return haversine_m(
                self.graph.nodes[u]["y"],
                self.graph.nodes[u]["x"],
                self.graph.nodes[end_node]["y"],
                self.graph.nodes[end_node]["x"],
            )

        try:
            return self.nx.astar_path(
                self.graph,
                source=start_node,
                target=end_node,
                heuristic=heuristic,
                weight=weight,
            )
        except (self.nx.NetworkXNoPath, self.nx.NodeNotFound):
            return None

    def nearest_node(self, lat: float, lon: float) -> int:
        return int(self.ox.distance.nearest_nodes(self.graph, X=lon, Y=lat))

    def path_geometry(
        self,
        path: list[int],
        origin: tuple[float, float] | None = None,
        destination: tuple[float, float] | None = None,
    ) -> tuple[list[list[float]], float, float]:
        pts = [[self.graph.nodes[n]["y"], self.graph.nodes[n]["x"]] for n in path]
        dist = 0.0
        occ_sum = 0.0
        for a, b in zip(path, path[1:]):
            best = min(self.graph[a][b].values(), key=lambda e: e.get("length", 1e9))
            dist += best.get("length", 0.0)
            occ_sum += best.get("predicted_occupancy", 0.5) * best.get("length", 0.0)

        if origin is not None and pts:
            gap = haversine_m(origin[0], origin[1], pts[0][0], pts[0][1])
            if gap > 5:
                pts.insert(0, [origin[0], origin[1]])
                dist += gap
        if destination is not None and pts:
            gap = haversine_m(destination[0], destination[1], pts[-1][0], pts[-1][1])
            if gap > 5:
                pts.append([destination[0], destination[1]])
                dist += gap

        return pts, round(dist, 1), round(occ_sum / dist, 4) if dist else 0.0

app = FastAPI(title="ZoPark Routing API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ROUTER: ZoParkRouter | None = None
LAST_STATS: dict[str, Any] = {}

@app.on_event("startup")
def startup() -> None:
    global ROUTER
    try:
        ROUTER = ZoParkRouter()
    except Exception as exc:
        print(f"[INIT] ECHEC : {exc}")
        print("[INIT] l'API repond quand meme ; /route renverra 503.")
        ROUTER = None

class RouteRequest(BaseModel):
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float

    alpha: float = 2.5

@app.get("/health")
def health() -> dict:
    if ROUTER is None:
        return {"status": "degraded", "reason": "routeur non initialise"}
    metrics = {}
    if os.path.exists(METRICS_PATH):
        with open(METRICS_PATH, encoding="utf-8") as fh:
            metrics = json.load(fh)
    return {
        "status": "ok",
        "nodes": ROUTER.graph.number_of_nodes(),
        "edges": ROUTER.graph.number_of_edges(),
        "model": metrics,
        "last_inference": LAST_STATS,
    }

@app.get("/availability")
def availability() -> dict:
    if ROUTER is None:
        raise HTTPException(503, "Routeur indisponible.")
    now = datetime.now()
    spots = ROUTER.predict_availability(now)
    free = [s["free"] for s in spots]
    return {
        "spots": spots,
        "generated_at": now.isoformat(timespec="seconds"),
        "weekday": now.weekday(),
        "hour": now.hour,
        "stats": {
            "count": len(spots),
            "min": round(min(free), 4) if free else 0,
            "max": round(max(free), 4) if free else 0,
            "mean": round(sum(free) / len(free), 4) if free else 0,
        },
    }

@app.post("/route")
def route(req: RouteRequest) -> dict:
    if ROUTER is None:
        raise HTTPException(503, "Routeur indisponible — verifie le modele et OSMnx.")

    global LAST_STATS
    LAST_STATS = ROUTER.update_occupancy(datetime.now())

    start = ROUTER.nearest_node(req.from_lat, req.from_lon)
    end = ROUTER.nearest_node(req.to_lat, req.to_lon)

    out: dict[str, Any] = {"inference": LAST_STATS}
    for label, alpha in (("classic", 0.0), ("zopark", req.alpha)):
        path = ROUTER.route(start, end, alpha)
        if path is None:
            out[label] = None
            continue
        pts, dist, occ = ROUTER.path_geometry(
            path,
            origin=(req.from_lat, req.from_lon),
            destination=(req.to_lat, req.to_lon),
        )
        out[label] = {
            "points": pts,
            "distance_m": dist,
            "avg_occupancy": occ,
            "nodes": len(path),
            "drive_minutes": max(1, round(dist / 1000 / 30 * 60)),
        }

    same = (
        out.get("classic")
        and out.get("zopark")
        and out["classic"]["points"] == out["zopark"]["points"]
    )
    out["routes_identical"] = bool(same)
    return out