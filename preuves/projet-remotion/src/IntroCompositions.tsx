import React from "react";
import { Composition } from "remotion";
import { charte, generique } from "./charte";
import { format } from "./format";
import { Intro } from "./Intro";

export const IntroCompositions: React.FC = () => (
  <>
    {/* Premier jet : le titre à 200 px déborde du cadre (voir correction.md). */}
    <Composition id="IntroV1" component={Intro} {...format} defaultProps={{ c: charte, taille: 200 }} />
    <Composition id="Intro" component={Intro} {...format} defaultProps={{ c: charte, taille: 168 }} />
    <Composition id="IntroGenerique" component={Intro} {...format} defaultProps={{ c: generique, taille: 168 }} />
  </>
);
