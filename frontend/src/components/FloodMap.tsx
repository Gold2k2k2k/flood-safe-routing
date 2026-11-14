import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AdvancedMarker,
  APIProvider,
  Map,
  Pin,
  useMap,
  useMapsLibrary
} from "@vis.gl/react-google-maps";
import { envConfig } from "../config/env";
import {
  FloodInspectorCard,
  type SelectedMapEntity
} from "./FloodInspectorCard";
import { HeatmapOverlay } from "./HeatmapOverlay";
import type {
  CameraItem,
  CameraPollResultItem,
  FloodZoneItem,
  HeatmapPoint,
  LatLng,
  RouteResponse
} from "../types/flood";

export type MapClickMode = "origin" | "destination" | null;
type TileStyle = "voyager" | "dark";

interface FloodMapProps {
  origin: LatLng;
  destination: LatLng;
  clickMode: MapClickMode;
  onSelectCoordinate: (mode: "origin" | "destination", coord: LatLng) => void;
  zones: FloodZoneItem[];
  cameras: CameraItem[];
  routeResult: RouteResponse | null;
  heatmapPoints: HeatmapPoint[];
  showHeatmap: boolean;
  selectedEntity: SelectedMapEntity | null;
  onSelectEntity: (entity: SelectedMapEntity | null) => void;
  pollResultsByCamera: Record<string, CameraPollResultItem>;
  onResolveZone: (eventId: string) => void;
  onPollCamera: (cameraId: string) => void;
  resolvingId: string | null;
  pollingCameraId: string | null;
}

function MapCameraController({
  origin,
  destination,
  routeResult,
  onTilesReady
}: {
  origin: LatLng;
  destination: LatLng;
  routeResult: RouteResponse | null;
  onTilesReady: () => void;
}) {
  const map = useMap();
  const coreLib = useMapsLibrary("core");

  useEffect(() => {
    if (!map) return;
    const listener = map.addListener("tilesloaded", () => {
      onTilesReady();
    });
    return () => {
      listener.remove();
    };
  }, [map, onTilesReady]);

  useEffect(() => {
    if (!map || !coreLib) return;
    const bounds = new coreLib.LatLngBounds();
    bounds.extend(origin);
    bounds.extend(destination);
    if (routeResult) {
      routeResult.route_coordinates.forEach((pt) => bounds.extend(pt));
      routeResult.baseline_route_coordinates?.forEach((pt) => bounds.extend(pt));
    }
    map.fitBounds(bounds, 64);
  }, [map, coreLib, origin, destination, routeResult]);

  return null;
}

function FloodCirclesLayer({
  zones,
  onSelectZone
}: {
  zones: FloodZoneItem[];
  onSelectZone: (zone: FloodZoneItem) => void;
}) {
  const map = useMap();
  const mapsLib = useMapsLibrary("maps");

  useEffect(() => {
    if (!map || !mapsLib) return;
    const circles = zones.map((zone) => {
      const color = zone.severity_level >= 2 ? "#ef4444" : "#eab308";
      const circle = new mapsLib.Circle({
        map,
        center: { lat: zone.lat, lng: zone.lng },
        radius: zone.radius_meters,
        fillColor: color,
        fillOpacity: 0.32,
        strokeColor: color,
        strokeWeight: 2,
        clickable: true
      });
      circle.addListener("click", () => onSelectZone(zone));
      return circle;
    });

    return () => {
      circles.forEach((c) => c.setMap(null));
    };
  }, [map, mapsLib, zones, onSelectZone]);

  return null;
}

function RoutePolylineLayer({ routeResult }: { routeResult: RouteResponse | null }) {
  const map = useMap();
  const mapsLib = useMapsLibrary("maps");

  useEffect(() => {
    if (!map || !mapsLib || !routeResult) return;

    const overlays: google.maps.Polyline[] = [];

    if (
      routeResult.rerouted &&
      routeResult.baseline_route_coordinates &&
      routeResult.baseline_route_coordinates.length >= 2
    ) {
      const dashSymbol: google.maps.Symbol = {
        path: "M 0,-1 0,1",
        strokeOpacity: 0.95,
        scale: 3
      };
      overlays.push(
        new mapsLib.Polyline({
          map,
          path: routeResult.baseline_route_coordinates,
          strokeColor: "#ef4444",
          strokeOpacity: 0,
          strokeWeight: 3,
          icons: [{ icon: dashSymbol, offset: "0", repeat: "14px" }],
          zIndex: 4
        })
      );
    }

    if (routeResult.route_coordinates.length >= 2) {
      overlays.push(
        new mapsLib.Polyline({
          map,
          path: routeResult.route_coordinates,
          strokeColor: routeResult.rerouted ? "#22c55e" : "#3b82f6",
          strokeOpacity: 0.92,
          strokeWeight: 5,
          zIndex: 6
        })
      );
    }

    return () => {
      overlays.forEach((line) => line.setMap(null));
    };
  }, [map, mapsLib, routeResult]);

  return null;
}

