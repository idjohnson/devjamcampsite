/**
 * Minnesota Park & Campsite Explorer - Frontend Application
 * Supports Google Maps JavaScript API + MarkerClusterer with automatic
 * interactive Leaflet/Topo fallback when GOOGLE_MAPS_API_KEY is not yet configured.
 */

const MN_CENTER = { lat: 46.35, lng: -94.2 };
const MN_DEFAULT_ZOOM = 6;

const state = {
  viewMode: "campsites", // "campsites" | "parks"
  campsites: [],
  parks: [],
  favorites: new Set(),
  notes: {},
  user: window.__INITIAL_CONFIG__?.user || null,
  selectedSite: null,
  mapEngine: null, // "google" | "fallback"
  gmap: null,
  gmapClusterer: null,
  gmapMarkers: [],
  gmapInfoWindow: null,
  lmap: null,
  lClusterGroup: null,
  lParkLayer: null,
  chips: {
    electric: false,
    waterfront: false,
    ada_accessible: false,
    pets_allowed: false,
    food_locker: false,
    favorites_only: false,
  },
};

// Determine color for a campsite pin based on attributes
function getSiteColor(site) {
  const unit = (site.unit_type || "").toLowerCase();
  const sType = (site.site_type || "").toLowerCase();
  if (unit.includes("tipi") || unit.includes("wall tent") || unit.includes("group")) {
    return "#e11d48"; // Rose-600
  }
  if (site.electric_30amp || site.electric_50amp || sType.includes("electric")) {
    return "#d97706"; // Amber-600
  }
  if (site.waterfront || sType.includes("canoe") || sType.includes("boat")) {
    return "#0284c7"; // Sky-600
  }
  if (sType.includes("backpack") || sType.includes("walk") || sType.includes("cart") || sType.includes("bike")) {
    return "#7e22ce"; // Purple-700
  }
  return "#15803d"; // Emerald-700
}

function formatDistanceFt(feet) {
  if (feet === null || feet === undefined) return "Not listed";
  if (feet >= 5280) {
    return `${(feet / 5280).toFixed(1)} mi (${feet.toLocaleString()} ft)`;
  }
  return `${feet.toLocaleString()} ft`;
}

// ============================================================================
// MAP INITIALIZATION (Google Maps JS API + Automatic Interactive Fallback)
// ============================================================================

function getEffectiveGoogleMapsKey() {
  const localKey = localStorage.getItem("mn_explorer_gmaps_key");
  if (localKey && localKey.trim()) return localKey.trim();
  return (window.__INITIAL_CONFIG__?.googleMapsApiKey || "").trim();
}

window.gm_authFailure = function () {
  console.warn("Google Maps API key authentication failed; switching to interactive fallback map.");
  initFallbackMap("Google Maps API Key Rejected (Fallback Active)");
  renderMapMarkers();
};

async function initMap() {
  const apiKey = getEffectiveGoogleMapsKey();
  const keyInput = document.getElementById("input-runtime-gmaps-key");
  if (keyInput && apiKey) keyInput.value = apiKey;

  if (apiKey) {
    try {
      await loadGoogleMapsScript(apiKey);
      initGoogleMap();
      return;
    } catch (err) {
      console.warn("Could not load Google Maps JS API, falling back to interactive map:", err);
    }
  }
  initFallbackMap();
}

