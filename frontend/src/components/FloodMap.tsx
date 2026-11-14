import React, { useEffect, useMemo, useState } from "react";
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
  routeResult
}: {
  origin: LatLng;
  destination: LatLng;
  routeResult: RouteResponse | null;
}) {
  const map = useMap();
  const coreLib = useMapsLibrary("core");

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

const SVG_WIDTH = 960;
const SVG_HEIGHT = 640;

interface BoundsBox {
  minLat: number;
  maxLat: number;
  minLng: number;
  maxLng: number;
}

function computeLocalBounds(
  origin: LatLng,
  destination: LatLng,
  routeResult: RouteResponse | null,
  zones: FloodZoneItem[],
  cameras: CameraItem[],
  zoomMultiplier: number
): BoundsBox {
  const focusPoints: LatLng[] = [origin, destination];
  if (routeResult) {
    focusPoints.push(...routeResult.route_coordinates);
    if (routeResult.baseline_route_coordinates) {
      focusPoints.push(...routeResult.baseline_route_coordinates);
    }
    if (routeResult.detour_waypoints_used) {
      focusPoints.push(...routeResult.detour_waypoints_used);
    }
  }

  const centerLat = focusPoints.reduce((acc, p) => acc + p.lat, 0) / focusPoints.length;
  const centerLng = focusPoints.reduce((acc, p) => acc + p.lng, 0) / focusPoints.length;

  // Include zones & cameras in the same city cluster (~0.18 deg) so Vietnam-wide points don't flatten local street zoom
  const localClusterMarginDeg = 0.18;
  zones.forEach((z) => {
    if (
      Math.abs(z.lat - centerLat) <= localClusterMarginDeg &&
      Math.abs(z.lng - centerLng) <= localClusterMarginDeg
    ) {
      focusPoints.push({ lat: z.lat, lng: z.lng });
    }
  });
  cameras.forEach((c) => {
    if (
      Math.abs(c.lat - centerLat) <= localClusterMarginDeg &&
      Math.abs(c.lng - centerLng) <= localClusterMarginDeg
    ) {
      focusPoints.push({ lat: c.lat, lng: c.lng });
    }
  });

  let minLat = Math.min(...focusPoints.map((p) => p.lat));
  let maxLat = Math.max(...focusPoints.map((p) => p.lat));
  let minLng = Math.min(...focusPoints.map((p) => p.lng));
  let maxLng = Math.max(...focusPoints.map((p) => p.lng));

  const spanLat = Math.max(0.014, maxLat - minLat);
  const spanLng = Math.max(0.018, maxLng - minLng);

  // Maintain SVG aspect ratio cleanly without squashing map angles
  const cosLat = Math.max(0.4, Math.cos((centerLat * Math.PI) / 180));
  const paddedLatHalf = (spanLat * 0.72) * zoomMultiplier;
  const targetRatio = SVG_WIDTH / SVG_HEIGHT;
  const minLngHalfFromRatio = (paddedLatHalf * targetRatio) / cosLat;
  const paddedLngHalf = Math.max((spanLng * 0.72) * zoomMultiplier, minLngHalfFromRatio);
  const finalLatHalf = Math.max(paddedLatHalf, (paddedLngHalf * cosLat) / targetRatio);

  const midLat = (minLat + maxLat) / 2;
  const midLng = (minLng + maxLng) / 2;

  return {
    minLat: midLat - finalLatHalf,
    maxLat: midLat + finalLatHalf,
    minLng: midLng - paddedLngHalf,
    maxLng: midLng + paddedLngHalf
  };
}

function SvgVectorFallbackMap({
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
  pollResultsByCamera
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
>) {
  const [zoomMultiplier, setZoomMultiplier] = useState(1);

  const bounds = useMemo(
    () => computeLocalBounds(origin, destination, routeResult, zones, cameras, zoomMultiplier),
    [origin, destination, routeResult, zones, cameras, zoomMultiplier]
  );

  const toXY = (pt: LatLng) => {
    const x = ((pt.lng - bounds.minLng) / (bounds.maxLng - bounds.minLng)) * SVG_WIDTH;
    const y = ((bounds.maxLat - pt.lat) / (bounds.maxLat - bounds.minLat)) * SVG_HEIGHT;
    return { x, y };
  };

  const metersToSvgRadius = (meters: number) => {
    const degLat = meters / 111320;
    const px = (degLat / (bounds.maxLat - bounds.minLat)) * SVG_HEIGHT;
    return Math.max(8, Math.min(90, px));
  };

  const handleSvgClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!clickMode) return;
    const rect = e.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const relX = (e.clientX - rect.left) / rect.width;
    const relY = (e.clientY - rect.top) / rect.height;
    const lng = bounds.minLng + relX * (bounds.maxLng - bounds.minLng);
    const lat = bounds.maxLat - relY * (bounds.maxLat - bounds.minLat);
    onSelectCoordinate(clickMode, {
      lat: Number(lat.toFixed(6)),
      lng: Number(lng.toFixed(6))
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

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", background: "#0b1120", overflow: "hidden" }}>
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
          color: "#cbd5e1"
        }}
      >
        <strong>Interactive Vector Map</strong> (Fallback khi không có{" "}
        <code>VITE_GOOGLE_MAPS_API_KEY</code>)
      </div>

      <div
        style={{
          position: "absolute",
          top: "0.85rem",
          right: "0.85rem",
          zIndex: 10,
          display: "flex",
          gap: "0.35rem"
        }}
      >
        <button
          type="button"
          onClick={() => setZoomMultiplier((z) => Math.max(0.35, z * 0.78))}
          style={{
            padding: "0.35rem 0.6rem",
            borderRadius: "6px",
            border: "1px solid #334155",
            background: "#1e293b",
            color: "#f8fafc",
            cursor: "pointer"
          }}
          title="Phóng to"
        >
          +
        </button>
        <button
          type="button"
          onClick={() => setZoomMultiplier((z) => Math.min(2.8, z * 1.28))}
          style={{
            padding: "0.35rem 0.6rem",
            borderRadius: "6px",
            border: "1px solid #334155",
            background: "#1e293b",
            color: "#f8fafc",
            cursor: "pointer"
          }}
          title="Thu nhỏ"
        >
          −
        </button>
        <button
          type="button"
          onClick={() => setZoomMultiplier(1)}
          style={{
            padding: "0.35rem 0.6rem",
            borderRadius: "6px",
            border: "1px solid #334155",
            background: "#1e293b",
            color: "#f8fafc",
            cursor: "pointer",
            fontSize: "0.75rem"
          }}
        >
          Fit tuyến
        </button>
      </div>

      <svg
        viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
        preserveAspectRatio="xMidYMid slice"
        onClick={handleSvgClick}
        style={{
          width: "100%",
          height: "100%",
          display: "block",
          cursor: clickMode ? "crosshair" : "default"
        }}
      >
        <defs>
          <radialGradient id="heatBlob" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(239, 68, 68, 0.65)" />
            <stop offset="55%" stopColor="rgba(249, 115, 22, 0.35)" />
            <stop offset="100%" stopColor="rgba(249, 115, 22, 0)" />
          </radialGradient>
        </defs>

        {/* Background grid resembling urban blocks */}
        <rect x={0} y={0} width={SVG_WIDTH} height={SVG_HEIGHT} fill="#0b1120" />
        {Array.from({ length: 16 }).map((_, idx) => {
          const x = (SVG_WIDTH / 16) * idx;
          return <line key={`vx-${idx}`} x1={x} y1={0} x2={x} y2={SVG_HEIGHT} stroke="#162033" strokeWidth={1} />;
        })}
        {Array.from({ length: 10 }).map((_, idx) => {
          const y = (SVG_HEIGHT / 10) * idx;
          return <line key={`hy-${idx}`} x1={0} y1={y} x2={SVG_WIDTH} y2={y} stroke="#162033" strokeWidth={1} />;
        })}

        {/* Historical Flood Heatmap Layer */}
        {showHeatmap &&
          heatmapPoints.map((pt, i) => {
            const { x, y } = toXY(pt);
            const r = 34 + pt.weight * 32;
            return <circle key={`heat-${i}`} cx={x} cy={y} r={r} fill="url(#heatBlob)" />;
          })}

        {/* Flood Zones */}
        {zones.map((z) => {
          const { x, y } = toXY(z);
          const r = metersToSvgRadius(z.radius_meters);
          const color = z.severity_level >= 2 ? "#ef4444" : "#eab308";
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
                fillOpacity={0.28}
                stroke={color}
                strokeWidth={2}
              />
              <circle cx={x} cy={y} r={7} fill={color} stroke="#ffffff" strokeWidth={2} />
              <text
                x={x}
                y={y - r - 6}
                textAnchor="middle"
                fill="#fca5a5"
                fontSize={11}
                fontWeight={600}
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
            stroke="#ef4444"
            strokeWidth={3.5}
            strokeDasharray="10 7"
            strokeLinecap="round"
            strokeOpacity={0.92}
          />
        )}

        {/* Active Safe / Detour Route */}
        {activePointsAttr && (
          <polyline
            points={activePointsAttr}
            fill="none"
            stroke={routeResult?.rerouted ? "#22c55e" : "#3b82f6"}
            strokeWidth={5.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeOpacity={0.95}
          />
        )}

        {/* Detour Via Waypoints */}
        {routeResult?.detour_waypoints_used?.map((wp, idx) => {
          const { x, y } = toXY(wp);
          return (
            <g key={`via-${idx}`}>
              <rect
                x={x - 5}
                y={y - 5}
                width={10}
                height={10}
                transform={`rotate(45 ${x} ${y})`}
                fill="#22c55e"
                stroke="#ffffff"
                strokeWidth={1.5}
              />
            </g>
          );
        })}

        {/* Cameras */}
        {cameras.map((cam) => {
          const { x, y } = toXY(cam);
          if (x < -40 || x > SVG_WIDTH + 40 || y < -40 || y > SVG_HEIGHT + 40) return null;
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
              <circle cx={x} cy={y} r={8} fill="#0284c7" stroke="#ffffff" strokeWidth={2} />
              <text x={x} y={y + 3.5} textAnchor="middle" fill="#ffffff" fontSize={9} fontWeight={700}>
                C
              </text>
            </g>
          );
        })}

        {/* Origin A & Destination B */}
        <g>
          <circle cx={originXY.x} cy={originXY.y} r={11} fill="#2563eb" stroke="#ffffff" strokeWidth={2.5} />
          <text x={originXY.x} y={originXY.y + 4} textAnchor="middle" fill="#ffffff" fontSize={11} fontWeight={700}>
            A
          </text>
        </g>
        <g>
          <circle cx={destXY.x} cy={destXY.y} r={11} fill="#16a34a" stroke="#ffffff" strokeWidth={2.5} />
          <text x={destXY.x} y={destXY.y + 4} textAnchor="middle" fill="#ffffff" fontSize={11} fontWeight={700}>
            B
          </text>
        </g>
      </svg>

      {/* Legend */}
      <div
        style={{
          position: "absolute",
          left: "0.85rem",
          bottom: "0.85rem",
          zIndex: 10,
          background: "rgba(15, 23, 42, 0.9)",
          border: "1px solid #334155",
          borderRadius: "8px",
          padding: "0.5rem 0.75rem",
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

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
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

      {!envConfig.hasGoogleMapsKey ? (
        <SvgVectorFallbackMap
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
        />
      ) : (
        <APIProvider apiKey={envConfig.googleMapsApiKey} libraries={["geometry", "places"]}>
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
            <MapCameraController origin={origin} destination={destination} routeResult={routeResult} />
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