const VIEW_WIDTH = 960;
const VIEW_HEIGHT = 640;
const TILE_SIZE = 256;

function latLngToWorldPx(lat: number, lng: number, zoom: number) {
  const scale = TILE_SIZE * Math.pow(2, zoom);
  const x = ((lng + 180) / 360) * scale;
  const clampedLat = Math.max(-85.05112878, Math.min(85.05112878, lat));
  const sinLat = Math.sin((clampedLat * Math.PI) / 180);
  const y = (0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI)) * scale;
  return { x, y };
}

function worldPxToLatLng(worldX: number, worldY: number, zoom: number): LatLng {
  const scale = TILE_SIZE * Math.pow(2, zoom);
  const lng = (worldX / scale) * 360 - 180;
  const n = Math.PI - (2 * Math.PI * worldY) / scale;
  const lat = (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
  return { lat, lng };
}

function computeFittedViewport(
  origin: LatLng,
  destination: LatLng,
  routeResult: RouteResponse | null
): { center: LatLng; zoom: number } {
  const points: LatLng[] = [origin, destination];
  if (routeResult) {
    points.push(...routeResult.route_coordinates);
    if (routeResult.baseline_route_coordinates) {
      points.push(...routeResult.baseline_route_coordinates);
    }
    if (routeResult.detour_waypoints_used) {
      points.push(...routeResult.detour_waypoints_used);
    }
  }

  const minLat = Math.min(...points.map((p) => p.lat));
  const maxLat = Math.max(...points.map((p) => p.lat));
  const minLng = Math.min(...points.map((p) => p.lng));
  const maxLng = Math.max(...points.map((p) => p.lng));

  const center = {
    lat: (minLat + maxLat) / 2,
    lng: (minLng + maxLng) / 2
  };

  for (let z = 16; z >= 11; z--) {
    const nw = latLngToWorldPx(maxLat, minLng, z);
    const se = latLngToWorldPx(minLat, maxLng, z);
    const spanW = Math.abs(se.x - nw.x);
    const spanH = Math.abs(se.y - nw.y);
    if (spanW <= VIEW_WIDTH * 0.68 && spanH <= VIEW_HEIGHT * 0.68) {
      return { center, zoom: z };
    }
  }

  return { center, zoom: 13 };
}

function tileUrl(style: TileStyle, zoom: number, x: number, y: number): string {
  if (style === "dark") {
    return `https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/${zoom}/${y}/${x}`;
  }
  return `https://tile.openstreetmap.org/${zoom}/${x}/${y}.png`;
}

function InteractiveOsmFallbackMap({
  origin,
  destination,
  clickMode,
  onSelectCoordinate,
  zones,
  cameras,
  routeResult,
  heatmapPoints,
  showHeatmap,
  onSelectEntity,
  pollResultsByCamera,
  fallbackReason,
  onRetryGoogleMaps
}: Pick<
  FloodMapProps,
  | "origin"
  | "destination"
  | "clickMode"
  | "onSelectCoordinate"
  | "zones"
  | "cameras"
  | "routeResult"
  | "heatmapPoints"
  | "showHeatmap"
  | "onSelectEntity"
  | "pollResultsByCamera"
> & {
  fallbackReason?: string | null;
  onRetryGoogleMaps?: () => void;
}) {
  const fitted = useMemo(
    () => computeFittedViewport(origin, destination, routeResult),
    [origin, destination, routeResult]
  );

  const [center, setCenter] = useState<LatLng>(fitted.center);
  const [zoom, setZoom] = useState<number>(fitted.zoom);
  const [tileStyle, setTileStyle] = useState<TileStyle>("voyager");
  const dragStateRef = useRef<{
    startClientX: number;
    startClientY: number;
    startWorldCenterX: number;
    startWorldCenterY: number;
    moved: boolean;
  } | null>(null);
  const suppressNextClickRef = useRef(false);

  useEffect(() => {
    setCenter(fitted.center);
    setZoom(fitted.zoom);
  }, [fitted.center.lat, fitted.center.lng, fitted.zoom]);

  const centerWorld = useMemo(
    () => latLngToWorldPx(center.lat, center.lng, zoom),
    [center.lat, center.lng, zoom]
  );
  const topLeftWorldX = centerWorld.x - VIEW_WIDTH / 2;
  const topLeftWorldY = centerWorld.y - VIEW_HEIGHT / 2;

  const toXY = (pt: LatLng) => {
    const w = latLngToWorldPx(pt.lat, pt.lng, zoom);
    return {
      x: w.x - topLeftWorldX,
      y: w.y - topLeftWorldY
    };
  };

  const metersToPx = (meters: number) => {
    const metersPerPx =
      (156543.03392 * Math.cos((center.lat * Math.PI) / 180)) / Math.pow(2, zoom);
    return Math.max(10, Math.min(120, meters / metersPerPx));
  };

  const visibleTiles = useMemo(() => {
    const maxIndex = Math.pow(2, zoom);
    const minTx = Math.floor(topLeftWorldX / TILE_SIZE);
    const maxTx = Math.floor((topLeftWorldX + VIEW_WIDTH) / TILE_SIZE);
    const minTy = Math.floor(topLeftWorldY / TILE_SIZE);
    const maxTy = Math.floor((topLeftWorldY + VIEW_HEIGHT) / TILE_SIZE);

    const tiles: Array<{ key: string; href: string; x: number; y: number }> = [];
    for (let ty = minTy; ty <= maxTy; ty++) {
      if (ty < 0 || ty >= maxIndex) continue;
      for (let tx = minTx; tx <= maxTx; tx++) {
        const wrappedTx = ((tx % maxIndex) + maxIndex) % maxIndex;
        tiles.push({
          key: `${tileStyle}-${zoom}-${tx}-${ty}`,
          href: tileUrl(tileStyle, zoom, wrappedTx, ty),
          x: tx * TILE_SIZE - topLeftWorldX,
          y: ty * TILE_SIZE - topLeftWorldY
        });
      }
    }
    return tiles;
  }, [tileStyle, zoom, topLeftWorldX, topLeftWorldY]);

  const handlePointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    const cw = latLngToWorldPx(center.lat, center.lng, zoom);
    dragStateRef.current = {
      startClientX: e.clientX,
      startClientY: e.clientY,
      startWorldCenterX: cw.x,
      startWorldCenterY: cw.y,
      moved: false
    };
  };

  const handlePointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const drag = dragStateRef.current;
    if (!drag) return;
    const rect = e.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const dxCss = e.clientX - drag.startClientX;
    const dyCss = e.clientY - drag.startClientY;
    if (Math.abs(dxCss) > 4 || Math.abs(dyCss) > 4) {
      drag.moved = true;
    }
    if (!drag.moved) return;
    const scaleX = VIEW_WIDTH / rect.width;
    const scaleY = VIEW_HEIGHT / rect.height;
    const nextCenter = worldPxToLatLng(
      drag.startWorldCenterX - dxCss * scaleX,
      drag.startWorldCenterY - dyCss * scaleY,
      zoom
    );
    setCenter(nextCenter);
  };

  const handlePointerUp = () => {
    if (dragStateRef.current?.moved) {
      suppressNextClickRef.current = true;
    }
    dragStateRef.current = null;
  };

  const handleSvgClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (suppressNextClickRef.current) {
      suppressNextClickRef.current = false;
      return;
    }
    if (!clickMode) return;
    const rect = e.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const svgX = ((e.clientX - rect.left) / rect.width) * VIEW_WIDTH;
    const svgY = ((e.clientY - rect.top) / rect.height) * VIEW_HEIGHT;
    const picked = worldPxToLatLng(topLeftWorldX + svgX, topLeftWorldY + svgY, zoom);
    onSelectCoordinate(clickMode, {
      lat: Number(picked.lat.toFixed(6)),
      lng: Number(picked.lng.toFixed(6))
    });
  };

  const baselinePointsAttr = (routeResult?.baseline_route_coordinates ?? [])
    .map((pt) => {
      const { x, y } = toXY(pt);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const activePointsAttr = (routeResult?.route_coordinates ?? [])
    .map((pt) => {
      const { x, y } = toXY(pt);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const originXY = toXY(origin);
  const destXY = toXY(destination);
  const isLightTiles = tileStyle === "voyager";

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        background: isLightTiles ? "#e2e8f0" : "#0b1120",
        overflow: "hidden",
        userSelect: "none"
      }}
    >
      <div
        style={{
          position: "absolute",
          top: "0.85rem",
          left: "0.85rem",
          zIndex: 10,
          background: "rgba(15, 23, 42, 0.9)",
          border: "1px solid #334155",
          borderRadius: "8px",
          padding: "0.45rem 0.7rem",
          fontSize: "0.75rem",
          color: "#e2e8f0",
          maxWidth: "460px"
        }}
      >
        <strong>OpenStreetMap Street View</strong>{" "}
        <span style={{ color: "#94a3b8" }}>
          ({fallbackReason || "Dùng nền đường phố thực tế khi không có Google Maps JS key"})
        </span>
      </div>

      <div
        style={{
          position: "absolute",
          top: "0.85rem",
          right: "0.85rem",
          zIndex: 10,
          display: "flex",
          flexWrap: "wrap",
          gap: "0.35rem"
        }}
      >
        {onRetryGoogleMaps && (
          <button
            type="button"
            onClick={onRetryGoogleMaps}
            style={{
              padding: "0.35rem 0.6rem",
              borderRadius: "6px",
              border: "1px solid #3b82f6",
              background: "rgba(15, 23, 42, 0.92)",
              color: "#93c5fd",
              cursor: "pointer",
              fontSize: "0.75rem"
            }}
          >
            Thử Google Maps
          </button>
        )}
        <button
          type="button"
          onClick={() => setTileStyle((s) => (s === "voyager" ? "dark" : "voyager"))}
          style={{
            padding: "0.35rem 0.6rem",
            borderRadius: "6px",
            border: "1px solid #334155",
            background: "rgba(15, 23, 42, 0.92)",
            color: "#f8fafc",
            cursor: "pointer",
            fontSize: "0.75rem"
          }}
        >
          {isLightTiles ? "🌙 Nền tối" : "☀️ Nền phố"}
        </button>
        <button
          type="button"
          onClick={() => setZoom((z) => Math.min(18, z + 1))}
          style={{
            padding: "0.35rem 0.65rem",
            borderRadius: "6px",
            border: "1px solid #334155",
            background: "rgba(15, 23, 42, 0.92)",
            color: "#f8fafc",
            cursor: "pointer"
          }}
          title="Phóng to"
        >
          +
        </button>
        <button
          type="button"
          onClick={() => setZoom((z) => Math.max(10, z - 1))}
          style={{
            padding: "0.35rem 0.65rem",
            borderRadius: "6px",
            border: "1px solid #334155",
            background: "rgba(15, 23, 42, 0.92)",
            color: "#f8fafc",
            cursor: "pointer"
          }}
          title="Thu nhỏ"
        >
          −
        </button>
        <button
          type="button"
          onClick={() => {
            setCenter(fitted.center);
            setZoom(fitted.zoom);
          }}
          style={{
            padding: "0.35rem 0.6rem",
            borderRadius: "6px",
            border: "1px solid #334155",
            background: "rgba(15, 23, 42, 0.92)",
            color: "#f8fafc",
            cursor: "pointer",
            fontSize: "0.75rem"
          }}
        >
          Fit tuyến
        </button>
      </div>

      <svg
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        preserveAspectRatio="xMidYMid slice"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        onClick={handleSvgClick}
        style={{
          width: "100%",
          height: "100%",
          display: "block",
          touchAction: "none",
          cursor: clickMode ? "crosshair" : "grab"
        }}
      >
        <defs>
          <radialGradient id="heatBlob" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(239, 68, 68, 0.7)" />
            <stop offset="55%" stopColor="rgba(249, 115, 22, 0.4)" />
            <stop offset="100%" stopColor="rgba(249, 115, 22, 0)" />
          </radialGradient>
        </defs>

        {/* Base fallback canvas + real Carto/OSM Slippy Street Tiles */}
        <rect
          x={0}
          y={0}
          width={VIEW_WIDTH}
          height={VIEW_HEIGHT}
          fill={isLightTiles ? "#cbd5e1" : "#0b1120"}
        />
        {visibleTiles.map((tile) => (
          <image
            key={tile.key}
            href={tile.href}
            x={tile.x}
            y={tile.y}
            width={TILE_SIZE}
            height={TILE_SIZE}
            preserveAspectRatio="none"
          />
        ))}

        {/* Historical Flood Heatmap Layer */}
        {showHeatmap &&
          heatmapPoints.map((pt, i) => {
            const { x, y } = toXY(pt);
            const r = 30 + pt.weight * 28;
            return <circle key={`heat-${i}`} cx={x} cy={y} r={r} fill="url(#heatBlob)" />;
          })}

        {/* Flood Zones */}
        {zones.map((z) => {
          const { x, y } = toXY(z);
          if (x < -140 || x > VIEW_WIDTH + 140 || y < -140 || y > VIEW_HEIGHT + 140) return null;
          const r = metersToPx(z.radius_meters);
          const color = z.severity_level >= 2 ? "#dc2626" : "#ca8a04";
          return (
            <g
              key={z.event_id}
              style={{ cursor: "pointer" }}
              onClick={(ev) => {
                if (clickMode) return;
                ev.stopPropagation();
                onSelectEntity({ kind: "zone", zone: z });
              }}
            >
              <circle
                cx={x}
                cy={y}
                r={r}
                fill={color}
                fillOpacity={0.32}
                stroke={color}
                strokeWidth={2.5}
              />
              <circle cx={x} cy={y} r={8} fill={color} stroke="#ffffff" strokeWidth={2} />
              <text
                x={x}
                y={y - r - 6}
                textAnchor="middle"
                fill={isLightTiles ? "#7f1d1d" : "#fecaca"}
                stroke={isLightTiles ? "#ffffff" : "#0f172a"}
                strokeWidth={3}
                paintOrder="stroke"
                fontSize={11}
                fontWeight={700}
              >
                {z.location_name || z.event_id} (M{z.severity_level})
              </text>
            </g>
          );
        })}

        {/* Baseline Blocked Route (Red Dashed) */}
        {routeResult?.rerouted && baselinePointsAttr && (
          <polyline
            points={baselinePointsAttr}
            fill="none"
            stroke="#dc2626"
            strokeWidth={4}
            strokeDasharray="10 7"
            strokeLinecap="round"
            strokeOpacity={0.95}
          />
        )}

        {/* Active Safe / Detour Route */}
        {activePointsAttr && (
          <>
            <polyline
              points={activePointsAttr}
              fill="none"
              stroke="#ffffff"
              strokeWidth={8.5}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeOpacity={0.85}
            />
            <polyline
              points={activePointsAttr}
              fill="none"
              stroke={routeResult?.rerouted ? "#16a34a" : "#2563eb"}
              strokeWidth={5.5}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeOpacity={0.98}
            />
          </>
        )}

        {/* Detour Via Waypoints */}
        {routeResult?.detour_waypoints_used?.map((wp, idx) => {
          const { x, y } = toXY(wp);
          return (
            <g key={`via-${idx}`}>
              <rect
                x={x - 6}
                y={y - 6}
                width={12}
                height={12}
                transform={`rotate(45 ${x} ${y})`}
                fill="#16a34a"
                stroke="#ffffff"
                strokeWidth={2}
              />
            </g>
          );
        })}

        {/* Cameras */}
        {cameras.map((cam) => {
          const { x, y } = toXY(cam);
          if (x < -40 || x > VIEW_WIDTH + 40 || y < -40 || y > VIEW_HEIGHT + 40) return null;
          return (
            <g
              key={cam.camera_id}
              style={{ cursor: "pointer" }}
              onClick={(ev) => {
                if (clickMode) return;
                ev.stopPropagation();
                onSelectEntity({
                  kind: "camera",
                  camera: cam,
                  pollResult: pollResultsByCamera[cam.camera_id]
                });
              }}
            >
              <circle cx={x} cy={y} r={9} fill="#0284c7" stroke="#ffffff" strokeWidth={2.5} />
              <text x={x} y={y + 3.5} textAnchor="middle" fill="#ffffff" fontSize={10} fontWeight={700}>
                C
              </text>
            </g>
          );
        })}

        {/* Origin A & Destination B */}
        <g>
          <circle cx={originXY.x} cy={originXY.y} r={12} fill="#2563eb" stroke="#ffffff" strokeWidth={2.5} />
          <text x={originXY.x} y={originXY.y + 4} textAnchor="middle" fill="#ffffff" fontSize={11} fontWeight={700}>
            A
          </text>
        </g>
        <g>
          <circle cx={destXY.x} cy={destXY.y} r={12} fill="#16a34a" stroke="#ffffff" strokeWidth={2.5} />
          <text x={destXY.x} y={destXY.y + 4} textAnchor="middle" fill="#ffffff" fontSize={11} fontWeight={700}>
            B
          </text>
        </g>
      </svg>

      {/* Legend & OSM attribution */}
      <div
        style={{
          position: "absolute",
          left: "0.85rem",
          bottom: "0.85rem",
          zIndex: 10,
          background: "rgba(15, 23, 42, 0.92)",
          border: "1px solid #334155",
          borderRadius: "8px",
          padding: "0.45rem 0.75rem",
          fontSize: "0.72rem",
          color: "#cbd5e1",
          display: "flex",
          flexWrap: "wrap",
          gap: "0.65rem"
        }}
      >
        <span>🔵 A → 🟢 B</span>
        <span>
          <span style={{ color: "#22c55e" }}>━━</span> Tuyến an toàn
        </span>
        <span>
          <span style={{ color: "#ef4444" }}>╌╌</span> Tuyến cũ bị ngập
        </span>
        <span>🔴 Vùng ngập (bấm xem AI)</span>
        <span>🔹 Camera (C)</span>
        <span style={{ color: "#94a3b8" }}>© OpenStreetMap contributors • Esri</span>
      </div>
    </div>
  );
}