function loadGoogleMapsScript(apiKey) {
  return new Promise((resolve, reject) => {
    if (window.google && window.google.maps) {
      resolve();
      return;
    }
    window.__onGoogleMapsLoaded = () => resolve();
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&callback=__onGoogleMapsLoaded`;
    script.async = true;
    script.defer = true;
    script.onerror = () => reject(new Error("Failed to load Google Maps script"));
    document.head.appendChild(script);
  });
}

function initGoogleMap() {
  state.mapEngine = "google";
  updateMapStatusBadge("Google Maps JS API", true);

  const container = document.getElementById("map-canvas");
  container.innerHTML = "";

  state.gmap = new google.maps.Map(container, {
    center: MN_CENTER,
    zoom: MN_DEFAULT_ZOOM,
    mapTypeId: "terrain",
    mapTypeControl: true,
    mapTypeControlOptions: {
      style: google.maps.MapTypeControlStyle.HORIZONTAL_BAR,
      position: google.maps.ControlPosition.TOP_LEFT,
    },
    streetViewControl: true,
    fullscreenControl: false,
  });

  state.gmapInfoWindow = new google.maps.InfoWindow();
}

function initFallbackMap(customStatusLabel) {
  state.mapEngine = "fallback";
  updateMapStatusBadge(customStatusLabel || "Interactive Map (Google Maps Ready)", false);

  const container = document.getElementById("map-canvas");
  if (state.lmap) {
    state.lmap.remove();
    state.lmap = null;
  }
  container.innerHTML = "";

  const osmLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors | Minnesota DNR Park Data',
  });

  const topoLayer = L.tileLayer("https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 16,
    attribution: "USGS National Map Topo",
  });

  const satLayer = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 19,
    attribution: "Esri World Imagery",
  });

  state.lmap = L.map(container, {
    center: [MN_CENTER.lat, MN_CENTER.lng],
    zoom: MN_DEFAULT_ZOOM,
    layers: [osmLayer],
    preferCanvas: true,
  });

  L.control.layers(
    {
      "Street & Park Map": osmLayer,
      "USGS Topographic": topoLayer,
      "Satellite Imagery": satLayer,
    },
    null,
    { position: "topleft" }
  ).addTo(state.lmap);

  state.lClusterGroup = L.markerClusterGroup({
    chunkedLoading: true,
    maxClusterRadius: 50,
    spiderfyOnMaxZoom: true,
    showCoverageOnHover: false,
  });
  state.lParkLayer = L.layerGroup();
  state.lmap.addLayer(state.lClusterGroup);
}

function updateMapStatusBadge(label, isNativeGoogle) {
  const dot = document.getElementById("map-engine-dot");
  const textEl = document.getElementById("map-engine-label");
  const modalLabel = document.getElementById("modal-map-engine-name");
  if (dot) {
    dot.className = isNativeGoogle
      ? "w-2 h-2 rounded-full bg-emerald-400"
      : "w-2 h-2 rounded-full bg-amber-400";
  }
  if (textEl) textEl.textContent = isNativeGoogle ? "Google Maps Active" : "Map Engine";
  if (modalLabel) modalLabel.textContent = label;
}

// ============================================================================
// RENDERING MARKERS ON MAP
// ============================================================================

function renderMapMarkers(fitBounds = false) {
  if (state.mapEngine === "google" && state.gmap) {
    renderGoogleMapMarkers(fitBounds);
  } else if (state.lmap) {
    renderFallbackMapMarkers(fitBounds);
  }
}

function renderGoogleMapMarkers(fitBounds = false) {
  if (state.gmapClusterer) {
    state.gmapClusterer.clearMarkers();
  }
  state.gmapMarkers.forEach((m) => m.setMap(null));
  state.gmapMarkers = [];

  const bounds = new google.maps.LatLngBounds();

  if (state.viewMode === "parks") {
    state.parks.forEach((park) => {
      const pos = { lat: park.lat, lng: park.lon };
      bounds.extend(pos);
      const marker = new google.maps.Marker({
        position: pos,
        map: state.gmap,
        title: `${park.park} (${park.total_sites} sites)`,
        label: {
          text: String(park.total_sites),
          color: "#ffffff",
          fontSize: "11px",
          fontWeight: "bold",
        },
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          fillColor: "#14532d",
          fillOpacity: 0.95,
          strokeColor: "#ffffff",
          strokeWeight: 2,
          scale: 16,
        },
      });
      marker.addListener("click", () => {
        selectParkFromMap(park);
      });
      state.gmapMarkers.push(marker);
    });
  } else {
    state.campsites.forEach((site) => {
      const pos = { lat: site.lat, lng: site.lon };
      bounds.extend(pos);
      const color = getSiteColor(site);
      const isFav = state.favorites.has(site.id);
      const marker = new google.maps.Marker({
        position: pos,
        title: `${site.park} - ${site.campground} #${site.site_name || site.unit_type}`,
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          fillColor: color,
          fillOpacity: 0.92,
          strokeColor: isFav ? "#facc15" : "#ffffff",
          strokeWeight: isFav ? 3 : 1.8,
          scale: isFav ? 9 : 7,
        },
      });
      marker.addListener("click", () => {
        openCampsiteDetail(site, true);
      });
      state.gmapMarkers.push(marker);
    });

    if (window.markerClusterer && window.markerClusterer.MarkerClusterer) {
      state.gmapClusterer = new window.markerClusterer.MarkerClusterer({
        map: state.gmap,
        markers: state.gmapMarkers,
      });
    } else {
      state.gmapMarkers.forEach((m) => m.setMap(state.gmap));
    }
  }

  if (fitBounds && state.gmapMarkers.length > 0) {
    state.gmap.fitBounds(bounds);
  }
}

