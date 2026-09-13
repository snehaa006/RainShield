/** Small numeric helpers shared by the synthetic data source and risk engine. */

export const clamp = (value: number, min = 0, max = 1) =>
  Math.min(max, Math.max(min, value));

export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

export const logistic = (x: number) => 1 / (1 + Math.exp(-x));

/** Deterministic PRNG so every reload renders the identical demo region. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Smooth value noise on a lattice — stands in for a real DEM / rainfall field. */
export function valueNoise(x: number, y: number, seed: number): number {
  const corner = (ix: number, iy: number) =>
    mulberry32(ix * 73856093 + iy * 19349663 + seed * 83492791)();
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const fx = x - x0;
  const fy = y - y0;
  const sx = fx * fx * (3 - 2 * fx);
  const sy = fy * fy * (3 - 2 * fy);
  const top = lerp(corner(x0, y0), corner(x0 + 1, y0), sx);
  const bottom = lerp(corner(x0, y0 + 1), corner(x0 + 1, y0 + 1), sx);
  return lerp(top, bottom, sy);
}

/** Layered value noise, returns 0-1. */
export function fbm(x: number, y: number, seed: number, octaves = 3): number {
  let value = 0;
  let amplitude = 0.5;
  let total = 0;
  let frequency = 1;
  for (let i = 0; i < octaves; i += 1) {
    value += valueNoise(x * frequency, y * frequency, seed + i) * amplitude;
    total += amplitude;
    amplitude *= 0.5;
    frequency *= 2;
  }
  return value / total;
}

/** Interpolate a colour ramp defined by ascending breakpoints. */
export function sampleRamp(
  ramp: { value: number; color: string }[],
  value: number,
): string {
  if (value <= ramp[0].value) return ramp[0].color;
  for (let i = 1; i < ramp.length; i += 1) {
    if (value <= ramp[i].value) {
      const t = (value - ramp[i - 1].value) / (ramp[i].value - ramp[i - 1].value);
      return mixHex(ramp[i - 1].color, ramp[i].color, t);
    }
  }
  return ramp[ramp.length - 1].color;
}

function mixHex(a: string, b: string, t: number): string {
  const pa = parseInt(a.slice(1), 16);
  const pb = parseInt(b.slice(1), 16);
  const mix = (shift: number) => {
    const ca = (pa >> shift) & 0xff;
    const cb = (pb >> shift) & 0xff;
    return Math.round(lerp(ca, cb, t));
  };
  const [r, g, bl] = [mix(16), mix(8), mix(0)];
  return `#${((r << 16) | (g << 8) | bl).toString(16).padStart(6, '0')}`;
}
