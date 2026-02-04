import * as THREE from "three";

type TextureResult = THREE.Texture | null;

const textureCache = new Map<string, THREE.Texture>();

function getCachedTexture(
  key: string,
  create: () => TextureResult,
): TextureResult {
  const cached = textureCache.get(key);
  if (cached) return cached;

  const created = create();
  if (!created) return null;

  textureCache.set(key, created);
  return created;
}

function createCanvasTexture(options: {
  width: number;
  height: number;
  colorSpace?: THREE.ColorSpace;
  wrap?: THREE.Wrapping;
  repeat?: readonly [number, number];
  draw: (ctx: CanvasRenderingContext2D, width: number, height: number) => void;
}): TextureResult {
  if (typeof document === "undefined") return null;

  const canvas = document.createElement("canvas");
  canvas.width = options.width;
  canvas.height = options.height;

  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  options.draw(ctx, options.width, options.height);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  texture.colorSpace = options.colorSpace ?? THREE.NoColorSpace;

  const wrap = options.wrap ?? THREE.RepeatWrapping;
  texture.wrapS = wrap;
  texture.wrapT = wrap;

  if (options.repeat) {
    texture.repeat.set(options.repeat[0], options.repeat[1]);
  }

  texture.anisotropy = 4;
  return texture;
}

function createNormalMapFromHeight(options: {
  width: number;
  height: number;
  heightAt: (x: number, y: number) => number;
  strength?: number;
  repeat?: readonly [number, number];
}): TextureResult {
  if (typeof document === "undefined") return null;

  const canvas = document.createElement("canvas");
  canvas.width = options.width;
  canvas.height = options.height;

  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  const image = ctx.createImageData(options.width, options.height);
  const strength = options.strength ?? 2.2;

  const clamp01 = (value: number) => Math.min(1, Math.max(0, value));

  for (let y = 0; y < options.height; y += 1) {
    for (let x = 0; x < options.width; x += 1) {
      const hL = options.heightAt((x - 1 + options.width) % options.width, y);
      const hR = options.heightAt((x + 1) % options.width, y);
      const hD = options.heightAt(x, (y - 1 + options.height) % options.height);
      const hU = options.heightAt(x, (y + 1) % options.height);

      const dx = (hR - hL) * strength;
      const dy = (hU - hD) * strength;

      const nx = -dx;
      const ny = -dy;
      const nz = 1;
      const len = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;

      const r = clamp01((nx / len) * 0.5 + 0.5);
      const g = clamp01((ny / len) * 0.5 + 0.5);
      const b = clamp01((nz / len) * 0.5 + 0.5);

      const idx = (y * options.width + x) * 4;
      image.data[idx] = Math.round(r * 255);
      image.data[idx + 1] = Math.round(g * 255);
      image.data[idx + 2] = Math.round(b * 255);
      image.data[idx + 3] = 255;
    }
  }

  ctx.putImageData(image, 0, 0);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  texture.colorSpace = THREE.NoColorSpace;
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  if (options.repeat) {
    texture.repeat.set(options.repeat[0], options.repeat[1]);
  }
  texture.anisotropy = 4;
  return texture;
}

