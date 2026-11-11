/**
 * Environment configuration helper for Vite Frontend.
 */

const isRealValue = (val?: string): boolean => {
  if (!val) return false;
  const lower = val.toLowerCase();
  return !lower.startsWith("your_") && !lower.includes("placeholder");
};

export const envConfig = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
  googleMapsApiKey: import.meta.env.VITE_GOOGLE_MAPS_API_KEY || "",
  useMockFallback:
    (import.meta.env.VITE_USE_MOCK_FALLBACK ?? "true").toString().toLowerCase() === "true",
  firebase: {
    apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "",
    authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "",
    projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "",
    storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || ""
  },
  get hasGoogleMapsKey(): boolean {
    return isRealValue(this.googleMapsApiKey);
  },
  get hasFirebaseConfig(): boolean {
    return isRealValue(this.firebase.apiKey) && isRealValue(this.firebase.projectId);
  }
};