function renderFallbackMapMarkers(fitBounds = false) {
  state.lClusterGroup.clearLayers();
  state.lParkLayer.clearLayers();

  const latLngs = [];

  if (state.viewMode === "parks") {
    if (state.lmap.hasLayer(state.lClusterGroup)) {
      state.lmap.removeLayer(state.lClusterGroup);
    }
    if (!state.lmap.hasLayer(state.lParkLayer)) {
      state.lmap.addLayer(state.lParkLayer);
    }

    state.parks.forEach((park) => {
      latLngs.push([park.lat, park.lon]);
      const icon = L.divIcon({
        className: "",
        html: `<div class="mn-park-badge" style="width:34px;height:34px;" title="${park.park}">${park.total_sites}</div>`,
        iconSize: [34, 34],
        iconAnchor: [17, 17],
      });
      const marker = L.marker([park.lat, park.lon], { icon });
      marker.bindTooltip(
        `<strong>${park.park}</strong><br/>${park.total_sites} campsites &bull; ${park.tourism_region || park.county}`,
        { direction: "top", offset: [0, -14] }
      );
      marker.on("click", () => selectParkFromMap(park));
      state.lParkLayer.addLayer(marker);
    });
  } else {
    if (state.lmap.hasLayer(state.lParkLayer)) {
      state.lmap.removeLayer(state.lParkLayer);
    }
    if (!state.lmap.hasLayer(state.lClusterGroup)) {
      state.lmap.addLayer(state.lClusterGroup);
    }

    const markers = [];
    state.campsites.forEach((site) => {
      latLngs.push([site.lat, site.lon]);
      const color = getSiteColor(site);
      const isFav = state.favorites.has(site.id);
      const ring = isFav ? "border: 2.5px solid #facc15;" : "border: 2px solid #ffffff;";
      const size = isFav ? 20 : 16;

      const icon = L.divIcon({
        className: "",
        html: `<div class="mn-pin-marker" style="width:${size}px;height:${size}px;background:${color};${ring}"></div>`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
      });

      const marker = L.marker([site.lat, site.lon], { icon });
      marker.bindTooltip(
        `<strong>${site.park}</strong><br/>${site.campground} &bull; Site ${site.site_name || site.unit_type}<br/><span style="color:#cbd5e1">${site.site_type || site.unit_type}</span>`,
        { direction: "top", offset: [0, -8] }
      );
      marker.on("click", () => openCampsiteDetail(site, false));
      markers.push(marker);
    });

    state.lClusterGroup.addLayers(markers);
  }

  if (fitBounds && latLngs.length > 0) {
    state.lmap.fitBounds(L.latLngBounds(latLngs), { padding: [35, 35], maxZoom: 15 });
  }
}

function selectParkFromMap(park) {
  const parkSelect = document.getElementById("filter-park");
  if (parkSelect) {
    parkSelect.value = park.park;
  }
  setViewMode("campsites", false);
  fetchAndRenderCampsites(true);
}

// ============================================================================
// DATA FETCHING & FILTERING
// ============================================================================

async function loadInitialData() {
  showLoading(true);
  try {
    const [configResp, parksResp, sitesResp] = await Promise.all([
      fetch("/api/config"),
      fetch("/api/parks"),
      fetch("/api/campsites"),
    ]);

    if (configResp.ok) {
      const cfg = await configResp.json();
      state.user = cfg.user;
      state.favorites = new Set(cfg.favorites || []);
      state.notes = cfg.notes || {};
      updateFavoritesBadge();
    }

    if (parksResp.ok) {
      const parksData = await parksResp.json();
      state.parks = parksData.parks || [];
    }

    if (sitesResp.ok) {
      const sitesData = await sitesResp.json();
      state.campsites = sitesData.campsites || [];
    }

    updateCounts();
    renderResultsList();
    renderMapMarkers(false);
  } catch (err) {
    console.error("Failed loading initial data:", err);
  } finally {
    showLoading(false);
  }
}

function buildFilterQueryParams() {
  const params = new URLSearchParams();

  const q = document.getElementById("filter-search")?.value?.trim();
  const region = document.getElementById("filter-region")?.value;
  const parkType = document.getElementById("filter-park-type")?.value;
  const park = document.getElementById("filter-park")?.value;
  const county = document.getElementById("filter-county")?.value;
  const unitType = document.getElementById("filter-unit-type")?.value;
  const siteType = document.getElementById("filter-site-type")?.value;
  const shade = document.getElementById("filter-shade")?.value;
  const amp50 = document.getElementById("filter-50amp")?.value;
  const padLen = parseInt(document.getElementById("filter-pad-length")?.value || "0", 10);
  const minPeople = parseInt(document.getElementById("filter-min-people")?.value || "0", 10);

  if (q) params.set("q", q);
  if (region) params.set("tourism_region", region);
  if (parkType) params.set("park_type", parkType);
  if (park) params.set("park", park);
  if (county) params.set("county", county);
  if (unitType) params.set("unit_type", unitType);
  if (siteType) params.set("site_type", siteType);
  if (shade) params.set("shade", shade);
  if (amp50 === "true") params.set("electric_50amp", "true");
  if (padLen > 0) params.set("min_pad_length", String(padLen));
  if (minPeople > 0) params.set("min_people", String(minPeople));

  Object.entries(state.chips).forEach(([key, active]) => {
    if (active) params.set(key, "true");
  });

  return params;
}

