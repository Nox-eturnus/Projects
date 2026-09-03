# Standards and Primary References

## ETSI GS QKD 014 V1.1.1
Application-facing REST key-delivery API.

Official published specification:
https://www.etsi.org/deliver/etsi_gs/QKD/001_099/014/01.01.01_60/gs_QKD014v010101p.pdf

Published V1 API paths used in this project:
- `GET /api/v1/keys/{slave_SAE_ID}/status`
- `POST /api/v1/keys/{slave_SAE_ID}/enc_keys`
- `POST /api/v1/keys/{master_SAE_ID}/dec_keys`

## ETSI GS QKD 020 V1.1.1
Interoperable KMS-to-KMS REST API, published June 2026.

Official ETSI QKD page:
https://www.etsi.org/technical-groups/qkd/

Official ETSI Forge repository:
https://forge.etsi.org/rep/qkd/gs020-interop-kms

Core paths implemented in this research testbed:
- `GET /kmapi/versions`
- `POST /kmapi/v1/ext_keys`
- `POST /kmapi/v1/ext_keys/ack`
- `POST /kmapi/v1/ext_keys/void`

## Finite-key BB84
Lim, Curty, Walenta, Xu, Zbinden, Phys. Rev. A 89, 022307 (2014).
https://doi.org/10.1103/PhysRevA.89.022307

## Decoy-state BB84
Ma, Qi, Zhao, Lo, Phys. Rev. A 72, 012326 (2005).
https://doi.org/10.1103/PhysRevA.72.012326

## MDI-QKD
Lo, Curty, Qi, Phys. Rev. Lett. 108, 130503 (2012).
https://doi.org/10.1103/PhysRevLett.108.130503

Curty et al., Nature Communications 5, 3732 (2014).
https://doi.org/10.1038/ncomms4732

## ITU-T QKDN architecture references
- ITU-T Y.3802 — QKDN functional architecture
- ITU-T Y.3803 — QKDN key management
- ITU-T Y.3806 — QKDN QoS requirements
- ITU-T X.1711 — QKD protocol framework in QKD networks
- ITU-T Y.3823 — end-to-end QKDN QoS allocation