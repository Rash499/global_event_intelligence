import { useEffect, useRef } from "react";
import GlobeGL from "globe.gl";

export default function Globe({
  events,
  onSelectEvent,
  onSelectCountry,
  selectedCountryCode,
}) {
  const containerRef = useRef(null);
  const globeRef = useRef(null);
  const countriesRef = useRef([]);

  useEffect(() => {
    if (!containerRef.current) return;

    const globe = GlobeGL()(
      containerRef.current
    )
      .globeImageUrl(
        "//unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
      )
      .bumpImageUrl(
        "//unpkg.com/three-globe/example/img/earth-topology.png"
      )
      .backgroundColor(
        "rgba(0,0,0,0)"
      )
      .showAtmosphere(true)
      .atmosphereColor("#4aa8df")
      .atmosphereAltitude(0.15)
      .pointsMerge(false);

    globeRef.current = globe;

    return () => {
      if (containerRef.current) {
        containerRef.current.innerHTML = "";
      }

      globeRef.current = null;
    };
  }, []);

  /*
   * Load static GeoJSON.
   *
   * Put your GeoJSON here:
   *
   * public/world.geojson
   */
  useEffect(() => {
    if (!globeRef.current) return;

    fetch("/world.geojson")
      .then((response) => response.json())
      .then((geojson) => {
        const countries =
          geojson.features || [];

        countriesRef.current =
          countries;

        globeRef.current
          .polygonsData(countries)
          .polygonCapColor(
            (country) => {
              const code =
                country.properties
                  ?.ISO_A2 ||
                country.properties
                  ?.ISO_A2_E;

              if (
                selectedCountryCode &&
                code === selectedCountryCode
              ) {
                return "rgba(0, 200, 255, 0.55)";
              }

              const countryEvents =
                events.filter(
                  (event) =>
                    event.country_code ===
                    code
                );

              if (!countryEvents.length) {
                return "rgba(40, 80, 110, 0.12)";
              }

              const maxImportance =
                Math.max(
                  ...countryEvents.map(
                    (event) =>
                      event.importance
                  )
                );

              if (maxImportance >= 8) {
                return "rgba(255, 70, 90, 0.45)";
              }

              if (maxImportance >= 6) {
                return "rgba(255, 170, 50, 0.40)";
              }

              return "rgba(60, 180, 255, 0.35)";
            }
          )
          .polygonSideColor(
            () =>
              "rgba(20, 50, 70, 0.25)"
          )
          .polygonStrokeColor(
            () =>
              "rgba(120, 200, 255, 0.35)"
          )
          .polygonAltitude(0.008)
          .polygonLabel(
            (country) => {
              const name =
                country.properties
                  ?.NAME ||
                country.properties
                  ?.ADMIN ||
                "Unknown";

              return `
                <div style="
                  background:#07111f;
                  color:white;
                  padding:8px 12px;
                  border-radius:8px;
                  font-family:Arial;
                ">
                  <strong>${name}</strong>
                  <br/>
                  <small>
                    Click to explore events
                  </small>
                </div>
              `;
            }
          )
          .onPolygonClick(
            (country) => {
              const code =
                country.properties
                  ?.ISO_A2 ||
                country.properties
                  ?.ISO_A2_E;

              const name =
                country.properties
                  ?.NAME ||
                country.properties
                  ?.ADMIN ||
                "Unknown";

              if (
                code &&
                code !== "-99"
              ) {
                onSelectCountry({
                  code,
                  name,
                });
              }
            }
          );
      })
      .catch((error) => {
        console.error(
          "Failed to load world GeoJSON:",
          error
        );
      });
  }, [
    events,
    onSelectCountry,
    selectedCountryCode,
  ]);

  /*
   * Event points
   */
  useEffect(() => {
    if (!globeRef.current) return;

    const validEvents =
      events.filter(
        (event) =>
          event.latitude !== null &&
          event.longitude !== null
      );

    globeRef.current
      .pointsData(validEvents)
      .pointLat("latitude")
      .pointLng("longitude")
      .pointAltitude(
        (event) =>
          0.02 +
          event.importance * 0.012
      )
      .pointRadius(
        (event) =>
          0.5 +
          event.importance * 0.09
      )
      .pointColor(
        (event) => {
          if (
            event.importance >= 8
          ) {
            return "#ff3b5c";
          }

          if (
            event.importance >= 6
          ) {
            return "#ffb020";
          }

          return "#36b8ff";
        }
      )
      .pointLabel(
        (event) => `
          <div style="
            background:#07111f;
            color:white;
            padding:10px 14px;
            border-radius:8px;
            font-family:Arial;
            max-width:280px;
          ">
            <strong>
              ${event.title}
            </strong>

            <br/>

            <small>
              ${event.country || "Global"}
              ·
              Importance
              ${event.importance}/10
            </small>
          </div>
        `
      )
      .onPointClick(
        (event) => {
          onSelectEvent(event);
        }
      );
  }, [events, onSelectEvent]);

  /*
   * Animated rings around important events
   */
  useEffect(() => {
    if (!globeRef.current) return;

    const importantEvents =
      events.filter(
        (event) =>
          event.latitude !== null &&
          event.longitude !== null &&
          event.importance >= 7
      );

    globeRef.current
      .ringsData(importantEvents)
      .ringLat("latitude")
      .ringLng("longitude")
      .ringColor(
        (event) => {
          if (
            event.importance >= 8
          ) {
            return "#ff3b5c";
          }

          return "#ffb020";
        }
      )
      .ringMaxRadius(
        (event) =>
          2 +
          event.importance * 0.35
      )
      .ringPropagationSpeed(
        1.5
      )
      .ringRepeatPeriod(
        1400
      );
  }, [events]);

  /*
   * Camera movement when country selected
   */
  useEffect(() => {
    if (
      !globeRef.current ||
      !selectedCountryCode
    ) {
      return;
    }

    const countryEvents =
      events.filter(
        (event) =>
          event.country_code ===
          selectedCountryCode
      );

    if (!countryEvents.length) {
      return;
    }

    const latitudes =
      countryEvents.map(
        (event) => event.latitude
      );

    const longitudes =
      countryEvents.map(
        (event) => event.longitude
      );

    const latitude =
      latitudes.reduce(
        (sum, value) =>
          sum + value,
        0
      ) / latitudes.length;

    const longitude =
      longitudes.reduce(
        (sum, value) =>
          sum + value,
        0
      ) / longitudes.length;

    globeRef.current.pointOfView(
      {
        lat: latitude,
        lng: longitude,
        altitude: 1.6,
      },
      1200
    );
  }, [
    selectedCountryCode,
    events,
  ]);

  return (
    <div
      ref={containerRef}
      className="globe"
    />
  );
}