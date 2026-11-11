import React from "react";
import "./police";
import { IntroCompositions } from "./IntroCompositions";
import { PromoCompositions } from "./PromoCompositions";

// Une série par fichier : l'intro du créateur d'un côté, la publicité du commerce de l'autre.
export const Root: React.FC = () => (
  <>
    <IntroCompositions />
    <PromoCompositions />
  </>
);
