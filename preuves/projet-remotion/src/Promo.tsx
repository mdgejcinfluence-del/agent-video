import React from "react";
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

// L'offre, telle qu'elle est écrite dans la demande. Rien d'autre n'apparaît à l'image.
export type Offre = { produit: string; detail: string; format: string; prix: string; consigne: string; photo: string };

const IVOIRE = "#FFF8EC";
const VERT = "#0B4F3A";
const JAUNE = "#FFC83D";

export const Promo: React.FC<{ offre: Offre }> = ({ offre }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const ressort = (debut: number) => spring({ frame: frame - debut, fps, config: { damping: 13, stiffness: 130 } });

  const zoom = interpolate(frame, [0, durationInFrames], [1, 1.05]);
  const titre = ressort(8);
  const detail = ressort(20);
  const format = ressort(34);
  const prix = ressort(62);
  const consigne = ressort(118);

  return (
    <AbsoluteFill style={{ background: IVOIRE, fontFamily: "Inter Tight", color: VERT }}>
      {/* La photo du produit, entière et sans retouche : seul un zoom lent l'anime. */}
      <Img
        src={staticFile(offre.photo)}
        style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${zoom})`, transformOrigin: "50% 35%" }}
      />
      <AbsoluteFill style={{ background: `linear-gradient(180deg, ${IVOIRE} 0%, ${IVOIRE}E6 22%, ${IVOIRE}00 40%)` }} />

      <div style={{ position: "absolute", left: 90, right: 90, top: 150 }}>
        <div
          style={{
            fontSize: 104,
            fontWeight: 900,
            letterSpacing: "-0.04em",
            lineHeight: 1,
            opacity: Math.min(1, titre * 1.5),
            transform: `translateY(${(1 - titre) * 70}px)`,
          }}
        >
          {offre.produit}
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <div
              style={{
                fontFamily: "Instrument Serif",
                fontStyle: "italic",
                fontSize: 136,
                lineHeight: 0.95,
                opacity: Math.min(1, detail * 1.5),
                transform: `translateY(${(1 - detail) * 70}px)`,
              }}
            >
              {offre.detail}
            </div>
            <div style={{ marginTop: 14, fontSize: 50, fontWeight: 600, opacity: format }}>{offre.format}</div>
          </div>
          <div
            style={{
              padding: "14px 36px 18px",
              borderRadius: 28,
              background: JAUNE,
              fontSize: 80,
              fontWeight: 900,
              letterSpacing: "-0.03em",
              whiteSpace: "nowrap",
              boxShadow: "0 18px 40px rgba(11,79,58,.28)",
              opacity: Math.min(1, prix * 1.6),
              transform: `scale(${0.5 + 0.5 * prix}) rotate(${-4 + (1 - prix) * -14}deg)`,
            }}
          >
            {offre.prix}
          </div>
        </div>
        {/* La consigne reste en haut : rien ne passe devant le produit, rien dans la zone basse des applications. */}
        <div
          style={{
            marginTop: 34,
            height: 104,
            borderRadius: 52,
            background: VERT,
            color: IVOIRE,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 54,
            fontWeight: 800,
            boxShadow: "0 16px 36px rgba(11,79,58,.3)",
            opacity: Math.min(1, consigne * 1.5),
            transform: `scale(${0.85 + 0.15 * consigne})`,
          }}
        >
          {offre.consigne}
        </div>
      </div>
    </AbsoluteFill>
  );
};
