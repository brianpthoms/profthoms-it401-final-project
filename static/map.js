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
    const surfSpotIdInput = document.getElementById("surf-spot-id");
    const surfSpotSuggestions = document.getElementById("surf-spot-suggestions");
    const spotSearchStatus = document.getElementById("spot-search-status");
    const useCurrentLocationButton = document.getElementById("use-forecast-location");
    let map = null;
    let currentLocationMarker = null;
    let surfBreakRequest = null;
    let cityRequest = null;
    let resolvedCity = selectedCityInput.value;
    let resolvedSurfBreak = surfBreakInput.value;
    let resolvedSpotType = "surf break";
    let currentLocationLabel = "";
    let currentSpotDistance = null;
    let catalogRequest = null;
    let catalogTimer = null;

    if (!mapElement || !latitudeInput || !longitudeInput || !useCurrentLocationButton) {
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
            surfSpotIdInput.value = "";
            window.setTimeout(() => map.invalidateSize(), 0);
        }
    }

    lookupInputs.forEach((input) => {
        input.addEventListener("change", () => setLookupMode(input.value));
    });

    function closeCatalogSuggestions() {
        surfSpotSuggestions.hidden = true;
        surfSpotSuggestions.replaceChildren();
        locationInput.setAttribute("aria-expanded", "false");
    }

    function chooseCatalogSpot(spot) {
        surfSpotIdInput.value = spot.id;
        locationInput.value = spot.name;
        spotSearchStatus.textContent = `Selected ${spot.name} · ${spot.location}`;
        closeCatalogSuggestions();
    }

    function renderCatalogSuggestions(spots) {
        surfSpotSuggestions.replaceChildren();
        if (!spots.length) {
            closeCatalogSuggestions();
            spotSearchStatus.textContent = "No catalog match. Enter a full coastal city and region instead.";
            return;
        }
        spots.forEach((spot) => {
            const option = document.createElement("button");
            option.type = "button";
            option.className = "spot-suggestion";
            option.setAttribute("role", "option");
            const name = document.createElement("strong");
            name.textContent = spot.name;
            const location = document.createElement("small");
            location.textContent = spot.location;
            option.append(name, location);
            option.addEventListener("click", () => chooseCatalogSpot(spot));
            surfSpotSuggestions.append(option);
        });
        surfSpotSuggestions.hidden = false;
        locationInput.setAttribute("aria-expanded", "true");
        spotSearchStatus.textContent = `${spots.length} known surf spot${spots.length === 1 ? "" : "s"} found.`;
    }

    async function searchCatalog(query) {
        if (catalogRequest) {
            catalogRequest.abort();
        }
        const controller = new AbortController();
        catalogRequest = controller;
        try {
            const response = await fetch(`/api/surf-spots?q=${encodeURIComponent(query)}`, {
                signal: controller.signal,
                headers: { Accept: "application/json" },
            });
            if (!response.ok) {
                throw new Error("Catalog search failed");
            }
            const payload = await response.json();
            renderCatalogSuggestions(payload.spots ?? []);
        } catch (error) {
            if (error.name !== "AbortError") {
                closeCatalogSuggestions();
                spotSearchStatus.textContent = "Spot suggestions are temporarily unavailable; city search still works.";
            }
        } finally {
            if (catalogRequest === controller) {
                catalogRequest = null;
            }
        }
    }

    locationInput.addEventListener("input", () => {
        surfSpotIdInput.value = "";
        window.clearTimeout(catalogTimer);
        const query = locationInput.value.trim();
        if (query.length < 2) {
            closeCatalogSuggestions();
            spotSearchStatus.textContent = "Type at least two characters to search known spots.";
            return;
        }
        catalogTimer = window.setTimeout(() => searchCatalog(query), 180);
    });

    locationInput.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeCatalogSuggestions();
        }
    });

    document.addEventListener("click", (event) => {
        if (!event.target.closest(".spot-search")) {
            closeCatalogSuggestions();
        }
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
        } else if (currentLocationLabel && resolvedSurfBreak) {
            const distance = currentSpotDistance === null
                ? ""
                : ` · Approximately ${formatDistance(currentSpotDistance)} away`;
            coordinateStatus.textContent = `Your location: ${currentLocationLabel} · Closest ${resolvedSpotType}: ${resolvedSurfBreak}${distance}`;
        } else if (resolvedSurfBreak && resolvedCity) {
            coordinateStatus.textContent = `Selected ${resolvedSpotType}: ${resolvedSurfBreak} · Near ${resolvedCity}`;
        } else if (resolvedSurfBreak) {
            coordinateStatus.textContent = `Selected ${resolvedSpotType}: ${resolvedSurfBreak}`;
        } else if (currentLocationLabel) {
            coordinateStatus.textContent = `Your location: ${currentLocationLabel} · No named beach was found nearby`;
        } else if (resolvedCity) {
            coordinateStatus.textContent = `Selected location: ${resolvedCity}`;
        } else {
            coordinateStatus.textContent = "Location selected · City name unavailable";
        }
    }

    async function reverseGeocode(latitude, longitude, useAsCurrentLocation = false) {
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
            const label = [city, region, address.country].filter(Boolean).join(", ");
            if (useAsCurrentLocation) {
                currentLocationLabel = label;
                resolvedCity = label;
                if (currentLocationMarker && label) {
                    currentLocationMarker.setTooltipContent(`Your location: ${label}`);
                }
            } else {
                resolvedCity = label;
            }
            selectedCityInput.value = resolvedCity;
            renderLocationStatus();
            return label;
        } catch (error) {
            if (error.name !== "AbortError") {
                if (!useAsCurrentLocation) {
                    resolvedCity = "";
                    selectedCityInput.value = "";
                }
                renderLocationStatus();
            }
            return "";
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

    function formatDistance(distanceInMetersValue) {
        const miles = distanceInMetersValue / 1609.344;
        return miles < 0.1 ? "less than 0.1 mi" : `${miles.toFixed(1)} mi`;
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

    async function findNearbySurfBreak(latitude, longitude, fromCurrentLocation = false) {
        if (surfBreakRequest) {
            surfBreakRequest.abort();
        }

        surfBreakInput.value = "";
        resolvedSurfBreak = "";
        resolvedSpotType = "surf break";
        currentSpotDistance = null;
        renderLocationStatus("Identifying the nearest named beach or surf break…");
        const controller = new AbortController();
        surfBreakRequest = controller;
        const timeout = window.setTimeout(() => controller.abort(), 8000);
        const query = `[out:json][timeout:6];(nwr(around:50000,${latitude},${longitude})["sport"="surfing"]["name"];nwr(around:50000,${latitude},${longitude})["natural"="beach"]["name"];);out center tags 60;`;
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
                    return tags.name
                        && (tags.sport === "surfing" || tags.natural === "beach")
                        && !tags.shop
                        && !tags.amenity
                        && !tags.club;
                })
                .map((element) => {
                    const coordinates = elementCoordinates(element);
                    return coordinates && {
                        name: element.tags.name,
                        latitude: coordinates[0],
                        longitude: coordinates[1],
                        spotType: element.tags.sport === "surfing" ? "surf break" : "beach",
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
                if (!fromCurrentLocation) {
                    await reverseGeocode(latitude, longitude);
                }
                return;
            }

            const nearestBreak = breaks[0];
            surfBreakInput.value = nearestBreak.name;
            resolvedSurfBreak = nearestBreak.name;
            resolvedSpotType = nearestBreak.spotType;
            currentSpotDistance = fromCurrentLocation ? nearestBreak.distance : null;
            marker.setLatLng([nearestBreak.latitude, nearestBreak.longitude]);
            updateInputs(nearestBreak.latitude, nearestBreak.longitude);
            marker.bindTooltip(
                `${nearestBreak.name} · ${nearestBreak.spotType}`,
                { direction: "top", offset: [0, -12] }
            ).openTooltip();
            if (fromCurrentLocation && currentLocationMarker) {
                map.fitBounds(
                    L.latLngBounds([
                        currentLocationMarker.getLatLng(),
                        marker.getLatLng(),
                    ]),
                    { padding: [45, 45], maxZoom: 13 }
                );
                selectedCityInput.value = currentLocationLabel;
                renderLocationStatus();
            } else {
                map.panTo([nearestBreak.latitude, nearestBreak.longitude]);
                await reverseGeocode(nearestBreak.latitude, nearestBreak.longitude);
            }
        } catch (error) {
            if (error.name !== "AbortError" || surfBreakRequest === controller) {
                if (!fromCurrentLocation) {
                    await reverseGeocode(latitude, longitude);
                } else {
                    renderLocationStatus();
                }
            }
        } finally {
            window.clearTimeout(timeout);
            if (surfBreakRequest === controller) {
                surfBreakRequest = null;
            }
        }
    }

    function clearCurrentLocation() {
        currentLocationLabel = "";
        currentSpotDistance = null;
        if (currentLocationMarker) {
            map.removeLayer(currentLocationMarker);
            currentLocationMarker = null;
        }
    }

    if (!("geolocation" in navigator)) {
        useCurrentLocationButton.disabled = true;
        useCurrentLocationButton.title = "Location services are not available in this browser.";
    } else {
        useCurrentLocationButton.addEventListener("click", () => {
            useCurrentLocationButton.disabled = true;
            renderLocationStatus("Finding your current location…");
            navigator.geolocation.getCurrentPosition(
                async ({ coords }) => {
                    const latitude = coords.latitude;
                    const longitude = coords.longitude;
                    clearCurrentLocation();
                    resolvedCity = "";
                    selectedCityInput.value = "";
                    currentLocationMarker = L.circleMarker(
                        [latitude, longitude],
                        {
                            radius: 9,
                            color: "#ffffff",
                            weight: 3,
                            fillColor: "#ff704f",
                            fillOpacity: 1,
                        }
                    ).addTo(map).bindTooltip("Your current location");
                    selectLocation(latitude, longitude);
                    map.setView([latitude, longitude], 11);
                    await reverseGeocode(latitude, longitude, true);
                    await findNearbySurfBreak(latitude, longitude, true);
                    useCurrentLocationButton.textContent = "Update my current location";
                    useCurrentLocationButton.disabled = false;
                },
                (error) => {
                    const messages = {
                        1: "Location permission was denied. Allow access and try again.",
                        2: "Your current location could not be determined.",
                        3: "Finding your location timed out. Please try again.",
                    };
                    renderLocationStatus(
                        messages[error.code]
                        || "Your current location could not be determined."
                    );
                    useCurrentLocationButton.disabled = false;
                },
                { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
            );
        });
    }

    map.on("click", (event) => {
        clearCurrentLocation();
        selectLocation(event.latlng.lat, event.latlng.lng);
        findNearbySurfBreak(event.latlng.lat, event.latlng.lng);
    });

    marker.on("dragend", () => {
        clearCurrentLocation();
        const position = marker.getLatLng();
        selectLocation(position.lat, position.lng);
        findNearbySurfBreak(position.lat, position.lng);
    });

    function syncMarkerFromInputs() {
        clearCurrentLocation();
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