let filterDebounceTimer = null;
function scheduleFilterRefresh(fitBounds = false) {
  if (filterDebounceTimer) clearTimeout(filterDebounceTimer);
  filterDebounceTimer = setTimeout(() => {
    fetchAndRenderCampsites(fitBounds);
  }, 180);
}

async function fetchAndRenderCampsites(fitBounds = false) {
  showLoading(true);
  try {
    const params = buildFilterQueryParams();
    const resp = await fetch(`/api/campsites?${params.toString()}`);
    if (!resp.ok) throw new Error("Failed fetching campsites");
    const data = await resp.json();
    state.campsites = data.campsites || [];
    updateCounts();
    renderResultsList();
    renderMapMarkers(fitBounds);
  } catch (err) {
    console.error("Error filtering campsites:", err);
  } finally {
    showLoading(false);
  }
}

function updateCounts() {
  const countEl = document.getElementById("count-filtered-sites");
  const tabCountEl = document.getElementById("tab-results-count");
  if (countEl) countEl.textContent = state.campsites.length.toLocaleString();
  if (tabCountEl) {
    tabCountEl.textContent =
      state.viewMode === "parks"
        ? state.parks.length.toLocaleString()
        : state.campsites.length.toLocaleString();
  }
}

function updateFavoritesBadge() {
  const favEl = document.getElementById("fav-count");
  if (favEl) favEl.textContent = String(state.favorites.size);
}

// ============================================================================
// RESULTS LIST RENDERING
// ============================================================================

function renderResultsList() {
  const container = document.getElementById("results-list-container");
  if (!container) return;

  if (state.viewMode === "parks") {
    if (state.parks.length === 0) {
      container.innerHTML = `<div class="p-6 text-center text-xs text-slate-500">No parks found.</div>`;
      return;
    }
    container.innerHTML = state.parks
      .map(
        (p) => `
      <div class="p-3.5 hover:bg-emerald-50/60 cursor-pointer transition flex items-center justify-between gap-2"
           data-park-name="${escapeHtml(p.park)}">
        <div>
          <div class="text-xs font-bold text-slate-900">${escapeHtml(p.park)}</div>
          <div class="text-[11px] text-slate-500">${escapeHtml(p.park_type)} &bull; ${escapeHtml(p.county)} County (${escapeHtml(p.tourism_region || "MN")})</div>
          <div class="flex flex-wrap gap-1 mt-1">
            ${p.has_electric ? `<span class="px-1.5 py-0.5 text-[10px] rounded bg-amber-100 text-amber-800 font-medium">⚡ Electric</span>` : ""}
            ${p.has_waterfront ? `<span class="px-1.5 py-0.5 text-[10px] rounded bg-sky-100 text-sky-800 font-medium">🌊 Waterfront</span>` : ""}
            ${p.has_ada ? `<span class="px-1.5 py-0.5 text-[10px] rounded bg-indigo-100 text-indigo-800 font-medium">♿ ADA</span>` : ""}
          </div>
        </div>
        <div class="shrink-0 px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-900 font-bold text-xs">
          ${p.total_sites} sites
        </div>
      </div>`
      )
      .join("");

    container.querySelectorAll("[data-park-name]").forEach((el) => {
      el.addEventListener("click", () => {
        const pName = el.getAttribute("data-park-name");
        const parkObj = state.parks.find((x) => x.park === pName);
        if (parkObj) selectParkFromMap(parkObj);
      });
    });
    return;
  }

  // Render first 200 matching campsites for crisp DOM performance
  const subset = state.campsites.slice(0, 200);
  if (subset.length === 0) {
    container.innerHTML = `
      <div class="p-8 text-center space-y-2">
        <div class="text-sm font-semibold text-slate-700">No matching Minnesota campsites</div>
        <p class="text-xs text-slate-500">Try clearing one or more filters to expand your search.</p>
      </div>`;
    return;
  }

  container.innerHTML =
    subset
      .map((s) => {
        const isFav = state.favorites.has(s.id);
        const hasNote = Boolean(state.notes[s.id]?.note || state.notes[s.id]?.rating);
        const color = getSiteColor(s);
        return `
      <div class="p-3 hover:bg-slate-50 cursor-pointer transition flex items-start justify-between gap-2"
           data-site-id="${escapeHtml(s.id)}">
        <div class="min-w-0">
          <div class="flex items-center gap-1.5">
            <span class="w-2.5 h-2.5 rounded-full shrink-0" style="background:${color}"></span>
            <span class="text-xs font-bold text-slate-900 truncate">${escapeHtml(s.park)}</span>
            ${isFav ? `<span class="text-amber-500 text-xs" title="Favorited">★</span>` : ""}
            ${hasNote ? `<span class="px-1.5 py-0.2 bg-amber-100 text-amber-800 rounded text-[10px] font-medium">Note</span>` : ""}
          </div>
          <div class="text-xs text-slate-700 font-medium mt-0.5">
            ${escapeHtml(s.campground)} &bull; <span class="text-emerald-800 font-semibold">Site ${escapeHtml(s.site_name || s.unit_type)}</span>
          </div>
          <div class="text-[11px] text-slate-500 mt-0.5 flex flex-wrap gap-1.5">
            <span>${escapeHtml(s.site_type || s.unit_type)}</span>
            ${s.electric_50amp ? `<span class="text-amber-700 font-medium">&bull; 50A</span>` : s.electric_30amp ? `<span class="text-amber-700 font-medium">&bull; 30A</span>` : ""}
            ${s.waterfront ? `<span class="text-sky-700 font-medium">&bull; Waterfront</span>` : ""}
            ${s.pad_length_ft ? `<span>&bull; ${s.pad_length_ft}ft pad</span>` : ""}
          </div>
        </div>
        <span class="text-[11px] text-emerald-700 font-semibold shrink-0">View &rarr;</span>
      </div>`;
      })
      .join("") +
    (state.campsites.length > 200
      ? `<div class="p-3 text-center text-[11px] text-slate-500 bg-slate-50">Showing first 200 of ${state.campsites.length.toLocaleString()} sites in list. All ${state.campsites.length.toLocaleString()} are plotted on the interactive map.</div>`
      : "");

  container.querySelectorAll("[data-site-id]").forEach((el) => {
    el.addEventListener("click", () => {
      const siteId = el.getAttribute("data-site-id");
      const site = state.campsites.find((x) => x.id === siteId);
      if (site) openCampsiteDetail(site, true);
    });
  });
}

