"use client";

import React, { useState } from "react";

type FolderBitsProps = {
  color?: string;
  size?: number;
  items?: React.ReactNode[];
  className?: string;
};

const darkenColor = (hex: string, percent: number): string => {
  let color = hex.startsWith("#") ? hex.slice(1) : hex;
  if (color.length === 3) {
    color = color
      .split("")
      .map((c) => c + c)
      .join("");
  }
  const num = parseInt(color, 16);
  let r = (num >> 16) & 0xff;
  let g = (num >> 8) & 0xff;
  let b = num & 0xff;
  r = Math.max(0, Math.min(255, Math.floor(r * (1 - percent))));
  g = Math.max(0, Math.min(255, Math.floor(g * (1 - percent))));
  b = Math.max(0, Math.min(255, Math.floor(b * (1 - percent))));
  return (
    "#" +
    ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1).toUpperCase()
  );
};

const getOpenTransform = (index: number): string => {
  if (index === 0) return "translate(-120%, -70%) rotate(-15deg)";
  if (index === 1) return "translate(10%, -70%) rotate(15deg)";
  if (index === 2) return "translate(-50%, -100%) rotate(5deg)";
  return "";
};

export default function FolderBits({
  color = "#5227FF",
  size = 1,
  items = [],
  className = "",
}: FolderBitsProps) {
  const maxItems = 3;
  const papers = items.slice(0, maxItems);
  while (papers.length < maxItems) {
    papers.push(null);
  }

  const [open, setOpen] = useState(false);
  const [paperOffsets, setPaperOffsets] = useState<{ x: number; y: number }[]>(
    Array.from({ length: maxItems }, () => ({ x: 0, y: 0 })),
  );

  const folderBackColor = darkenColor(color, 0.08);
  const paper1 = darkenColor("#ffffff", 0.1);
  const paper2 = darkenColor("#ffffff", 0.05);
  const paper3 = "#ffffff";

  const handleClick = () => {
    setOpen((prev) => !prev);
    if (open) {
      setPaperOffsets(Array.from({ length: maxItems }, () => ({ x: 0, y: 0 })));
    }
  };

  const handlePaperMouseMove = (
    e: React.MouseEvent<HTMLDivElement, MouseEvent>,
    index: number,
  ) => {
    if (!open) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    const offsetX = (e.clientX - centerX) * 0.15;
    const offsetY = (e.clientY - centerY) * 0.15;
    setPaperOffsets((prev) => {
      const next = [...prev];
      next[index] = { x: offsetX, y: offsetY };
      return next;
    });
  };

  const handlePaperMouseLeave = (
    _e: React.MouseEvent<HTMLDivElement, MouseEvent>,
    index: number,
  ) => {
    setPaperOffsets((prev) => {
      const next = [...prev];
      next[index] = { x: 0, y: 0 };
      return next;
    });
  };

  const scaleStyle: React.CSSProperties = { transform: `scale(${size})` };

  return (
    <div style={scaleStyle} className={className}>
      <div
        className={`group relative cursor-pointer transition-all duration-200 ease-in ${open ? "" : "hover:-translate-y-2"}`}
        style={
          {
            "--folder-color": color,
            "--folder-back-color": folderBackColor,
            "--paper-1": paper1,
            "--paper-2": paper2,
            "--paper-3": paper3,
            transform: open ? "translateY(-8px)" : undefined,
          } as React.CSSProperties
        }
        onClick={handleClick}
      >
        <div className="relative h-[82px] w-[116px] rounded-tr-[12px] rounded-br-[12px] rounded-bl-[12px] bg-[var(--folder-back-color)]">
          <span className="absolute bottom-[98%] left-0 h-[12px] w-[36px] rounded-tl-[6px] rounded-tr-[6px] bg-[var(--folder-back-color)]" />
          {papers.map((item, i) => {
            let width = "w-[88%]";
            let height = "h-[60%]";
            if (i === 0) {
              width = "w-[70%]";
              height = "h-[80%]";
            }
            if (i === 1) {
              width = "w-[80%]";
              height = open ? "h-[80%]" : "h-[70%]";
            }
            if (i === 2) {
              width = open ? "w-[90%]" : "w-[90%]";
              height = open ? "h-[80%]" : "h-[60%]";
            }

            const baseClasses = `absolute bottom-[12%] left-1/2 z-20 -translate-x-1/2 rounded-[12px] transition-all duration-300 ease-in-out ${width} ${height}`;
            const closedState = "translate-y-[12%] group-hover:translate-y-1";
            const openTransform = `${getOpenTransform(i)} translate(${paperOffsets[i]?.x ?? 0}px, ${paperOffsets[i]?.y ?? 0}px)`;

            return (
              <div
                key={i}
                onMouseMove={(e) => handlePaperMouseMove(e, i)}
                onMouseLeave={(e) => handlePaperMouseLeave(e, i)}
                className={`${baseClasses} ${open ? "hover:scale-110" : closedState}`}
                style={{
                  backgroundColor: i === 0 ? paper1 : i === 1 ? paper2 : paper3,
                  transform: open ? openTransform : undefined,
                }}
              >
                {item}
              </div>
            );
          })}
          <div
            className={`absolute inset-0 z-30 origin-bottom rounded-[8px_14px_14px_14px] bg-[var(--folder-color)] transition-all duration-300 ease-in-out ${
              open
                ? "[transform:skew(15deg)_scaleY(0.6)]"
                : "group-hover:[transform:skew(15deg)_scaleY(0.6)]"
            }`}
          />
          <div
            className={`absolute inset-0 z-20 origin-bottom rounded-[8px_14px_14px_14px] bg-[var(--folder-color)] transition-all duration-300 ease-in-out opacity-60 ${
              open
                ? "[transform:skew(-15deg)_scaleY(0.6)]"
                : "group-hover:[transform:skew(-15deg)_scaleY(0.6)]"
            }`}
          />
        </div>
      </div>
    </div>
  );
}
