// Plain-language copy for a first-time viewer: the glossary of the aviation terms on screen
// (docs/UI-REDESIGN.md R9.1), the plain meaning of each source kind, and the scope line for
// volcanic gases. Strings only; panels build the DOM.

export const GLOSSARY = [
  ["SIGMET", "A warning issued for one flight information region by its meteorological watch office. For ash it is a VA SIGMET."],
  ["VAA and VAAC", "The volcanic ash advisory, and the advisory centre that issues it (Tokyo, Darwin)."],
  ["VONA", "The volcano observatory's notice for aviation."],
  ["FIR", "Flight information region: a block of airspace with one air traffic service."],
  ["FL", "Flight level, in hundreds of feet. FL350 is about 35,000 ft."],
  ["Z", "UTC. 06:30Z is 06:30 UTC."],
  ["ADS-B", "Positions that aircraft broadcast, collected here from adsb.lol. A gap in coverage is not an empty sky."],
  ["RFA proxy flight", "Ring of Fire Air (RFA) is a fictional airline. Each RFA flight number stands in for a real aircraft seen on ADS-B."],
  ["TEPHRA Assistant", "TEPHRA's AI assistant (Gemini). Its skills (Plume reader, Satellite reader, Flight planner, Drafter, Recovery planner, Notice reader, Ask) read the feeds and draft the text, in the order the Coordinator sets. Code does every number and safety rule, and a person approves everything."],
  ["Code only (NO MODEL)", "The offline test mode: no model is connected and code answers every step, labelled NO MODEL. It is not a fallback: the live site never uses it in place of a model."],
  ["REPLAY and reconstructed", "REPLAY plays recorded real feeds and is labelled for the whole session. A reconstructed case was rebuilt after the event from archived bulletins. A synthetic demo case is invented data on real places, labelled \"synthetic demo data\"."],
  ["Affected area", "The area an official product says the ash covers."],
  ["Policy A (illustrative)", "An example operator policy: every margin, minimum and threshold TEPHRA applies, with its reason. It is not a real airline's policy."],
  ["Alert colour", "The aviation colour code a volcano observatory gives: green, yellow, orange, red (rising concern). Grey means it was not given."],
  ["Estimate", "TEPHRA's ash area. Never smaller than the official area, which stays binding. It is an estimate, not a forecast."],
  ["Advisory", "A message drafted for one flight (for example keep watching, hold, change level or divert). A person approves or rejects it on the Desk."],
  ["Dispatcher", "The airline person who plans and watches flights from the ground. Here, the person who decides on the Desk."],
  ["Proxy flight", "An RFA flight number that stands in for a real aircraft seen on ADS-B. RFA is a fictional airline."],
  ["SO2", "Sulphur dioxide, a volcanic gas. It is not ash. TEPHRA shows it as context only and does not model gases."],
  ["Crew report caution area", "An area code draws around ash a crew (pilot) reported, from a report a dispatcher enters on the Desk. It is operator policy A, not a VAA or SIGMET: it flags flights for a dispatcher, never shrinks an official area and re-plans nothing."],
  ["VAR", "Volcanic activity report: the ICAO form a crew fills in after seeing ash. TEPHRA only drafts it for a person to complete and sign. Nothing is sent."],
];

// The plain meaning shown as a second line under each source column head (7.12).
export const KIND_PLAIN = {
  VONA: "volcano observatory notice",
  SIGMET: "met office warning for the airspace",
  VAA: "ash advisory centre",
};

export const GASES_SCOPE = "SO2 is not ash. Volcanic gases may also be undesirable to fly through, and TEPHRA does not model them.";
export const GASES_SCOPE_SHORT = "SO2 is not ash, gases not modelled";
