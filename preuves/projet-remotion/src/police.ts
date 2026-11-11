// Charge les polices du dossier public/ avant le premier calcul d'image.
import { continueRender, delayRender, staticFile } from "remotion";

const polices: [string, string, FontFaceDescriptors][] = [
  ["Inter Tight", "InterTight.ttf", { weight: "100 900" }],
  ["Instrument Serif", "InstrumentSerif-Italic.ttf", { style: "italic" }],
  ["JetBrains Mono", "JetBrainsMono.ttf", { weight: "100 800" }],
];

const attente = delayRender("polices");
Promise.all(
  polices.map(([nom, fichier, options]) =>
    new FontFace(nom, `url(${staticFile(fichier)})`, options).load().then((p) => document.fonts.add(p)),
  ),
).then(() => continueRender(attente));
