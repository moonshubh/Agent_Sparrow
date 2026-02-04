export type MemoryImageSizing = {
  baseSrc: string;
  width?: number;
  height?: number;
};

export const parseDimensionValue = (value: unknown): number | undefined => {
  if (value === null || value === undefined) return undefined;
  if (typeof value === "number" && Number.isFinite(value) && value > 0) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number.parseInt(value, 10);
    if (Number.isFinite(parsed) && parsed > 0) return parsed;
  }
  return undefined;
};

const parseDimension = (value: string | null): number | undefined =>
  parseDimensionValue(value ?? undefined);

const decodeParams = (value: string): string =>
  value
    .replace(/&amp;/gi, "&")
    .replace(/&#38;/gi, "&")
    .replace(/&#x26;/gi, "&")
    .replace(/%26/gi, "&")
    .replace(/%3D/gi, "=");

export const parseMemoryImageSrc = (src: string): MemoryImageSizing => {
  if (!src) return { baseSrc: src };

  const hashIndex = src.lastIndexOf("#");
  const encodedHashIndex = src.lastIndexOf("%23");
  const fragmentIndex = Math.max(hashIndex, encodedHashIndex);
  if (fragmentIndex >= 0) {
    const fragmentOffset = fragmentIndex === hashIndex ? 1 : 3;
    const fragmentRaw = src.slice(fragmentIndex + fragmentOffset);
    const fragment = decodeParams(fragmentRaw);
    if (fragment.startsWith("w=")) {
      const params = new URLSearchParams(fragment);
      const width = parseDimension(params.get("w"));
      const height = parseDimension(params.get("h"));
      if (width && height) {
        return {
          baseSrc: src.slice(0, fragmentIndex),
          width,
          height,
        };
      }
    }
  }

  const queryIndex = src.indexOf("?");
  if (queryIndex >= 0) {
    const queryRaw = src.slice(queryIndex + 1);
    const query = decodeParams(queryRaw);
    const params = new URLSearchParams(query);
    const width = parseDimension(params.get("w"));
    const height = parseDimension(params.get("h"));
    if (width && height) {
      params.delete("w");
      params.delete("h");
      const remaining = params.toString();
      return {
        baseSrc: remaining
          ? `${src.slice(0, queryIndex)}?${remaining}`
          : src.slice(0, queryIndex),
        width,
        height,
      };
    }
  }

  return { baseSrc: src };
};

export const withSizeFragment = (
  baseSrc: string,
  width?: number,
  height?: number,
): string => {
  if (!width || !height) return baseSrc;
  const w = Math.round(width);
  const h = Math.round(height);
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) {
    return baseSrc;
  }
  const normalized = parseMemoryImageSrc(baseSrc).baseSrc;
  const [path, query = ""] = normalized.split("?");
  const params = new URLSearchParams(decodeParams(query));
  params.set("w", String(w));
  params.set("h", String(h));
  const queryString = params.toString();
  return queryString ? `${path}?${queryString}` : path;
};