// ============================================================================
// CAMPSITE DETAIL DRAWER & FAVORITES / NOTES
// ============================================================================

function openCampsiteDetail(site, panMap = true) {
  state.selectedSite = site;

  if (panMap) {
    if (state.mapEngine === "google" && state.gmap) {
      state.gmap.panTo({ lat: site.lat, lng: site.lon });
      if (state.gmap.getZoom() < 14) state.gmap.setZoom(15);
    } else if (state.lmap) {
      state.lmap.setView([site.lat, site.lon], Math.max(state.lmap.getZoom(), 15));
    }
  }

  document.getElementById("detail-park-type").textContent = site.park_type || "Minnesota Park";
  document.getElementById("detail-region").textContent = site.tourism_region || "Minnesota";
  document.getElementById("detail-county").textContent = site.county ? `${site.county} County` : "";
  document.getElementById("detail-title").textContent = `${site.park}`;
  document.getElementById("detail-subtitle").textContent = `${site.campground} — Site ${site.site_name || site.unit_type}`;

  // Badges
  const badges = [];
  badges.push(`<span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-900">${escapeHtml(site.unit_type)}</span>`);
  if (site.site_type) {
    badges.push(`<span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-200 text-slate-800">${escapeHtml(site.site_type)}</span>`);
  }
  if (site.electric_50amp) {
    badges.push(`<span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-900">⚡ 50-Amp &amp; ${site.electric_30amp ? "30-Amp" : "Electric"}</span>`);
  } else if (site.electric_30amp) {
    badges.push(`<span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-900">⚡ 30-Amp Electric</span>`);
  }
  if (site.waterfront) {
    badges.push(`<span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-sky-100 text-sky-900">🌊 Waterfront</span>`);
  }
  if (site.ada_accessible) {
    badges.push(`<span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-900">♿ ADA Accessible</span>`);
  }
  if (site.food_locker) {
    badges.push(`<span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-orange-100 text-orange-900">🐻 Bear/Food Locker</span>`);
  }
  document.getElementById("detail-badges").innerHTML = badges.join("");

  // Google Maps external directions link
  const gmapsLink = document.getElementById("link-gmaps-directions");
  gmapsLink.href = `https://www.google.com/maps/search/?api=1&query=${site.lat},${site.lon}`;

  // Specs Grid
  document.getElementById("detail-specs-grid").innerHTML = [
    specItem("Max People", site.max_people ? `${site.max_people} campers` : "Standard"),
    specItem("Max Vehicles", site.max_vehicles ? `${site.max_vehicles} vehicles` : "Standard"),
    specItem("Tree Shade", site.shade || "Not specified"),
    specItem("Pets Allowed", site.pets_allowed ? "Yes" : "No"),
    specItem("Fire Ring", site.fire_ring ? "Yes" : "No"),
    specItem("Picnic Table", site.picnic_table ? "Yes" : "No"),
    specItem("Food Locker", site.food_locker ? "Yes" : "No"),
    specItem("Coordinates", `${site.lat.toFixed(5)}, ${site.lon.toFixed(5)}`),
  ].join("");

  // Pad Grid
  document.getElementById("detail-pad-grid").innerHTML = [
    specItem("Pad Length", site.pad_length_ft ? `${site.pad_length_ft} ft` : "N/A"),
    specItem("Pad Width", site.pad_width_ft ? `${site.pad_width_ft} ft` : "N/A"),
    specItem("Pad Surface", site.pad_surface || "Natural"),
    specItem("Tent Pad", site.tent_pad || "N/A"),
    specItem("30-Amp Electric", site.electric_30amp ? "Yes" : "No"),
    specItem("50-Amp Electric", site.electric_50amp ? "Yes" : "No"),
  ].join("");

  // Distances Grid
  document.getElementById("detail-distances-grid").innerHTML = [
    specItem("To Restroom", formatDistanceFt(site.feet_to_restroom)),
    specItem("To Showers", formatDistanceFt(site.feet_to_shower)),
    specItem("To Drinking Water", formatDistanceFt(site.feet_to_water)),
    specItem("To Dump Station", formatDistanceFt(site.feet_to_dump_station)),
  ].join("");

  // Favorite star state
  updateDrawerFavoriteStar();

  // Populate user note & rating
  const existingNote = state.notes[site.id] || { note: "", rating: null };
  const noteTextarea = document.getElementById("note-textarea");
  const noteRating = document.getElementById("note-rating");
  const noteStatus = document.getElementById("note-save-status");
  if (noteTextarea) noteTextarea.value = existingNote.note || "";
  if (noteRating) noteRating.value = existingNote.rating ? String(existingNote.rating) : "";
  if (noteStatus) noteStatus.textContent = "";

  document.getElementById("site-detail-drawer").classList.remove("hidden");
}

