// How each part of TEPHRA works, in plain words (UI-DESIGN 7.22). These lines are the guide's "How
// each part works" section; Details shows the data, not the manual.

export const EXPLAIN = [
  ["entry", "How a flight's entry is estimated", ["Code projects the last position along its track, speed and level. An entry time is an estimate: it holds only if track, speed and level are held."]],
  ["route", "Where a flight's route comes from", ["The usual route for the callsign, from VRS standing data. It is not the filed flight plan, and TEPHRA never guesses one."]],
  ["src", "How to read the sources", ["One row per kind of report, the newest of each. A pink edge marks an official report (SIGMET, VAA): it is binding. A blue edge marks the observatory (VONA): it supports. A value that disagrees with another source carries the caution shape."]],
  ["area", "About TEPHRA's estimate", ["TEPHRA's estimate is an estimate, not a forecast. It is drawn as the amber dashed line, never smaller than the official area, which stays binding."]],
  ["hist", "About lag", ["Official reports are reissued every few hours, so they trail the observatory: a lag is usual. The time bar's History shows these events on three lanes."]],
  ["trace", "How to read How TEPHRA decided", ["Each step in plain words. Steps that say the same thing are one row with how many times and when. Open a row for each step. Lines TEPHRA has no plain wording for are shown as written, and the raw line is always under Technical detail."]],
  ["crew", "How crew reports work", [
    "A dispatcher enters a crew (pilot) report on the Desk, and code draws a caution area around the reported position over the reported levels (operator policy A, not a VAA or SIGMET). It flags flights whose projected track crosses it.",
    "It never shrinks or replaces an official area, re-plans nothing and calls no model. A sulphur smell or haze alone is a routine report with no area. A no-ash report never removes one."]],
  ["sat", "How the satellite check works", [
    "TEPHRA Assistant's Satellite reader (a model) looks at the latest Himawari picture for each active volcano and says whether it sees ash. While the assistant is off a code stub reads it instead.",
    "It is supporting evidence only: it never changes the hazard area, the flight levels or an action. Colour alone cannot separate ash from dust, and a picture gives no height."]],
  ["notices", "How notices are checked", ["Notices pasted on the Desk, and JMA volcano reports. A pasted notice is read by a model, then every claim is checked against its own words. Only a verified notice can enter the picture. JMA reports are read by code from JMA's XML."]],
  ["recovery", "How the airport plan is made", ["Airports the ash closes, and the day's flights of RFA (a fictional airline, synthetic schedule) re-planned around them. An optimiser (code) builds the scenarios, and a model only picks one and explains it. A dispatcher approves on the Desk."]],
  ["assistant", "How TEPHRA Assistant works", [
    "TEPHRA Assistant is TEPHRA's AI assistant. It reads feeds and drafts text. Code does every number and safety rule, and a person approves everything. One skill, the Coordinator, orders the day's assistant work and hands it to the other skills through tools. Code builds the work list and holds the safety line. The Coordinator decides the order and writes the brief.",
    "Every assistant step on the Wall is listed in How TEPHRA decided. When a step does not run it says why, and nothing is made up in its place."]],
];
