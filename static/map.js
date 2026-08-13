(() => {
    const mapElement = document.getElementById("location-map");
    const latitudeInput = document.getElementById("latitude");
    const longitudeInput = document.getElementById("longitude");
    const coordinateStatus = document.getElementById("coordinate-status");
    const fallbackMessage = document.getElementById("map-fallback");
    const coordinatePicker = document.getElementById("coordinate-picker");
    const cityPicker = document.getElementById("city-picker");
    const locationInput = document.getElementById("location");
    const lookupInputs = document.querySelectorAll('input[name="lookup"]');
    const forecastFields = document.querySelector(".forecast-form");
    const surfBreakInput = document.getElementById("surf-break-name");
    const selectedCityInput = document.getElementById("selected-city");
    let map = null;
    let surfBreakRequest = null;
    let cityRequest = null;
    let resolvedCity = selectedCityInput.value;
    let resolvedSurfBreak = surfBreakInput.value;

    if (!mapElement || !latitudeInput || !longitudeInput) {
        return;
    }

    function setLookupMode(mode) {
        const useLocation = mode === "location";
        coordinatePicker.hidden = useLocation;
        coordinateStatus.hidden = useLocation;
        cityPicker.hidden = !useLocation;
        forecastFields.classList.toggle("city-mode", useLocation);
        latitudeInput.disabled = useLocation;
        longitudeInput.disabled = useLocation;
        latitudeInput.required = !useLocation;
        longitudeInput.required = !useLocation;
        locationInput.disabled = !useLocation;
        locationInput.required = useLocation;

        if (useLocation) {
            if (surfBreakRequest) {
                surfBreakRequest.abort();
            }
            surfBreakInput.value = "";
            selectedCityInput.value = "";
            locationInput.focus();
        } else if (map) {
            window.setTimeout(() => map.invalidateSize(), 0);
        }
    }

    lookupInputs.forEach((input) => {
        input.addEventListener("change", () => setLookupMode(input.value));
    });

    if (typeof L === "undefined") {
        fallbackMessage.hidden = false;
        return;
    }

    const defaultCoordinates = [33.6595, -117.9988];

    function validCoordinates(latitude, longitude) {
        return Number.isFinite(latitude)
            && Number.isFinite(longitude)
            && latitude >= -90
            && latitude <= 90
            && longitude >= -180
            && longitude <= 180;
    }

    function readInputs() {
        const latitude = Number.parseFloat(mapElement.dataset.latitude);
        const longitude = Number.parseFloat(mapElement.dataset.longitude);
        return validCoordinates(latitude, longitude)
            ? [latitude, longitude]
            : defaultCoordinates;
    }

    function updateInputs(latitude, longitude) {
        latitudeInput.value = latitude.toFixed(5);
        longitudeInput.value = longitude.toFixed(5);
    }

    function renderLocationStatus(message = "") {
        if (message) {
            coordinateStatus.textContent = message;
        } else if (resolvedSurfBreak && resolvedCity) {
            coordinateStatus.textContent = `Selected surf break: ${resolvedSurfBreak} · Near ${resolvedCity}`;
        } else if (resolvedSurfBreak) {
            coordinateStatus.textContent = `Selected surf break: ${resolvedSurfBreak}`;
        } else if (resolvedCity) {
            coordinateStatus.textContent = `Selected location: ${resolvedCity}`;
        } else {
            coordinateStatus.textContent = "Location selected · City name unavailable";
        }
    }

    async function reverseGeocode(latitude, longitude) {
        if (cityRequest) {
            cityRequest.abort();
        }
        const controller = new AbortController();
        cityRequest = controller;
        const timeout = window.setTimeout(() => controller.abort(), 6000);

        try {
            const params = new URLSearchParams({
                format: "jsonv2",
                lat: latitude.toString(),
                lon: longitude.toString(),
                zoom: "10",
                addressdetails: "1",
            });
            const response = await fetch(
                `https://nominatim.openstreetmap.org/reverse?${params}`,
                {
                    signal: controller.signal,
                    headers: {
                        Accept: "application/json",
                        "Api-User-Agent": "Breakline/1.0",
                    },
                },
            );
            if (!response.ok) {
                throw new Error("Reverse geocoding failed");
            }

            const payload = await response.json();
            const address = payload.address ?? {};
            const city = address.city
                ?? address.town
                ?? address.village
                ?? address.municipality
                ?? address.county
                ?? address.state;
            const region = address.state && address.state !== city ? address.state : null;
            resolvedCity = [city, region].filter(Boolean).join(", ");
            selectedCityInput.value = resolvedCity;
            renderLocationStatus();
        } catch (error) {
            if (error.name !== "AbortError") {
                resolvedCity = "";
                selectedCityInput.value = "";
                renderLocationStatus();
            }
        } finally {
            window.clearTimeout(timeout);
            if (cityRequest === controller) {
                cityRequest = null;
            }
        }
    }

    function distanceInMeters(originLatitude, originLongitude, targetLatitude, targetLongitude) {
        const earthRadius = 6371000;
        const toRadians = (degrees) => degrees * Math.PI / 180;
        const latitudeDelta = toRadians(targetLatitude - originLatitude);
        const longitudeDelta = toRadians(targetLongitude - originLongitude);
        const a = Math.sin(latitudeDelta / 2) ** 2
            + Math.cos(toRadians(originLatitude))
            * Math.cos(toRadians(targetLatitude))
            * Math.sin(longitudeDelta / 2) ** 2;
        return 2 * earthRadius * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    function elementCoordinates(element) {
        const latitude = element.lat ?? element.center?.lat;
        const longitude = element.lon ?? element.center?.lon;
        return validCoordinates(latitude, longitude) ? [latitude, longitude] : null;
    }

    const initialCoordinates = readInputs();
    map = L.map(mapElement, { scrollWheelZoom: false }).setView(initialCoordinates, 10);

    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    const marker = L.marker(initialCoordinates, {
        draggable: true,
        title: "Selected forecast location",
    }).addTo(map);
    updateInputs(initialCoordinates[0], initialCoordinates[1]);

    marker.bindTooltip("Forecast point", { direction: "top", offset: [0, -12] });

    function selectLocation(latitude, longitude, panMap = false) {
        marker.setLatLng([latitude, longitude]);
        updateInputs(latitude, longitude);
        if (panMap) {
            map.panTo([latitude, longitude]);
        }
    }

    async function findNearbySurfBreak(latitude, longitude) {
        if (surfBreakRequest) {
            surfBreakRequest.abort();
        }

        surfBreakInput.value = "";
        resolvedSurfBreak = "";
        renderLocationStatus("Identifying the nearest city and surf break…");
        const controller = new AbortController();
        surfBreakRequest = controller;
        const timeout = window.setTimeout(() => controller.abort(), 8000);
        const query = `[out:json][timeout:6];nwr(around:10000,${latitude},${longitude})["sport"="surfing"]["name"];out center tags 30;`;
        const overpassEndpoints = [
            "https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter",
        ];

        try {
            let payload = null;
            for (const endpoint of overpassEndpoints) {
                try {
                    const response = await fetch(
                        `${endpoint}?data=${encodeURIComponent(query)}`,
                        { signal: controller.signal, headers: { Accept: "application/json" } },
                    );
                    if (response.ok) {
                        payload = await response.json();
                        break;
                    }
                } catch (error) {
                    if (error.name === "AbortError") {
                        throw error;
                    }
                }
            }

            if (!payload) {
                throw new Error("OpenStreetMap lookup failed");
            }
            const breaks = payload.elements
                .filter((element) => {
                    const tags = element.tags ?? {};
                    return tags.name && !tags.shop && !tags.amenity && !tags.club;
                })
                .map((element) => {
                    const coordinates = elementCoordinates(element);
                    return coordinates && {
                        name: element.tags.name,
                        latitude: coordinates[0],
                        longitude: coordinates[1],
                        distance: distanceInMeters(
                            latitude,
                            longitude,
                            coordinates[0],
                            coordinates[1],
                        ),
                    };
                })
                .filter(Boolean)
                .sort((first, second) => first.distance - second.distance);

            if (breaks.length === 0) {
                await reverseGeocode(latitude, longitude);
                return;
            }

            const nearestBreak = breaks[0];
            surfBreakInput.value = nearestBreak.name;
            resolvedSurfBreak = nearestBreak.name;
            marker.setLatLng([nearestBreak.latitude, nearestBreak.longitude]);
            updateInputs(nearestBreak.latitude, nearestBreak.longitude);
            map.panTo([nearestBreak.latitude, nearestBreak.longitude]);
            marker.bindTooltip(nearestBreak.name, { direction: "top", offset: [0, -12] }).openTooltip();
            await reverseGeocode(nearestBreak.latitude, nearestBreak.longitude);
        } catch (error) {
            if (error.name !== "AbortError" || surfBreakRequest === controller) {
                await reverseGeocode(latitude, longitude);
            }
        } finally {
            window.clearTimeout(timeout);
            if (surfBreakRequest === controller) {
                surfBreakRequest = null;
            }
        }
    }

    map.on("click", (event) => {
        selectLocation(event.latlng.lat, event.latlng.lng);
        findNearbySurfBreak(event.latlng.lat, event.latlng.lng);
    });

    marker.on("dragend", () => {
        const position = marker.getLatLng();
        selectLocation(position.lat, position.lng);
        findNearbySurfBreak(position.lat, position.lng);
    });

    function syncMarkerFromInputs() {
        const latitude = Number.parseFloat(latitudeInput.value);
        const longitude = Number.parseFloat(longitudeInput.value);
        if (validCoordinates(latitude, longitude)) {
            selectLocation(latitude, longitude, true);
            findNearbySurfBreak(latitude, longitude);
        }
    }

    latitudeInput.addEventListener("change", syncMarkerFromInputs);
    longitudeInput.addEventListener("change", syncMarkerFromInputs);

})();
