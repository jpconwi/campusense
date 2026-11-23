export function googleMapsPinUrl(latitude, longitude) {
  const lat = Number(latitude);
  const lng = Number(longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)
      || lat < -90 || lat > 90 || lng < -180 || lng > 180) return "";
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${lat},${lng}`)}`;
}

export default function MapPinLink({
  latitude,
  longitude,
  children = "Open pin in Google Maps",
}) {
  const url = googleMapsPinUrl(latitude, longitude);
  if (!url) return null;
  return <a href={url} target="_blank" rel="noopener noreferrer">{children}</a>;
}
