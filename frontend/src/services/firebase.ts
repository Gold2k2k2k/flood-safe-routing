/**
 * Firebase v10 Modular Firestore real-time listener with backend polling fallback
 * when VITE_FIREBASE_* keys are not yet configured.
 */

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

export { envConfig };
