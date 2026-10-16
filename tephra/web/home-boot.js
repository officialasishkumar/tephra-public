// An old link to the Wall at /#... lands on the demo with its query and hash (the server never sees
// a hash; it redirects /?... itself). A classic script, first in the head, so nothing draws before it.
if (location.hash.length > 1) location.replace("/demo" + location.search + location.hash);