function specItem(label, value) {
  return `
    <div>
      <div class="text-[11px] text-slate-400 font-medium">${escapeHtml(label)}</div>
      <div class="text-xs font-semibold text-slate-800">${escapeHtml(String(value))}</div>
    </div>`;
}

function updateDrawerFavoriteStar() {
  const starSvg = document.getElementById("icon-favorite-star");
  if (!starSvg || !state.selectedSite) return;
  const isFav = state.favorites.has(state.selectedSite.id);
  if (isFav) {
    starSvg.setAttribute("fill", "#facc15");
    starSvg.classList.add("text-amber-400");
  } else {
    starSvg.setAttribute("fill", "none");
    starSvg.classList.remove("text-amber-400");
  }
}

async function toggleSelectedFavorite() {
  if (!state.selectedSite) return;
  if (!state.user) {
    openModal("login");
    return;
  }
  const siteId = state.selectedSite.id;
  const resp = await fetch(`/api/favorites/${encodeURIComponent(siteId)}`, { method: "POST" });
  if (resp.status === 401) {
    openModal("login");
    return;
  }
  if (resp.ok) {
    const data = await resp.json();
    state.favorites = new Set(data.favorites || []);
    updateDrawerFavoriteStar();
    updateFavoritesBadge();
    renderResultsList();
    renderMapMarkers(false);
  }
}

