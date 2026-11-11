// La charte : tout ce qui fait qu'une animation ressemble à TA marque.
// Les compositions ne contiennent aucune couleur ni police en dur : elles lisent cet objet.
export type Charte = {
  fond: string;
  texte: string;
  accent: string;
  accent2: string;
  police: string;
  ressort: boolean; // true : entrées en ressort ; false : glissement linéaire
};

// Ce qu'on obtient quand la demande ne dit rien du style.
export const generique: Charte = {
  fond: "#FFFFFF",
  texte: "#111111",
  accent: "#3B82F6",
  accent2: "#3B82F6",
  police: "Arial",
  ressort: false,
};

// La charte donnée dans la demande écrite.
export const charte: Charte = {
  fond: "#0E1014",
  texte: "#F4F5F7",
  accent: "#8B5CF6",
  accent2: "#C6F432",
  police: "Inter Tight",
  ressort: true,
};
