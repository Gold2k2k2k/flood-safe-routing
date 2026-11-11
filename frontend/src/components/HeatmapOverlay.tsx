import { useEffect } from "react";
import { useMap, useMapsLibrary } from "@vis.gl/react-google-maps";
import type { HeatmapPoint } from "../types/flood";

interface HeatmapOverlayProps {
  visible: boolean;
  points: HeatmapPoint[];
}

/**
 * Maps JS API v3.65+ compatible Thermal Heatmap Overlay using google.maps.OverlayView + HTML5 Canvas.
 * Google deprecated and removed google.maps.visualization.HeatmapLayer in Maps JS API v3.65;
 * this viewport-bounded Canvas Overlay renders smooth weighted thermal blobs with zero extra deps.
 */
export function HeatmapOverlay({ visible, points }: HeatmapOverlayProps) {
  const map = useMap();
  const mapsLib = useMapsLibrary("maps");

  useEffect(() => {
    if (!map || !mapsLib || !visible || points.length === 0) {
      return;
    }

    const maxWeight = Math.max(
      1,
      ...points.map((pt) => pt.weight || pt.flood_frequency_30d * pt.avg_severity)
    );

    class ThermalCanvasOverlay extends google.maps.OverlayView {
      private canvas: HTMLCanvasElement | null = null;

      onAdd(): void {
        const canvas = document.createElement("canvas");
        canvas.style.position = "absolute";
        canvas.style.pointerEvents = "none";
        this.canvas = canvas;
        const panes = this.getPanes();
        panes?.overlayLayer.appendChild(canvas);
      }

      draw(): void {
        const canvas = this.canvas;
        const projection = this.getProjection();
        const bounds = map?.getBounds();
        if (!canvas || !projection || !bounds) return;

        const sw = projection.fromLatLngToDivPixel(bounds.getSouthWest());
        const ne = projection.fromLatLngToDivPixel(bounds.getNorthEast());
        if (!sw || !ne) return;

        const radiusPx = 56;
        const left = Math.floor(Math.min(sw.x, ne.x)) - radiusPx;
        const top = Math.floor(Math.min(ne.y, sw.y)) - radiusPx;
        const width = Math.max(1, Math.ceil(Math.abs(ne.x - sw.x)) + radiusPx * 2);
        const height = Math.max(1, Math.ceil(Math.abs(sw.y - ne.y)) + radiusPx * 2);

        canvas.style.left = `${left}px`;
        canvas.style.top = `${top}px`;
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        canvas.width = width;
        canvas.height = height;

        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        ctx.clearRect(0, 0, width, height);

        for (const pt of points) {
          const px = projection.fromLatLngToDivPixel(new google.maps.LatLng(pt.lat, pt.lng));
          if (!px) continue;
          const cx = px.x - left;
          const cy = px.y - top;
          if (cx < -radiusPx || cy < -radiusPx || cx > width + radiusPx || cy > height + radiusPx) {
            continue;
          }
          const weight = pt.weight || pt.flood_frequency_30d * pt.avg_severity;
          const intensity = Math.min(1, Math.max(0.25, weight / maxWeight));
          const grad = ctx.createRadialGradient(cx, cy, 4, cx, cy, radiusPx);
          grad.addColorStop(0, `rgba(239, 68, 68, ${0.72 * intensity})`);
          grad.addColorStop(0.45, `rgba(245, 158, 11, ${0.45 * intensity})`);
          grad.addColorStop(1, "rgba(234, 179, 8, 0)");
          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.arc(cx, cy, radiusPx, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      onRemove(): void {
        if (this.canvas?.parentNode) {
          this.canvas.parentNode.removeChild(this.canvas);
        }
        this.canvas = null;
      }
    }

    const overlay = new ThermalCanvasOverlay();
    overlay.setMap(map);

    return () => {
      overlay.setMap(null);
    };
  }, [map, mapsLib, visible, points]);

  return null;
}