export function FloodMap(props: FloodMapProps) {
  const {
    origin,
    destination,
    clickMode,
    onSelectCoordinate,
    zones,
    cameras,
    routeResult,
    heatmapPoints,
    showHeatmap,
    selectedEntity,
    onSelectEntity,
    pollResultsByCamera,
    onResolveZone,
    onPollCamera,
    resolvingId,
    pollingCameraId
  } = props;

  const [preferFallbackMap, setPreferFallbackMap] = useState(false);
  const [fallbackReason, setFallbackReason] = useState<string | null>(null);
  const googleTilesLoadedRef = useRef(false);

  useEffect(() => {
    if (!envConfig.hasGoogleMapsKey || preferFallbackMap) return;
    googleTilesLoadedRef.current = false;

    const win = window as unknown as { gm_authFailure?: () => void };
    const prevAuthFailure = win.gm_authFailure;
    win.gm_authFailure = () => {
      setFallbackReason("Google Maps API key lỗi xác thực/Billing — tự động chuyển sang OSM Street View");
      setPreferFallbackMap(true);
      prevAuthFailure?.();
    };

    const timer = window.setTimeout(() => {
      if (!googleTilesLoadedRef.current) {
        setFallbackReason("Google Maps không tải được tile — tự động chuyển sang OSM Street View");
        setPreferFallbackMap(true);
      }
    }, 5500);

    return () => {
      win.gm_authFailure = prevAuthFailure;
      window.clearTimeout(timer);
    };
  }, [preferFallbackMap]);

  const useOsmFallback = !envConfig.hasGoogleMapsKey || preferFallbackMap;

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", minHeight: "420px" }}>
      {clickMode && (
        <div
          style={{
            position: "absolute",
            top: "0.85rem",
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 25,
            background: "#2563eb",
            color: "#ffffff",
            padding: "0.45rem 0.9rem",
            borderRadius: "999px",
            fontSize: "0.8rem",
            fontWeight: 600,
            boxShadow: "0 8px 20px rgba(0,0,0,0.4)"
          }}
        >
          Chạm lên bản đồ để chọn {clickMode === "origin" ? "Điểm đi (A)" : "Điểm đến (B)"}
        </div>
      )}

      {useOsmFallback ? (
        <InteractiveOsmFallbackMap
          origin={origin}
          destination={destination}
          clickMode={clickMode}
          onSelectCoordinate={onSelectCoordinate}
          zones={zones}
          cameras={cameras}
          routeResult={routeResult}
          heatmapPoints={heatmapPoints}
          showHeatmap={showHeatmap}
          onSelectEntity={onSelectEntity}
          pollResultsByCamera={pollResultsByCamera}
          fallbackReason={fallbackReason}
          onRetryGoogleMaps={
            envConfig.hasGoogleMapsKey
              ? () => {
                  setFallbackReason(null);
                  setPreferFallbackMap(false);
                }
              : undefined
          }
        />
      ) : (
        <div style={{ position: "absolute", inset: 0 }}>
          <button
            type="button"
            onClick={() => {
              setFallbackReason("Chế độ xem OpenStreetMap theo yêu cầu");
              setPreferFallbackMap(true);
            }}
            style={{
              position: "absolute",
              top: "0.85rem",
              right: "0.85rem",
              zIndex: 15,
              padding: "0.38rem 0.65rem",
              borderRadius: "6px",
              border: "1px solid #334155",
              background: "rgba(15, 23, 42, 0.9)",
              color: "#e2e8f0",
              cursor: "pointer",
              fontSize: "0.75rem"
            }}
          >
            Đổi sang OSM Street Map
          </button>

          <APIProvider
            apiKey={envConfig.googleMapsApiKey}
            libraries={["geometry", "places"]}
            onError={() => {
              setFallbackReason("Không nạp được Google Maps JS SDK — chuyển sang OSM Street View");
              setPreferFallbackMap(true);
            }}
          >
            <Map
              defaultCenter={origin}
              defaultZoom={14}
              mapId="DEMO_MAP_ID"
              style={{ width: "100%", height: "100%" }}
              onClick={(ev) => {
                if (!clickMode || !ev.detail.latLng) return;
                onSelectCoordinate(clickMode, {
                  lat: ev.detail.latLng.lat,
                  lng: ev.detail.latLng.lng
                });
              }}
            >
              <MapCameraController
                origin={origin}
                destination={destination}
                routeResult={routeResult}
                onTilesReady={() => {
                  googleTilesLoadedRef.current = true;
                }}
              />
              <FloodCirclesLayer
                zones={zones}
                onSelectZone={(z) => onSelectEntity({ kind: "zone", zone: z })}
              />
              <RoutePolylineLayer routeResult={routeResult} />
              <HeatmapOverlay visible={showHeatmap} points={heatmapPoints} />

              <AdvancedMarker position={origin} title="Điểm đi (A)">
                <Pin background="#2563eb" borderColor="#ffffff" glyphColor="#ffffff" glyph="A" />
              </AdvancedMarker>
              <AdvancedMarker position={destination} title="Điểm đến (B)">
                <Pin background="#16a34a" borderColor="#ffffff" glyphColor="#ffffff" glyph="B" />
              </AdvancedMarker>

              {routeResult?.detour_waypoints_used?.map((wp, idx) => (
                <AdvancedMarker key={`detour-${idx}`} position={wp} title={`Điểm vòng an toàn #${idx + 1}`}>
                  <Pin background="#22c55e" borderColor="#052e16" glyphColor="#ffffff" scale={0.78} />
                </AdvancedMarker>
              ))}

              {zones.map((z) => (
                <AdvancedMarker
                  key={z.event_id}
                  position={{ lat: z.lat, lng: z.lng }}
                  title={`${z.location_name || z.event_id} (Mức ${z.severity_level})`}
                  onClick={() => onSelectEntity({ kind: "zone", zone: z })}
                >
                  <Pin
                    background={z.severity_level >= 2 ? "#ef4444" : "#eab308"}
                    borderColor="#ffffff"
                    glyphColor="#ffffff"
                  />
                </AdvancedMarker>
              ))}

              {cameras.map((cam) => (
                <AdvancedMarker
                  key={cam.camera_id}
                  position={{ lat: cam.lat, lng: cam.lng }}
                  title={`Camera: ${cam.name}`}
                  onClick={() =>
                    onSelectEntity({
                      kind: "camera",
                      camera: cam,
                      pollResult: pollResultsByCamera[cam.camera_id]
                    })
                  }
                >
                  <Pin background="#0284c7" borderColor="#ffffff" glyphColor="#ffffff" glyph="C" />
                </AdvancedMarker>
              ))}
            </Map>
          </APIProvider>
        </div>
      )}

      <FloodInspectorCard
        selected={selectedEntity}
        onClose={() => onSelectEntity(null)}
        onResolveZone={onResolveZone}
        onPollCamera={onPollCamera}
        resolvingId={resolvingId}
        pollingCameraId={pollingCameraId}
      />
    </div>
  );
}
