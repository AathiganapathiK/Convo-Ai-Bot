import React, { useEffect, useState } from "react";

const chevron = Array.from({ length: 9 }, (_, i) => {
  const r = Math.floor(i / 3), c = i % 3;
  return (c + Math.abs(r - 1)) * 90;
});

const ORBIT_ORDER = [0, 1, 2, 5, 8, 7, 6, 3];
const orbit = Array.from({ length: 9 }, (_, i) => {
  const k = ORBIT_ORDER.indexOf(i);
  return k === -1 ? null : k * 110;
});

const PATTERNS = {
  Drive: { delays: chevron, dur: 650, round: false },
  Dots: { delays: chevron, dur: 650, round: true },
  Orbit: { delays: orbit, dur: 950, round: false },
};

function LoaderGrid({ delays, dur, round }) {
  return (
    <span aria-hidden className="loader-grid-container">
      {delays.map((delay, index) => (
        <span
          key={index}
          className={`loader-grid-cell ${round ? "round" : ""}`}
          style={{
            opacity: delay === null ? 0.07 : 0.15,
            animation: delay === null ? "none" : `pixel-on ${dur}ms ease-in-out ${delay}ms infinite`,
          }}
        />
      ))}
    </span>
  );
}

function useElapsed() {
  const [ds, setDs] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setDs((d) => d + 1), 100);
    return () => clearInterval(t);
  }, []);
  const total = ds / 10;
  if (total < 60) return `${total.toFixed(1)}s`;
  return `${Math.floor(total / 60)}m ${(total % 60).toFixed(1)}s`;
}

export default function LoadingState({
  label,
  variant = "Drive",
  videoSrc = "/subway-surfers.mp4",
}) {
  const elapsed = useElapsed();
  const surfer = variant === "Surfer";
  const resolvedLabel = label ?? (surfer ? "Subway surfing" : "Churning");
  const [videoOk, setVideoOk] = useState(true);
  const { delays, dur, round } = PATTERNS[variant] ?? PATTERNS.Drive;

  const labelEl = <span className="loader-shimmer-label">{resolvedLabel}</span>;
  const elapsedEl = <span className="loader-elapsed-timer">{elapsed}</span>;

  if (surfer) {
    return (
      <div role="status" className="loader-status-container surfer-variant">
        <div className="loader-status-header">
          <LoaderGrid {...PATTERNS.Drive} />
          {labelEl}
          {elapsedEl}
        </div>

        <div className="loader-video-container">
          <div className="loader-video-aspect">
            {videoOk ? (
              <video
                src={videoSrc}
                autoPlay
                muted
                loop
                playsInline
                onError={() => setVideoOk(false)}
                className="loader-video-element"
              />
            ) : (
              <div className="loader-video-fallback">
                <LoaderGrid {...PATTERNS.Drive} />
                <span className="loader-fallback-text">Video unavailable</span>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div role="status" className="loader-status-container">
      <LoaderGrid delays={delays} dur={dur} round={round} />
      {labelEl}
      {elapsedEl}
    </div>
  );
}
