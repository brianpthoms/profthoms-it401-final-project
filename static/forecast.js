document.addEventListener("DOMContentLoaded", () => {
    const locationType = document.querySelector("#location-type");
    if (!locationType) return;

    const mapElement = document.querySelector("#forecast-map");
    const latitudeInput = document.querySelector("[name='latitude']");
    const longitudeInput = document.querySelector("[name='longitude']");
    const coordinateOutput = document.querySelector("#map-coordinates");
    const mapHeading = document.querySelector("#map-heading");
    const mapHelp = document.querySelector("#map-help");
    let map;
    let marker;

    const validCoordinates = () => {
        const latitude = Number.parseFloat(latitudeInput.value);
        const longitude = Number.parseFloat(longitudeInput.value);
        if (
            Number.isFinite(latitude) && Number.isFinite(longitude) &&
            latitude >= -90 && latitude <= 90 &&
            longitude >= -180 && longitude <= 180
        ) {
            return { latitude, longitude };
        }
        return null;
    };

    const updateCoordinateFields = (latitude, longitude) => {
        latitudeInput.value = latitude.toFixed(6);
        longitudeInput.value = longitude.toFixed(6);
        coordinateOutput.textContent = `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`;
    };

    const placeMarker = (latitude, longitude, centerMap = false) => {
        if (!map) return;
        if (!marker) {
            marker = window.L.marker([latitude, longitude], {
                draggable: locationType.value === "coordinates",
                autoPan: true,
                title: "Selected forecast location",
                alt: "Selected forecast location",
            }).addTo(map);
            marker.on("dragend", () => {
                const point = marker.getLatLng();
                updateCoordinateFields(point.lat, point.lng);
            });
        } else {
            marker.setLatLng([latitude, longitude]);
        }
        if (centerMap) map.setView([latitude, longitude], Math.max(map.getZoom(), 10));
    };

    const ensureMap = () => {
        if (map || !mapElement || !window.L) return;
        const selected = validCoordinates();
        const center = selected
            ? [selected.latitude, selected.longitude]
            : [20, 0];
        map = window.L.map(mapElement).setView(center, selected ? 11 : 2);
        window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(map);
        map.on("click", (event) => {
            if (locationType.value !== "coordinates") return;
            updateCoordinateFields(event.latlng.lat, event.latlng.lng);
            placeMarker(event.latlng.lat, event.latlng.lng);
        });
        if (selected) {
            updateCoordinateFields(selected.latitude, selected.longitude);
            placeMarker(selected.latitude, selected.longitude);
        }
    };

    const updateLocationFields = () => {
        document.querySelectorAll("[data-location-field]").forEach((field) => {
            const isActive = field.dataset.locationField
                .split(" ")
                .includes(locationType.value);
            field.hidden = !isActive;
            const input = field.querySelector("input");
            if (input) input.required = isActive;
        });
        if (["coordinates", "surf_spot"].includes(locationType.value)) {
            ensureMap();
            window.setTimeout(() => map?.invalidateSize(), 0);
        }
        if (marker) {
            if (locationType.value === "coordinates") marker.dragging.enable();
            else marker.dragging.disable();
        }
        if (mapHeading && mapHelp) {
            const isSpotSearch = locationType.value === "surf_spot";
            mapHeading.textContent = isSpotSearch ? "Resolved surf spot" : "Choose a forecast point";
            mapHelp.textContent = isSpotSearch
                ? "Verify the OpenStreetMap location used for this forecast."
                : "Click the map or drag the marker to set the coordinates.";
        }
    };

    [latitudeInput, longitudeInput].forEach((input) => {
        input.addEventListener("change", () => {
            const selected = validCoordinates();
            if (!selected) return;
            updateCoordinateFields(selected.latitude, selected.longitude);
            placeMarker(selected.latitude, selected.longitude, true);
        });
    });

    locationType.addEventListener("change", updateLocationFields);
    updateLocationFields();
});
