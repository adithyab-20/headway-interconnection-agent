// Smooth, sharp map motion.
//
// Out of the box, Leaflet zooms by stretching a picture of the map and only redraws it once
// the zoom has finished: for a moment the dots and borders are blurry and swollen, then they
// snap back. This map has only a few hundred shapes, so it can afford to redraw on every
// frame instead. Every zoom (wheel, trackpad, buttons, keys, double-click) also eases towards
// where it's heading, rather than jumping a whole level at a time.
//
// It reaches into a few of Leaflet's internal methods (the ones its own flyTo uses), pinned
// by the exact Leaflet version in package-lock.json.

import type * as Leaflet from "leaflet";

type Inner = Leaflet.Map & {
  _move(center: Leaflet.LatLng, zoom: number): Inner;
  _moveStart(zoomChanged: boolean, noMoveStart: boolean): Inner;
  _moveEnd(zoomChanged: boolean): Inner;
  _stop(): Inner;
  _limitZoom(zoom: number): number;
  _getCenterOffset(center: Leaflet.LatLng): Leaflet.Point;
  _tryAnimatedZoom(center: Leaflet.LatLng, zoom: number, options?: { animate?: boolean }): boolean;
  _getBoundsCenterZoom(bounds: Leaflet.LatLngBoundsExpression, options: Leaflet.FitBoundsOptions): { center: Leaflet.LatLng; zoom: number };
  _flyToFrame: number;
};

// How quickly a zoom settles: about two thirds of the way there every SETTLE_MS.
const SETTLE_MS = 90;
// Zoom levels per pixel of wheel movement. A trackpad pinch reports much smaller movements.
const PER_PIXEL = 0.0045;
const PER_PIXEL_PINCH = 0.012;

export function smoothMotion(map: Leaflet.Map): void {
  const m = map as Inner;
  let glide: { zoom: number; at: Leaflet.Point; ll: Leaflet.LatLng; last: number; frame: number } | null = null;

  // Redraw everything whenever the view moves, so nothing is ever shown stretched.
  map.on("move", () => m.fire("viewreset"));

  // The centre that keeps `ll` under the screen point `at` at this zoom.
  const centreFor = (ll: Leaflet.LatLng, at: Leaflet.Point, zoom: number) =>
    m.unproject(m.project(ll, zoom).subtract(at.subtract(m.getSize().divideBy(2))), zoom);

  const step = (now: number) => {
    const g = glide;
    if (!g) return;
    const dt = g.last < 0 ? 16 : Math.min(Math.max(now - g.last, 0), 50);
    g.last = now;
    const from = m.getZoom();
    const done = Math.abs(g.zoom - from) < 0.002;
    const zoom = done ? g.zoom : from + (g.zoom - from) * (1 - Math.exp(-dt / SETTLE_MS));
    m._move(centreFor(g.ll, g.at, zoom), zoom);
    if (done) {
      glide = null;
      m._moveEnd(true);
    } else g.frame = requestAnimationFrame(step);
  };

  // Ease towards `zoom`, keeping the place under screen point `at` where it is. A new request
  // while one is under way just changes where it's heading, so quick wheel turns add up.
  const zoomAround = (zoom: number, at: Leaflet.Point) => {
    zoom = m._limitZoom(zoom);
    const ll = m.containerPointToLatLng(at);
    if (glide) {
      Object.assign(glide, { zoom, at, ll });
      return;
    }
    if (Math.abs(zoom - m.getZoom()) < 0.002) return;
    m._stop();
    m._moveStart(true, false);
    glide = { zoom, at, ll, last: -1, frame: requestAnimationFrame(step) };
  };

  // Anything else that starts moving the map (a drag, a flight, a pinch) takes over.
  map.on("movestart", () => {
    if (!glide) return;
    cancelAnimationFrame(glide.frame);
    glide = null;
    m._moveEnd(true);
  });

  const heading = () => glide?.zoom ?? m.getZoom();
  const centre = () => m.getSize().divideBy(2);

  // setView, setZoom, setZoomAround, the keyboard and double-click all come through here.
  m._tryAnimatedZoom = (center, zoom, options) => {
    if (options?.animate === false) return false;
    const scale = m.getZoomScale(zoom, m.getZoom());
    const offset = m._getCenterOffset(center).divideBy(1 - 1 / scale);
    // The fixed point is far off screen: it's more of a journey than a zoom.
    if (!m.getSize().contains(offset)) {
      m.flyTo(center, zoom, { duration: 0.6 });
      return true;
    }
    zoomAround(zoom, centre().add(offset));
    return true;
  };
  Object.assign(map, {
    zoomIn: (delta = 1) => (zoomAround(heading() + delta, centre()), map),
    zoomOut: (delta = 1) => (zoomAround(heading() - delta, centre()), map),
  });

  map.getContainer().addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      const px = e.deltaY * (e.deltaMode === 1 ? 20 : e.deltaMode === 2 ? 400 : 1);
      zoomAround(heading() - px * (e.ctrlKey ? PER_PIXEL_PINCH : PER_PIXEL), m.mouseEventToContainerPoint(e));
    },
    { passive: false },
  );
}

// Going somewhere the reader picked. A long journey keeps Leaflet's flight, which pulls back
// to show where it's heading. A short one glides straight there: on a short hop that pull-back
// just makes the dots shrink and regrow and the names blink out and back.
export function travel(map: Leaflet.Map, center: Leaflet.LatLngExpression, zoom: number): void {
  const m = map as Inner;
  const to = toLatLng(m, center);
  const z0 = m.getZoom();
  zoom = m._limitZoom(zoom);
  const size = Math.max(m.getSize().x, m.getSize().y);
  const low = Math.min(z0, zoom);
  const far = m.project(m.getCenter(), low).distanceTo(m.project(to, low)) / size;
  if (far > 1) {
    m.flyTo(to, zoom, { duration: 0.9 });
    return;
  }
  const ms = Math.min(420 + far * 300 + Math.abs(zoom - z0) * 100, 800);
  const p0 = m.project(m.getCenter(), z0);
  const p1 = m.project(to, z0);
  const zooming = Math.abs(zoom - z0) > 0.001;
  m._stop();
  m._moveStart(zooming, false);
  const start = performance.now();
  const frame = (now: number) => {
    const t = Math.min(Math.max((now - start) / ms, 0), 1);
    const s = t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
    if (t < 1) {
      m._move(m.unproject(p0.add(p1.subtract(p0).multiplyBy(s)), z0), z0 + (zoom - z0) * s);
      // Kept where Leaflet keeps its own flight, so a drag or a new journey cancels this one.
      m._flyToFrame = requestAnimationFrame(frame);
    } else m._move(to, zoom)._moveEnd(zooming);
  };
  m._flyToFrame = requestAnimationFrame(frame);
}

export function travelToBounds(map: Leaflet.Map, bounds: Leaflet.LatLngBoundsExpression, options: Leaflet.FitBoundsOptions): void {
  const target = (map as Inner)._getBoundsCenterZoom(bounds, options);
  travel(map, target.center, target.zoom);
}

// A LatLng from any of the ways Leaflet accepts one, without importing Leaflet here.
function toLatLng(m: Inner, at: Leaflet.LatLngExpression): Leaflet.LatLng {
  return m.unproject(m.project(at, 0), 0);
}