function seededRng(seed: number): () => number {
  return () => {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function getLeafTexture(): TextureResult {
  return getCachedTexture("leafTexture.v2", () =>
    createCanvasTexture({
      width: 128,
      height: 128,
      colorSpace: THREE.SRGBColorSpace,
      wrap: THREE.ClampToEdgeWrapping,
      draw: (ctx, width, height) => {
        const rng = seededRng(42);
        ctx.clearRect(0, 0, width, height);

        const cx = width / 2;
        const cy = height / 2;

        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(-Math.PI / 2);

        const leafW = width * 0.38;
        const leafH = height * 0.56;

        ctx.beginPath();
        ctx.moveTo(0, -leafH);
        ctx.bezierCurveTo(
          leafW * 0.9,
          -leafH * 0.75,
          leafW * 1.2,
          -leafH * 0.05,
          0,
          leafH,
        );
        ctx.bezierCurveTo(
          -leafW * 1.2,
          -leafH * 0.05,
          -leafW * 0.9,
          -leafH * 0.75,
          0,
          -leafH,
        );
        ctx.closePath();

        const fill = ctx.createLinearGradient(0, -leafH, 0, leafH);
        fill.addColorStop(0, "rgba(255,255,255,0.92)");
        fill.addColorStop(0.55, "rgba(255,255,255,0.78)");
        fill.addColorStop(1, "rgba(255,255,255,0.0)");

        ctx.shadowColor = "rgba(255,255,255,0.08)";
        ctx.shadowBlur = 10;
        ctx.fillStyle = fill;
        ctx.fill();

        // Midrib + veins (subtle highlights).
        ctx.shadowBlur = 0;
        ctx.lineCap = "round";
        ctx.strokeStyle = "rgba(255,255,255,0.22)";
        ctx.lineWidth = Math.max(1, Math.round(width * 0.012));
        ctx.beginPath();
        ctx.moveTo(0, -leafH * 0.92);
        ctx.lineTo(0, leafH * 0.85);
        ctx.stroke();

        ctx.strokeStyle = "rgba(255,255,255,0.14)";
        ctx.lineWidth = Math.max(1, Math.round(width * 0.006));
        for (let i = 0; i < 6; i += 1) {
          const t = (i + 1) / 7;
          const y = -leafH * 0.7 + t * leafH * 1.25;
          const x = leafW * (0.15 + t * 0.55);
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.quadraticCurveTo(x * 0.5, y + leafH * 0.05, x, y + leafH * 0.14);
          ctx.stroke();
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.quadraticCurveTo(
            -x * 0.5,
            y + leafH * 0.05,
            -x,
            y + leafH * 0.14,
          );
          ctx.stroke();
        }

        // Edge softening + micro texture
        ctx.globalCompositeOperation = "source-atop";
        const speckleCount = 420;
        for (let i = 0; i < speckleCount; i += 1) {
          const x = (rng() - 0.5) * leafW * 2.2;
          const y = (rng() - 0.5) * leafH * 2.2;
          const r = 0.4 + rng() * 1.0;
          ctx.fillStyle = `rgba(255,255,255,${0.025 + rng() * 0.06})`;
          ctx.beginPath();
          ctx.arc(x, y, r, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.globalCompositeOperation = "source-over";

        ctx.restore();
      },
    }),
  );
}

export function getBarkTextures(): {
  map: TextureResult;
  normalMap: TextureResult;
} {
  const map = getCachedTexture("bark.map.v2", () => {
    const rng = seededRng(1337);
    return createCanvasTexture({
      width: 384,
      height: 384,
      colorSpace: THREE.SRGBColorSpace,
      repeat: [2, 6],
      draw: (ctx, width, height) => {
        ctx.fillStyle = "#2a201b";
        ctx.fillRect(0, 0, width, height);

        // Vertical ridges (bark grain)
        for (let x = 0; x < width; x += 1) {
          const ridge = Math.sin((x / width) * Math.PI * 18) * 0.24;
          const ridge2 =
            Math.sin((x / width) * Math.PI * 6 + (rng() - 0.5) * 0.4) * 0.18;
          const noise = (rng() - 0.5) * 0.22;
          const v = Math.min(1, Math.max(0, 0.56 + ridge + ridge2 + noise));
          const c = Math.round(52 + v * 92);
          const g = Math.round(c * 0.77);
          const b = Math.round(c * 0.61);
          ctx.fillStyle = `rgb(${c}, ${g}, ${b})`;
          ctx.fillRect(x, 0, 1, height);
        }

        // Longitudinal cracks
        ctx.globalAlpha = 0.22;
        ctx.strokeStyle = "rgba(0,0,0,0.45)";
        ctx.lineWidth = 1.2;
        for (let i = 0; i < 38; i += 1) {
          const x = rng() * width;
          const wobble = 6 + rng() * 14;
          ctx.beginPath();
          ctx.moveTo(x, -10);
          for (let y = 0; y <= height + 10; y += 18) {
            const dx =
              Math.sin((y / height) * Math.PI * 2 + rng() * 6) * wobble;
            ctx.lineTo(x + dx, y);
          }
          ctx.stroke();
        }

        ctx.globalAlpha = 0.18;
        // Knots / bumps
        for (let i = 0; i < 22; i += 1) {
          const x = rng() * width;
          const y = rng() * height;
          const r = 10 + rng() * 24;
          const knot = ctx.createRadialGradient(x, y, 1, x, y, r);
          knot.addColorStop(0, "rgba(170,140,112,0.22)");
          knot.addColorStop(0.55, "rgba(55,40,30,0.12)");
          knot.addColorStop(1, "rgba(0,0,0,0)");
          ctx.fillStyle = knot;
          ctx.beginPath();
          ctx.arc(x, y, r, 0, Math.PI * 2);
          ctx.fill();
        }

        // Micro speckles
        ctx.globalAlpha = 0.24;
        for (let i = 0; i < 5200; i += 1) {
          const x = Math.floor(rng() * width);
          const y = Math.floor(rng() * height);
          const r = 1 + Math.floor(rng() * 2);
          const c = 40 + Math.floor(rng() * 70);
          ctx.fillStyle = `rgb(${c}, ${Math.round(c * 0.75)}, ${Math.round(c * 0.62)})`;
          ctx.beginPath();
          ctx.arc(x, y, r, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.globalAlpha = 1;
      },
    });
  });

  const normalMap = getCachedTexture("bark.normal.v2", () => {
    const width = 256;
    const height = 256;
    const rng = seededRng(4242);
    const heightMap = new Float32Array(width * height);

    const knots = Array.from({ length: 10 }, () => ({
      x: rng() * width,
      y: rng() * height,
      r: 18 + rng() * 34,
      a: 0.35 + rng() * 0.35,
    }));

    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const xf = x / width;
        const yf = y / height;

        const ridge = Math.sin(xf * Math.PI * 18) * 0.55;
        const ridge2 =
          Math.sin(xf * Math.PI * 6 + Math.sin(yf * Math.PI * 2) * 0.8) * 0.25;
        const warp = Math.sin(yf * Math.PI * 10 + xf * Math.PI * 2) * 0.18;
        const grain = (rng() - 0.5) * 0.3;

        let v = ridge + ridge2 + warp + grain;

        for (const knot of knots) {
          const dx = x - knot.x;
          const dy = y - knot.y;
          const d2 = dx * dx + dy * dy;
          const r2 = knot.r * knot.r;
          if (d2 > r2) continue;
          const t = 1 - d2 / r2;
          v += t * knot.a;
        }

        heightMap[y * width + x] = v;
      }
    }

    return createNormalMapFromHeight({
      width,
      height,
      repeat: [2, 6],
      strength: 2.35,
      heightAt: (x, y) => heightMap[y * width + x] ?? 0,
    });
  });

  return { map, normalMap };
}

export function getGroundTextures(): {
  map: TextureResult;
  normalMap: TextureResult;
  emissiveMap: TextureResult;
} {
  const map = getCachedTexture("ground.map.v2", () => {
    const rng = seededRng(2025);
    return createCanvasTexture({
      width: 384,
      height: 384,
      colorSpace: THREE.SRGBColorSpace,
      repeat: [8, 8],
      draw: (ctx, width, height) => {
        ctx.fillStyle = "#2f4b2a";
        ctx.fillRect(0, 0, width, height);

        // Grass & soil grain
        ctx.globalAlpha = 0.6;
        for (let i = 0; i < 9000; i += 1) {
          const x = Math.floor(rng() * width);
          const y = Math.floor(rng() * height);
          const r = 1 + Math.floor(rng() * 2);
          const g = 70 + Math.floor(rng() * 110);
          const rr = 30 + Math.floor(rng() * 60);
          ctx.fillStyle = `rgb(${rr}, ${g}, ${Math.round(rr * 0.7)})`;
          ctx.beginPath();
          ctx.arc(x, y, r, 0, Math.PI * 2);
          ctx.fill();
        }

        // Soil patches
        ctx.globalAlpha = 0.28;
        for (let i = 0; i < 520; i += 1) {
          const x = rng() * width;
          const y = rng() * height;
          const w = 6 + rng() * 26;
          const h = 4 + rng() * 18;
          ctx.fillStyle = `rgba(70, 52, 40, ${0.35 + rng() * 0.3})`;
          ctx.beginPath();
          ctx.ellipse(x, y, w, h, rng() * Math.PI, 0, Math.PI * 2);
          ctx.fill();
        }

        // Moss blooms
        ctx.globalAlpha = 0.28;
        for (let i = 0; i < 180; i += 1) {
          const x = rng() * width;
          const y = rng() * height;
          const r = 10 + rng() * 32;
          const moss = ctx.createRadialGradient(x, y, 0, x, y, r);
          moss.addColorStop(0, "rgba(92, 190, 105, 0.55)");
          moss.addColorStop(0.55, "rgba(52, 132, 70, 0.18)");
          moss.addColorStop(1, "rgba(0, 0, 0, 0)");
          ctx.fillStyle = moss;
          ctx.beginPath();
          ctx.arc(x, y, r, 0, Math.PI * 2);
          ctx.fill();
        }

        ctx.globalAlpha = 1;
      },
    });
  });

  const emissiveMap = getCachedTexture("ground.emissive.v1", () => {
    const rng = seededRng(9001);
    return createCanvasTexture({
      width: 384,
      height: 384,
      colorSpace: THREE.SRGBColorSpace,
      repeat: [8, 8],
      draw: (ctx, width, height) => {
        ctx.fillStyle = "#000000";
        ctx.fillRect(0, 0, width, height);

        // Fluorescent moss specks
        for (let i = 0; i < 720; i += 1) {
          const x = rng() * width;
          const y = rng() * height;
          const r = 1.2 + rng() * 3.4;
          const hue = 160 + rng() * 40;
          const alpha = 0.08 + rng() * 0.18;
          ctx.fillStyle = `hsla(${hue}, 95%, 68%, ${alpha})`;
          ctx.beginPath();
          ctx.arc(x, y, r, 0, Math.PI * 2);
          ctx.fill();
        }

        // A few larger glow blooms
        for (let i = 0; i < 34; i += 1) {
          const x = rng() * width;
          const y = rng() * height;
          const r = 12 + rng() * 26;
          const grad = ctx.createRadialGradient(x, y, 0, x, y, r);
          grad.addColorStop(0, "rgba(34, 211, 238, 0.25)");
          grad.addColorStop(0.5, "rgba(34, 211, 238, 0.08)");
          grad.addColorStop(1, "rgba(0, 0, 0, 0)");
          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.arc(x, y, r, 0, Math.PI * 2);
          ctx.fill();
        }
      },
    });
  });

  const normalMap = getCachedTexture("ground.normal.v2", () => {
    const width = 256;
    const height = 256;
    const rng = seededRng(77);
    const heightMap = new Float32Array(width * height);

    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const xf = x / width;
        const yf = y / height;
        const n1 = (rng() - 0.5) * 0.9;
        const n2 = Math.sin(xf * Math.PI * 18) * 0.18;
        const n3 = Math.sin(yf * Math.PI * 14) * 0.16;
        const n4 = Math.sin((xf + yf) * Math.PI * 10) * 0.12;
        heightMap[y * width + x] = n1 + n2 + n3 + n4;
      }
    }

    return createNormalMapFromHeight({
      width,
      height,
      repeat: [8, 8],
      strength: 1.35,
      heightAt: (x, y) => heightMap[y * width + x] ?? 0,
    });
  });

  return { map, normalMap, emissiveMap };
}
