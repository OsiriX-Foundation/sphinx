# Next implementation tasks

| Task | Estimated human engineering hours | External dependency |
| --- | ---: | --- |
| Restore a coordinated PostgreSQL, LDAP and object backup into a fresh local project and check UID/content preservation | 4–6 | None beyond the local Docker runtime |
| Expand integrity testing to multi-series studies and representative compressed syntaxes | 3–5 | None if using synthetic fixtures and public codecs |
| Repeat the tested path against a dedicated Exoscale SOS test bucket | 3–5 | Explicit authorization, a test bucket, scoped credentials and agreed cost limit |
