"""Optional extensions that are never imported on the default code path.

Nothing in `oriward/` may import this package at module level: each extension is
loaded lazily, only after its own environment switch is set. Extensions talk to
third-party platforms whose terms of service are the user's responsibility, so
shipping them in the main package would silently turn a personal tool into a
client that every clone is allowed to point at someone else's endpoint.
"""