async function saveSelectedSiteNote() {
  if (!state.selectedSite) return;
  if (!state.user) {
    openModal("login");
    return;
  }
  const siteId = state.selectedSite.id;
  const note = document.getElementById("note-textarea")?.value || "";
  const ratingVal = document.getElementById("note-rating")?.value;
  const rating = ratingVal ? parseInt(ratingVal, 10) : null;
  const statusEl = document.getElementById("note-save-status");

  if (statusEl) statusEl.textContent = "Saving...";
  const resp = await fetch(`/api/notes/${encodeURIComponent(siteId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note, rating }),
  });

  if (resp.ok) {
    const data = await resp.json();
    state.notes = data.notes || {};
    if (statusEl) statusEl.textContent = "Saved to your profile!";
    renderResultsList();
  } else {
    if (statusEl) statusEl.textContent = "Failed to save note.";
  }
}

// ============================================================================
// GOOGLE IDENTITY SERVICES CALLBACK & SHEET SYNC
// ============================================================================

window.handleGoogleCredentialResponse = async function (response) {
  if (!response?.credential) return;
  try {
    const res = await fetch("/auth/google/token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential: response.credential }),
    });
    if (res.ok) {
      window.location.reload();
    }
  } catch (err) {
    console.error("Google Identity login failed:", err);
  }
};

async function triggerGoogleSheetSync() {
  const btn = document.getElementById("btn-sync-sheet");
  const icon = document.getElementById("sync-icon");
  if (icon) icon.classList.add("animate-spin");
  if (btn) btn.disabled = true;

  try {
    const resp = await fetch("/api/sync", { method: "POST" });
    if (resp.ok) {
      const data = await resp.json();
      const syncedEl = document.getElementById("meta-last-synced");
      const badgeEl = document.getElementById("meta-source-badge");
      if (syncedEl && data.metadata) syncedEl.textContent = data.metadata.last_synced_at;
      if (badgeEl && data.metadata) badgeEl.textContent = data.metadata.source;
      await fetchAndRenderCampsites(false);
    }
  } catch (err) {
    console.error("Failed syncing Google Sheet:", err);
  } finally {
    if (icon) icon.classList.remove("animate-spin");
    if (btn) btn.disabled = false;
  }
}

// ============================================================================
// UI EVENT LISTENERS & MODALS
// ============================================================================

function setViewMode(mode, rerender = true) {
  state.viewMode = mode;
  const btnSites = document.getElementById("mode-campsites");
  const btnParks = document.getElementById("mode-parks");
  if (mode === "campsites") {
    btnSites.className = "py-1.5 px-2 rounded-md bg-white text-emerald-900 shadow-sm font-semibold transition";
    btnParks.className = "py-1.5 px-2 rounded-md text-slate-600 hover:text-slate-900 transition";
  } else {
    btnParks.className = "py-1.5 px-2 rounded-md bg-white text-emerald-900 shadow-sm font-semibold transition";
    btnSites.className = "py-1.5 px-2 rounded-md text-slate-600 hover:text-slate-900 transition";
  }
  updateCounts();
  renderResultsList();
  if (rerender) renderMapMarkers(false);
}

function openModal(type) {
  const backdrop = document.getElementById("modal-backdrop");
  const title = document.getElementById("modal-title");
  const loginBody = document.getElementById("modal-body-login");
  const mapBody = document.getElementById("modal-body-map");

  if (type === "map") {
    title.textContent = "Google Maps JavaScript API Settings";
    loginBody.classList.add("hidden");
    mapBody.classList.remove("hidden");
  } else {
    title.textContent = "Sign in with Google IdP";
    mapBody.classList.add("hidden");
    loginBody.classList.remove("hidden");
  }
  backdrop.classList.remove("hidden");
}

function closeModal() {
  document.getElementById("modal-backdrop")?.classList.add("hidden");
}

function showLoading(visible) {
  const overlay = document.getElementById("map-loading-overlay");
  if (!overlay) return;
  if (visible) overlay.classList.remove("hidden");
  else overlay.classList.add("hidden");
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

document.addEventListener("DOMContentLoaded", async () => {
  await initMap();
  await loadInitialData();

  // Sidebar mobile toggle
  document.getElementById("btn-toggle-sidebar")?.addEventListener("click", () => {
    const sb = document.getElementById("sidebar-panel");
    sb?.classList.toggle("-translate-x-full");
  });

  // View Mode buttons
  document.getElementById("mode-campsites")?.addEventListener("click", () => setViewMode("campsites", true));
  document.getElementById("mode-parks")?.addEventListener("click", () => setViewMode("parks", true));

  // Sub-tabs (Filters vs Results List)
  const tabFilters = document.getElementById("tab-btn-filters");
  const tabResults = document.getElementById("tab-btn-results");
  const panelFilters = document.getElementById("tab-panel-filters");
  const panelResults = document.getElementById("tab-panel-results");

  tabFilters?.addEventListener("click", () => {
    tabFilters.className = "flex-1 py-2.5 border-b-2 border-emerald-700 text-emerald-800 bg-emerald-50/40";
    tabResults.className = "flex-1 py-2.5 border-b-2 border-transparent hover:text-slate-900";
    panelFilters.classList.remove("hidden");
    panelResults.classList.add("hidden");
  });

  tabResults?.addEventListener("click", () => {
    tabResults.className = "flex-1 py-2.5 border-b-2 border-emerald-700 text-emerald-800 bg-emerald-50/40";
    tabFilters.className = "flex-1 py-2.5 border-b-2 border-transparent hover:text-slate-900";
    panelResults.classList.remove("hidden");
    panelFilters.classList.add("hidden");
  });

  // Quick filter chips
  document.querySelectorAll(".quick-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const chipKey = btn.getAttribute("data-chip");
      if (chipKey === "favorites_only" && !state.user) {
        openModal("login");
        return;
      }
      state.chips[chipKey] = !state.chips[chipKey];
      if (state.chips[chipKey]) {
        btn.classList.add("bg-emerald-700", "text-white", "border-emerald-700");
        btn.classList.remove("bg-white", "text-slate-700", "bg-amber-50/60", "text-amber-900");
      } else {
        btn.classList.remove("bg-emerald-700", "text-white", "border-emerald-700");
        btn.classList.add("bg-white", "text-slate-700");
      }
      if (state.viewMode !== "campsites") setViewMode("campsites", false);
      fetchAndRenderCampsites(true);
    });
  });

  // Search box
  const searchInput = document.getElementById("filter-search");
  const clearSearchBtn = document.getElementById("btn-clear-search");
  searchInput?.addEventListener("input", () => {
    if (searchInput.value) clearSearchBtn?.classList.remove("hidden");
    else clearSearchBtn?.classList.add("hidden");
    if (state.viewMode !== "campsites") setViewMode("campsites", false);
    scheduleFilterRefresh(false);
  });
  clearSearchBtn?.addEventListener("click", () => {
    searchInput.value = "";
    clearSearchBtn.classList.add("hidden");
    fetchAndRenderCampsites(false);
  });

  // Select dropdowns
  [
    "filter-region",
    "filter-park-type",
    "filter-park",
    "filter-county",
    "filter-unit-type",
    "filter-site-type",
    "filter-shade",
    "filter-50amp",
  ].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", () => {
      if (state.viewMode !== "campsites") setViewMode("campsites", false);
      fetchAndRenderCampsites(true);
    });
  });

  // Sliders
  const padSlider = document.getElementById("filter-pad-length");
  const padLabel = document.getElementById("label-pad-length");
  padSlider?.addEventListener("input", () => {
    const val = parseInt(padSlider.value, 10);
    if (padLabel) padLabel.textContent = val > 0 ? `${val}+ ft` : "Any";
    scheduleFilterRefresh(false);
  });

  const peopleSlider = document.getElementById("filter-min-people");
  const peopleLabel = document.getElementById("label-min-people");
  peopleSlider?.addEventListener("input", () => {
    const val = parseInt(peopleSlider.value, 10);
    if (peopleLabel) peopleLabel.textContent = val > 0 ? `${val}+ campers` : "Any";
    scheduleFilterRefresh(false);
  });

  // Reset filters
  document.getElementById("btn-reset-filters")?.addEventListener("click", () => {
    if (searchInput) searchInput.value = "";
    clearSearchBtn?.classList.add("hidden");
    [
      "filter-region",
      "filter-park-type",
      "filter-park",
      "filter-county",
      "filter-unit-type",
      "filter-site-type",
      "filter-shade",
      "filter-50amp",
    ].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.value = "";
    });
    if (padSlider) padSlider.value = "0";
    if (padLabel) padLabel.textContent = "Any";
    if (peopleSlider) peopleSlider.value = "0";
    if (peopleLabel) peopleLabel.textContent = "Any";

    Object.keys(state.chips).forEach((k) => (state.chips[k] = false));
    document.querySelectorAll(".quick-chip").forEach((btn) => {
      btn.classList.remove("bg-emerald-700", "text-white", "border-emerald-700");
      btn.classList.add("bg-white", "text-slate-700");
    });

    fetchAndRenderCampsites(true);
  });

  // Fit bounds button
  document.getElementById("btn-reset-bounds")?.addEventListener("click", () => {
    renderMapMarkers(true);
  });

  // Detail drawer actions
  document.getElementById("btn-close-drawer")?.addEventListener("click", () => {
    document.getElementById("site-detail-drawer")?.classList.add("hidden");
  });
  document.getElementById("btn-favorite-site")?.addEventListener("click", toggleSelectedFavorite);
  document.getElementById("btn-save-note")?.addEventListener("click", saveSelectedSiteNote);
  document.getElementById("btn-filter-this-park")?.addEventListener("click", () => {
    if (!state.selectedSite) return;
    const parkSelect = document.getElementById("filter-park");
    if (parkSelect) parkSelect.value = state.selectedSite.park;
    fetchAndRenderCampsites(true);
  });

  // Login & Map settings modals
  document.getElementById("btn-open-login")?.addEventListener("click", () => openModal("login"));
  document.getElementById("btn-map-settings")?.addEventListener("click", () => openModal("map"));
  document.getElementById("btn-close-modal")?.addEventListener("click", closeModal);
  document.getElementById("modal-backdrop")?.addEventListener("click", (e) => {
    if (e.target.id === "modal-backdrop") closeModal();
  });

  // Apply runtime Google Maps API key
  document.getElementById("btn-apply-gmaps-key")?.addEventListener("click", () => {
    const val = document.getElementById("input-runtime-gmaps-key")?.value?.trim() || "";
    if (val) {
      localStorage.setItem("mn_explorer_gmaps_key", val);
    } else {
      localStorage.removeItem("mn_explorer_gmaps_key");
    }
    window.location.reload();
  });

  document.getElementById("btn-clear-gmaps-key")?.addEventListener("click", () => {
    localStorage.removeItem("mn_explorer_gmaps_key");
    window.location.reload();
  });

  // Sheet sync button
  document.getElementById("btn-sync-sheet")?.addEventListener("click", triggerGoogleSheetSync);
});
