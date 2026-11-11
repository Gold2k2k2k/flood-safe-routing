# Deep Reference: Google Maps JS API (`@vis.gl/react-google-maps`) & Firebase Real-time Sync

This document specifies verified frontend integration patterns for **Google Maps JavaScript API**, **`HeatmapLayer`**, **Firebase v10 Modular Firestore (`onSnapshot`)**, and automatic **Live Rerouting** on the client.

---

## 1. `@vis.gl/react-google-maps` Setup & Map Libraries

### Provider & Map Container
Always load `visualization`, `geometry`, and `places` upfront on `<APIProvider>` so `HeatmapLayer` and polyline utilities are available cleanly. Remember that `<AdvancedMarker>` requires a `mapId` (for rapid hackathon demos without a custom Cloud Map Style ID, you can use Google's documented demo Map ID `"DEMO_MAP_ID"`).

```tsx
import {
  APIProvider,
  Map,
  AdvancedMarker,
  Pin,
  Polyline,
  Circle,
  useMap,
  useMapsLibrary
} from "@vis.gl/react-google-maps";
```

> **Version Resilience Note:** If a pinned minor version or wrapper does not export `<Polyline>` / `<Circle>` directly, or if you need fine-grained imperative control over `setPath` / `setMap(null)`, instantiate `google.maps.Polyline` and `google.maps.Circle` inside `useEffect` using `const map = useMap()` and `const mapsLib = useMapsLibrary("maps")`.

### Declarative Camera Markers & Red Flood Circles

```tsx
{zones.map((zone) => {
  const isBlocked = zone.severity_level >= 2;
  const color = isBlocked ? "#ef4444" : "#eab308";
  return (
    <React.Fragment key={zone.event_id}>
      <Circle
        center={{ lat: zone.lat, lng: zone.lng }}
        radius={zone.radius_meters}
        fillColor={color}
        fillOpacity={0.32}
        strokeColor={color}
        strokeWeight={2}
      />
      <AdvancedMarker
        position={{ lat: zone.lat, lng: zone.lng }}
        title={`${zone.location_name ?? zone.event_id} (Level ${zone.severity_level})`}
      >
        <Pin
          background={color}
          borderColor="#ffffff"
          glyphColor="#ffffff"
        />
      </AdvancedMarker>
    </React.Fragment>
  );
})}
```

---

## 2. `HeatmapLayer` Pattern (`useMapsLibrary('visualization')`)

`HeatmapLayer` is not a built-in React component in `@vis.gl/react-google-maps`. Load it via `useMapsLibrary("visualization")` and bind it to `useMap()`, taking care to clean up with `heatmap.setMap(null)` on toggle/unmount to prevent duplicate stacked layers on re-render.

```tsx
import { useEffect, useMemo } from "react";
import { useMap, useMapsLibrary } from "@vis.gl/react-google-maps";
import type { HeatmapPoint } from "../types/flood";

interface FloodHeatmapLayerProps {
  visible: boolean;
  points: HeatmapPoint[];
}

export function FloodHeatmapLayer({ visible, points }: FloodHeatmapLayerProps) {
  const map = useMap();
  const visualizationLib = useMapsLibrary("visualization");

  const weightedLocations = useMemo(() => {
    if (!visualizationLib || !points.length) return [];
    return points.map((pt) => ({
      location: new google.maps.LatLng(pt.lat, pt.lng),
      weight: pt.weight || pt.flood_frequency_30d * pt.avg_severity
    }));
  }, [visualizationLib, points]);

  useEffect(() => {
    if (!visualizationLib || !map || !visible || weightedLocations.length === 0) {
      return;
    }

    const heatmap = new visualizationLib.HeatmapLayer({
      data: weightedLocations,
      map,
      radius: 45,
      opacity: 0.75
    });

    return () => {
      heatmap.setMap(null);
    };
  }, [visualizationLib, map, visible, weightedLocations]);

  return null;
}
```

---

## 3. Firebase v10 Modular Firestore (`onSnapshot`) + Mock Fallback

Initialize Firebase **only** when `envConfig.hasFirebaseConfig` is `true` so contributors without Firebase credentials never hit `FirebaseError: invalid-api-key` at import time.

```typescript
import { initializeApp, getApps } from "firebase/app";
import {
  getFirestore,
  collection,
  query,
  where,
  onSnapshot,
  type QuerySnapshot,
  type DocumentData
} from "firebase/firestore";
import { envConfig } from "../config/env";
import { fetchFloodZones } from "./api";
import type { FloodZoneItem } from "../types/flood";

export function subscribeToActiveFloodZones(
  onUpdate: (zones: FloodZoneItem[]) => void
): () => void {
  if (!envConfig.hasFirebaseConfig) {
    // Polling fallback against FastAPI backend (works with USE_MOCK_FALLBACK=true)
    let active = true;
    const poll = async () => {
      try {
        const items = await fetchFloodZones();
        if (active) onUpdate(items);
      } catch {
        // Backend still starting up
      }
    };
    poll();
    const timer = window.setInterval(poll, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }

  const app = getApps().length
    ? getApps()[0]
    : initializeApp(envConfig.firebase);
  const db = getFirestore(app);

  const q = query(
    collection(db, "active_flood_zones"),
    where("status", "==", "active")
  );

  return onSnapshot(
    q,
    (snapshot: QuerySnapshot<DocumentData>) => {
      const zones: FloodZoneItem[] = snapshot.docs.map((doc) => {
        const data = doc.data();
        return {
          ...(data as FloodZoneItem),
          event_id: data.event_id || doc.id,
          updated_at:
            typeof data.updated_at?.toDate === "function"
              ? data.updated_at.toDate().toISOString()
              : data.updated_at
        };
      });
      onUpdate(zones);
    },
    (err) => {
      console.error("Firestore onSnapshot error:", err);
    }
  );
}
```

---

## 4. Automatic Live Rerouting Trigger in React

When Firestore pushes a new `active_flood_zones` list while a driver already has an active `routeResult`:
1. Track the current `origin` and `destination` in component state.
2. Whenever `zones` updates (specifically when a zone with `severity_level >= 2` is added whose `event_id` is **not** already in `routeResult.avoided_flood_zone_ids`), check client-side proximity against `routeResult.route_coordinates` (or trigger `requestSafeRoute({ origin, destination, travel_mode: "TWO_WHEELER", avoid_flood_zones: true })` automatically).
3. Render the old flooded path briefly as a dashed red polyline (`strokeOpacity: 0, icons: [dashSymbol]`) alongside the newly computed green safe polyline (`#22c55e`) so judges visually see the instant detour.
