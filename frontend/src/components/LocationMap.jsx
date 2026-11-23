import { useEffect } from "react";
import L from "leaflet";
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";
import "leaflet/dist/leaflet.css";

const pinIcon = L.divIcon({
  className: "location-map-pin",
  html: "<span></span>",
  iconSize: [24, 24],
  iconAnchor: [12, 12],
});

function MapPin({ position, onSelect }) {
  useMapEvents({
    click(event) {
      onSelect([event.latlng.lat.toFixed(6), event.latlng.lng.toFixed(6)]);
    },
  });
  return position ? <Marker position={position} icon={pinIcon} /> : null;
}

function MapCenter({ center }) {
  const map = useMap();
  useEffect(() => { map.setView(center, map.getZoom()); }, [center, map]);
  return null;
}

export default function LocationMap({ center, position, onSelect }) {
  return (
    <MapContainer center={position || center} zoom={16} scrollWheelZoom className="location-map">
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        maxZoom={19}
      />
      <MapCenter center={center} />
      <MapPin position={position} onSelect={onSelect} />
    </MapContainer>
  );
}
