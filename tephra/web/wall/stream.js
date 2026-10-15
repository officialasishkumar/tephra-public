// The Wall's and Connect's event stream, the part with no DOM (tests/test_wall_stream.py runs it
// under Node). A browser's EventSource retries by itself after a network error but stays CLOSED
// after an HTTP error (a 503 while the service restarts): the page must open a new one. The wait
// between tries doubles from 5 s to a minute, and the first try after a good open is 5 s again.

export const STREAM_RETRY_MS = 5000;
const STREAM_RETRY_MAX_MS = 60000;

// The next wait after `prev` ms (0 or undefined after a good open): 5 s, 10 s, 20 s, ... 60 s.
export const nextRetryMs = (prev) => Math.min((prev || STREAM_RETRY_MS / 2) * 2, STREAM_RETRY_MAX_MS);

// A source the browser gave up on (EventSource.CLOSED is 2) needs a fresh one from the page.
export const shouldReopen = (readyState) => readyState === 2;
