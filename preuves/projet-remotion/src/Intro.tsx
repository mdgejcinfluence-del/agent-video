import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Charte } from "./charte";

const MOTS = ["erreurs", "de montage"];

export const Intro: React.FC<{ c: Charte; taille: number }> = ({ c, taille }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Une entrée vaut 0 avant « debut », puis monte vers 1 : en ressort ou en ligne droite.
  const entree = (debut: number) =>
    c.ressort
      ? spring({ frame: frame - debut, fps, config: { damping: 12, stiffness: 140 } })
      : interpolate(frame, [debut, debut + 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const chiffre = entree(6);
  const etiquette = entree(78);
  const barre = interpolate(frame, [100, durationInFrames - 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const halo = interpolate(frame, [0, durationInFrames], [-120, 160]);

  return (
    <AbsoluteFill style={{ background: c.fond, color: c.texte, fontFamily: c.police }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(900px circle at ${540 + halo}px 620px, ${c.accent}55, transparent 70%)`,
        }}
      />
      <AbsoluteFill style={{ padding: 90, justifyContent: "center" }}>
        <div
          style={{
            fontSize: taille * 2.1,
            fontWeight: 900,
            lineHeight: 0.8,
            color: c.accent,
            opacity: Math.min(1, chiffre * 1.5),
            transform: `scale(${0.4 + 0.6 * chiffre}) rotate(${(1 - chiffre) * -18}deg)`,
            transformOrigin: "left bottom",
          }}
        >
          3
        </div>
        {MOTS.map((mot, i) => {
          const p = entree(22 + i * 14);
          return (
            <div
              key={mot}
              style={{
                fontSize: taille,
                fontWeight: 900,
                lineHeight: 0.98,
                letterSpacing: "-0.04em",
                whiteSpace: "nowrap",
                opacity: Math.min(1, p * 1.5),
                transform: `translateY(${(1 - p) * 110}px)`,
              }}
            >
              {mot}
            </div>
          );
        })}
        <div
          style={{
            alignSelf: "flex-start",
            marginTop: 60,
            padding: "14px 34px",
            borderRadius: 999,
            background: c.accent2,
            color: c.fond,
            fontSize: 44,
            fontWeight: 800,
            letterSpacing: "0.08em",
            opacity: Math.min(1, etiquette * 1.5),
            transform: `scale(${0.6 + 0.4 * etiquette})`,
            transformOrigin: "left center",
          }}
        >
          ÉPISODE 04
        </div>
        <div style={{ marginTop: 90, height: 16, borderRadius: 8, background: `${c.texte}22`, overflow: "hidden" }}>
          <div style={{ width: `${barre * 100}%`, height: "100%", borderRadius: 8, background: c.accent2 }} />
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
