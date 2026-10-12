// Shared Desk state. desk.js owns the transitions; the view modules read it and call the
// functions desk.js registers on app.hub.

export const app = {
  state: null, // SystemState from /api/state and `state` events
  me: null, // SessionInfo
  drafts: new Map(), // id -> open DRAFT Advisory
  closed: new Map(), // id -> Advisory that left DRAFT while this page was open
  known: new Set(), // ids already shown once (a new id after the first load is "new")
  arrivedAt: new Map(), // id -> performance.now() when it arrived as new
  cones: new Map(), // cone_id -> ConeFeatureProps (for the hazard band)
  coneGeo: new Map(), // cone_id -> GeoJSON geometry (for the route sketch)
  failures: new Map(), // AiFailure id -> open AiFailure
  messages: new Map(), // CrewPaxMessage id -> message (DRAFT ones are the queue)
  duty: null, // newest DutyRun (the Duty Officer brief card)
  dutyLoaded: false,
  plans: [], // RecoveryPlan, newest first
  plansLoaded: false,
  replan: null, // { airports, at } from the newest RECOVERY trace line when no plan is newer yet
  docs: [], // DocSummary, newest first
  notices: [], // NoticeReading, newest first
  budget: null, // BudgetView
  activeRegions: new Set(), // region keys with an active volcano (Paperwork's SRA select)
  exposedIds: null, // Set of "hex:volcano_id" in or heading into TEPHRA's area now; null until read
  tab: 'queue', // queue | ask | network | docs
  askFlight: null, // { id, proxy } the flight Ask is about
  listLoaded: false,
  listError: '',
  loadSeq: 0,
  lastLoadedAt: null, // active-clock ms of the last good list
  selectedId: null, // the draft open in the review sheet (or selected at 1440)
  offline: false, // no network, a failed fetch, or the stream down for 10 s
  conn: 'idle', // idle | live | reconnecting | offline
  inFlight: new Set(), // ids with a decision request outstanding
  wakeWanted: true,
  hub: {}, // functions registered by desk.js
};

export const draftList = () => [...app.drafts.values()];
