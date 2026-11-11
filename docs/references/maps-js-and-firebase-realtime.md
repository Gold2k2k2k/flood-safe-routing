# Deep Reference: Google Maps JS API (`@vis.gl/react-google-maps`) & Firebase Real-time Sync

This document specifies verified frontend integration patterns for **Google Maps JavaScript API v3.65+**, a **Maps JS `OverlayView` Canvas Thermal Heatmap**, **Firebase v10 Modular Firestore (`onSnapshot`)**, and automatic **Live Rerouting** on the client.

---

## 1. `@vis.gl/react-google-maps` Setup & Map Libraries

### Provider & Map Container
Load `geometry` and `places` on `<APIProvider>` (`visualization` was deprecated and `google.maps.visualization.HeatmapLayer` was removed in Maps JS API v3.65 — do **NOT** call `HeatmapLayer`). Always specify a `mapId` (e.g., `"DEMO_MAP_ID"` for rapid prototyping) when using `<AdvancedMarker>`.

```tsx
import {
  APIProvider,
  Map,
  AdvancedMarker,
  Pin,
  useMap,
  useMapsLibrary
} from "@vis.gl/react-google-maps";
```

> **Version Resilience Note:** Instantiate `mapsLib.Polyline` and `mapsLib.Circle` inside `useEffect` via `useMap()` + `useMapsLibrary("maps")`, and always call `.setMap(null)` on cleanup. This pattern works reliably across all `@vis.gl/react-google-maps` 1.x versions.

---

## 2. Maps JS v3.65+ Flood Heatmap Pattern (`google.maps.OverlayView` Canvas)

> **CRITICAL DEPRECATION GUARD:** Google removed `google.maps.visualization.HeatmapLayer` in Maps JS API **v3.65** (May 2026). Calling `new visualizationLib.HeatmapLayer(...)` fails TypeScript compilation in `@types/google.maps` and throws a runtime error in Maps JS v3.65+.

Instead, `frontend/src/components/HeatmapOverlay.tsx` renders a **viewport-bounded HTML5 Canvas thermal overlay** inside `google.maps.OverlayView` (`overlayLayer` pane), or you can optionally pair `@deck.gl/google-maps` (`GoogleMapsOverlay`) + `@deck.gl/aggregation-layers` (`HeatmapLayer`).

### Canvas `OverlayView` Highlights (`HeatmapOverlay.tsx`)
1. Guard instantiation on `if (!map || !mapsLib || !visible || points.length === 0) return;`.
2. In `onAdd()`, create `<canvas style="position:absolute;pointer-events:none">` and attach to `this.getPanes()?.overlayLayer`.
3. In `draw()`, project `map.getBounds()` (`getSouthWest()`, `getNorthEast()`) via `projection.fromLatLngToDivPixel(...)` to size the canvas strictly to the visible viewport (`+ 2 * radiusPx`), then render radial weighted gradients (`rgba(239,68,68)` -> `rgba(245,158,11)` -> transparent) for each `HeatmapPoint`.
4. In `onRemove()` and React `useEffect` cleanup, remove the canvas DOM node and call `overlay.setMap(null)`.

---

## 3. Firebase v10 Modular Firestore (`onSnapshot`) + Mock Fallback

Initialize Firebase **only** when `envConfig.hasFirebaseConfig` is `true` so contributors without Firebase credentials never hit `FirebaseError: invalid-api-key` at import time.

```typescript
import { getApps, initializeApp } from "firebase/app";
import {
  collection,
  getFirestore,
  onSnapshot,
  query,
  where,
  type DocumentData,
  type QuerySnapshot
} from "firebase/firestore";
import { envConfig } from "../config/env";
import { fetchFloodZones } from "./api";
import type { FloodZoneItem } from "../types/flood";

export function subscribeToActiveFloodZones(
  onUpdate: (zones: FloodZoneItem[]) => void,
  onError?: (err: Error) => void
): () => void {
  if (!envConfig.hasFirebaseConfig) {
    let active = true;
    const poll = async () => {
      try {
        const items = await fetchFloodZones();
        if (active) onUpdate(items);
      } catch (err) {
        if (onError && err instanceof Error) onError(err);
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }

  const app = getApps().length ? getApps()[0] : initializeApp(envConfig.firebase);
  const db = getFirestore(app);
  const q = query(collection(db, "active_flood_zones"), where("status", "==", "active"));

  return onSnapshot(
    q,
    (snapshot: QuerySnapshot<DocumentData>) => {
      const nowMs = Date.now();
      const zones: FloodZoneItem[] = [];
      snapshot.forEach((doc) => {
        const data = doc.data();
        const ttl = data.ttl_expires_at as string | undefined;
        if (ttl) {
          const ttlMs = Date.parse(ttl);
          if (!Number.isNaN(ttlMs) && ttlMs <= nowMs) return;
        }
        zones.push({
          ...(data as FloodZoneItem),
          event_id: (data.event_id as string) || doc.id,
          updated_at:
            typeof data.updated_at?.toDate === "function"
              ? data.updated_at.toDate().toISOString()
              : (data.updated_at as string)
        });
      });
      onUpdate(zones);
    },
    (error) => {
      if (onError) onError(error);
    }
  );
}
```

---

## 4. Automatic Live Rerouting Trigger in React (`useAutoReroute.ts`)

When Firestore pushes a new `active_flood_zones` list while a driver already has an active `routeResult`:
1. Compare incoming active zones (`severity_level >= 2`) against `routeResult.avoided_flood_zone_ids`.
2. If any new un-avoided severe zone appears, `useAutoReroute` automatically invokes `requestSafeRoute({ origin, destination, travel_mode: "TWO_WHEELER", avoid_flood_zones: true })`.
3. `FloodMap` re-renders the safe polyline in green (`#22c55e`) when `routeResult.rerouted === true` alongside red flood circles (`#ef4444`).
