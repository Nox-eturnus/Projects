# Standards and Primary References

## ETSI GS QKD 014 V1.1.1
Application-facing REST key-delivery API (published February 2019).

Official published specification:
https://www.etsi.org/deliver/etsi_gs/QKD/001_099/014/01.01.01_60/gs_QKD014v010101p.pdf

Published V1 API paths used in this project:
- `GET /api/v1/keys/{slave_SAE_ID}/status`
- `POST /api/v1/keys/{slave_SAE_ID}/enc_keys`
- `POST /api/v1/keys/{master_SAE_ID}/dec_keys`

Implementation invariants:
- Master SAE and Slave SAE identities are verified and bound to requested keys.
- Secret key bytes are masked in `ManagedKey` string representations.
- Atomic consumption prevents duplicate key reissue.

---

## ETSI GS QKD 020 V1.1.1
Interoperable KMS-to-KMS REST API (published June 2026).

Official ETSI QKD page:
https://www.etsi.org/technical-groups/qkd/

Official ETSI Forge repository:
https://forge.etsi.org/rep/qkd/gs020-interop-kms

Core paths implemented in this research testbed:
- `GET /kmapi/versions` (advertises `synchronous_mode: True`)
- `POST /kmapi/v1/ext_keys` (transactional batch import)
- `POST /kmapi/v1/ext_keys/ack` (supports single container and array of `AckContainer`s)
- `POST /kmapi/v1/ext_keys/void` (`all_confirmation=True` is strictly scoped to the initiator/target SAE pair)

---

## Finite-Key Security Scopes

### Decoy-State BB84 (Theorem-Level Composable Security)
- **Primary Reference**: Lim, Curty, Walenta, Xu, Zbinden, Phys. Rev. A 89, 022307 (2014).
  https://doi.org/10.1103/PhysRevA.89.022307
- **Correctness**: Achieves $\epsilon_{cor}$-correctness via a randomly seeded 2-universal Toeplitz hash family with tag length $t_{ver} \ge \lceil \log_2(1/\epsilon_{cor}) \rceil$, accounting for $t_{ver} + 1$ bits of public leakage.
- **Secrecy**: Composable $\epsilon_{sec}$-secrecy bounded via smooth min-entropy and Chernoff/Hoeffding statistical fluctuations.

### MDI-QKD (Finite-Resource Engineering Model)
- **Primary References**:
  - Lo, Curty, Qi, Phys. Rev. Lett. 108, 130503 (2012). https://doi.org/10.1103/PhysRevLett.108.130503
  - Curty et al., Nature Communications 5, 3732 (2014). https://doi.org/10.1038/ncomms4732
- **Model Scope**: Implements Curty-2014 finite-resource parameter estimation for asymmetric arm lengths ($L_{AC} \neq L_{BC}$) and asymmetric intensities. Evaluates finite-key yields under conservative statistical approximations (omitting vacuum yield as lower bound for robust performance). Delineated from full theorem-level composable min-entropy proofs.

---

## ITU-T QKDN Architecture Editions
- **ITU-T Y.3802 (12/2020)**: Quantum key distribution networks - Functional architecture.
- **ITU-T Y.3803 (12/2020)**: Quantum key distribution networks - Key management.
- **ITU-T Y.3804 (12/2020)**: Quantum key distribution networks - Control and management.
- **ITU-T Y.3806 (09/2021)**: Quantum key distribution networks - Requirements for quality of service assurance.
- **ITU-T Y.3823 (04/2026)**: Quantum key distribution networks - End-to-end quality of service allocation and control.
- **ITU-T X.1711 (03/2026)**: Framework of quantum key distribution (QKD) protocols in QKD networks.