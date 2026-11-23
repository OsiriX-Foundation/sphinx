# Next implementation tasks

| Task | Estimated human engineering hours | External dependency |
| --- | ---: | --- |
| Expand integrity testing to representative compressed syntaxes and additional IODs | 3–5 | None if using synthetic fixtures and public codecs |
| Repeat the tested path against a dedicated Exoscale SOS test bucket | 3–5 | Explicit authorization, a test bucket, scoped credentials and agreed cost limit |

The [local recovery drill](recovery-drill.md) covers coordinated restore and
catalogue-free replay of a two-series uncompressed study.
