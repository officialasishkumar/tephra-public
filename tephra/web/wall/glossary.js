// Plain-language copy for a first-time viewer: how to read the Wall, the glossary of the
// aviation terms on screen (docs/UI-DESIGN.md 7.3a), the plain line under each source
// column head, and the scope line for volcanic gases. Strings only; panels build the DOM.

export const HOW_TO_READ = [
  "The map shows the official ash areas from the SIGMETs and VAAs, and TEPHRA's cautious area, which is never smaller than the official one.",
  "The right rail compares what each source says about the selected volcano and lists where they disagree.",
  "The flight list shows aircraft heading into an area.",
  "The Desk is where a person approves or rejects each advisory. Nothing is sent to a real system.",
  "REPLAY means the data was recorded or reconstructed earlier; it is not live.",
  "Times end in Z, which means UTC.",
];

export const GLOSSARY = [
  ["SIGMET", "A warning issued for one flight information region by its meteorological watch office. For ash it is a VA SIGMET."],
  ["VAA and VAAC", "The volcanic ash advisory, and the advisory centre that issues it (Tokyo, Darwin)."],
  ["VONA", "The volcano observatory's notice for aviation."],
  ["FIR", "Flight information region: a block of airspace with one air traffic service."],
  ["FL", "Flight level, in hundreds of feet. FL350 is about 35,000 ft."],
  ["Z", "UTC. 06:30Z is 06:30 UTC."],
  ["ADS-B", "Positions that aircraft broadcast, collected here from adsb.lol. A gap in coverage is not an empty sky."],
  ["RFA proxy flight", "Ring of Fire Air (RFA) is a fictional airline. Each RFA flight number stands in for a real aircraft seen on ADS-B."],
  ["NO MODEL", "No AI model is connected. Code does every step, and code templates write the text a model would."],
  ["REPLAY and reconstructed", "REPLAY plays recorded real feeds and is labelled for the whole session. A reconstructed case was rebuilt after the event from archived bulletins."],
  ["Affected area", "The area an official product says the ash covers."],
  ["Policy A (illustrative)", "An example operator policy: every margin, minimum and threshold TEPHRA applies, with its reason. It is not a real airline's policy."],
];

// The plain meaning shown as a second line under each source column head (7.12).
export const KIND_PLAIN = {
  VONA: "volcano observatory notice",
  SIGMET: "met office warning for the airspace",
  VAA: "ash advisory centre",
};

export const GASES_SCOPE = "SO2 is not ash. Volcanic gases may also be undesirable to fly through; TEPHRA does not model them.";
export const GASES_SCOPE_SHORT = "SO2 is not ash; gases not modelled";
