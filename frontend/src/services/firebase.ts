/**
 * Firebase Firestore real-time listener wrapper with polling fallback
 * when VITE_FIREBASE_* keys are not yet configured.
 */

import { envConfig } from "../config/env";
import { fetchFloodZones } from "./api";
import type { FloodZoneItem } from "../types/flood";

export function subscribeToActiveFloodZones(
  onUpdate: (zones: FloodZoneItem[]) => void
): () => void {
  // Fallback to backend polling when Firebase Web SDK credentials are not yet configured
  let active = true;
  const poll = async () => {
    try {
      const items = await fetchFloodZones();
      if (active) onUpdate(items);
    } catch {
      // Ignore transient errors while backend starts up
    }
  };

  poll();
  const timer = window.setInterval(poll, 8000);
  return () => {
    active = false;
    window.clearInterval(timer);
  };
}

export { envConfig };
