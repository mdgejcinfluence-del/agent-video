import React from "react";
import { Composition } from "remotion";
import { format } from "./format";
import { Offre, Promo } from "./Promo";

// L'offre est écrite ici, une seule fois : on la change sans toucher à l'animation.
const karite: Offre = {
  produit: "Beurre de karité",
  detail: "fouetté",
  format: "Pot de 200 g",
  prix: "3 500 FCFA",
  consigne: "Commande par message",
  photo: "photo.jpg",
};

export const PromoCompositions: React.FC = () => (
  <>
    <Composition id="Promo" component={Promo} {...format} defaultProps={{ offre: karite }} />
  </>
);
