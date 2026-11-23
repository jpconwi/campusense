import { lazy, Suspense, useState } from "react";
import MapPinLink from "./MapPinLink.jsx";

const TANDAG_CENTER = [9.078, 126.198];
const LocationMap = lazy(() => import("./LocationMap.jsx"));

export default function LocationPicker({
  latitude,
  longitude,
  disabled,
  invalid,
  onCoordinatesChange,
}) {
  const [mapOpen, setMapOpen] = useState(true);
  const [mapCenter, setMapCenter] = useState(() => (
    latitude !== "" && latitude !== null && latitude !== undefined
      && longitude !== "" && longitude !== null && longitude !== undefined
      && Number.isFinite(Number(latitude)) && Number.isFinite(Number(longitude))
      ? [Number(latitude), Number(longitude)] : TANDAG_CENTER
  ));
  const [error, setError] = useState("");
  const [locating, setLocating] = useState(false);
  const lat = Number(latitude);
  const lng = Number(longitude);
  const hasPin = latitude !== "" && latitude !== null && latitude !== undefined
    && longitude !== "" && longitude !== null && longitude !== undefined
    && Number.isFinite(lat) && Number.isFinite(lng);
  const position = hasPin ? [lat, lng] : null;

  function selectPin(coords) {
    onCoordinatesChange(coords[0], coords[1]);
    setMapCenter([Number(coords[0]), Number(coords[1])]);
    setError("");
  }

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      setError("Location access is unavailable in this browser. You can place a pin on the map.");
      return;
    }
    setLocating(true);
    setError("");
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        selectPin([coords.latitude.toFixed(6), coords.longitude.toFixed(6)]);
        setLocating(false);
      },
      () => {
        setError("Could not get your location. Allow location access or place a pin on the map.");
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  return (
    <div className="location-picker">
      <div className="location-picker-actions">
        <button type="button" className="btn ghost" disabled={disabled}
                aria-expanded={mapOpen} onClick={() => setMapOpen((open) => !open)}>
          {mapOpen ? "Hide map" : "Show map"}
        </button>
        {hasPin && <>
          <span className="location-pin-coordinates">Pin: {lat.toFixed(6)}, {lng.toFixed(6)}</span>
          <MapPinLink latitude={lat} longitude={lng} />
          <button type="button" className="chip" disabled={disabled}
                  onClick={() => onCoordinatesChange("", "")}>Clear pin</button>
        </>}
      </div>
      {mapOpen && <div className={`location-map-panel${invalid ? " invalid" : ""}`}>
        <div className="location-map-toolbar">
          <span>{hasPin ? "Click the map to move the pin." : "Click the map to place a pin."}</span>
          <button type="button" className="btn ghost" disabled={disabled || locating}
                  onClick={useCurrentLocation}>
            {locating ? "Finding you..." : "Use my location"}
          </button>
        </div>
        <Suspense fallback={<div className="location-map location-map-loading">Loading map...</div>}>
          <LocationMap center={mapCenter} position={position} onSelect={selectPin} />
        </Suspense>
        {error && <p className="location-map-error" role="alert">{error}</p>}
      </div>}
    </div>
  );
}
