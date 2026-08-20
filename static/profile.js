(() => {
    const useLocationButton = document.querySelector("#use-current-location");
    const clearLocationButton = document.querySelector("#clear-current-location");
    const latitudeInput = document.querySelector("#history-latitude");
    const longitudeInput = document.querySelector("#history-longitude");
    const locationLabelInput = document.querySelector("#history-location-label");
    const radiusSelect = document.querySelector("#history-radius");
    const status = document.querySelector("#location-status");

    if (!useLocationButton || !clearLocationButton || !latitudeInput || !longitudeInput || !locationLabelInput || !radiusSelect || !status) {
        return;
    }

    const setStatus = (message) => {
        status.textContent = message;
    };

    clearLocationButton.addEventListener("click", () => {
        latitudeInput.value = "";
        longitudeInput.value = "";
        locationLabelInput.value = "";
        radiusSelect.value = "";
        clearLocationButton.hidden = true;
        useLocationButton.textContent = "Use my location";
        setStatus("Location removed from this search.");
    });

    if (!("geolocation" in navigator)) {
        useLocationButton.disabled = true;
        setStatus("Location services are not available in this browser.");
        return;
    }

    async function reverseGeocode(latitude, longitude) {
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), 6000);
        const params = new URLSearchParams({
            format: "jsonv2",
            lat: latitude.toString(),
            lon: longitude.toString(),
            zoom: "10",
            addressdetails: "1",
        });

        try {
            const response = await fetch(
                `https://nominatim.openstreetmap.org/reverse?${params}`,
                {
                    signal: controller.signal,
                    headers: {
                        Accept: "application/json",
                        "Api-User-Agent": "Breakline/1.0",
                    },
                }
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
                ?? address.county;
            const parts = [city, address.state, address.country]
                .filter((value, index, values) => value && values.indexOf(value) === index);
            return parts.join(", ");
        } finally {
            window.clearTimeout(timeout);
        }
    }

    useLocationButton.addEventListener("click", () => {
        useLocationButton.disabled = true;
        setStatus("Finding your current location…");
        navigator.geolocation.getCurrentPosition(
            async ({ coords }) => {
                latitudeInput.value = coords.latitude.toFixed(6);
                longitudeInput.value = coords.longitude.toFixed(6);
                locationLabelInput.value = "";
                if (!radiusSelect.value) {
                    radiusSelect.value = "10";
                }
                useLocationButton.textContent = "Update my location";
                clearLocationButton.hidden = false;
                setStatus("Location found. Identifying the city, state, and country…");
                try {
                    const locationLabel = await reverseGeocode(
                        coords.latitude,
                        coords.longitude
                    );
                    if (locationLabel) {
                        locationLabelInput.value = locationLabel;
                        setStatus(`Current location: ${locationLabel}. Submit the form to search nearby forecasts.`);
                    } else {
                        setStatus("Current coordinates added. A city name was not available; you can still search nearby forecasts.");
                    }
                } catch (error) {
                    setStatus("Current coordinates added. The city lookup was unavailable; you can still search nearby forecasts.");
                } finally {
                    useLocationButton.disabled = false;
                }
            },
            (error) => {
                const messages = {
                    1: "Location permission was denied. Allow access and try again.",
                    2: "Your current location could not be determined.",
                    3: "Finding your location timed out. Please try again.",
                };
                setStatus(messages[error.code] || "Your current location could not be determined.");
                useLocationButton.disabled = false;
            },
            { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
        );
    });

})();
