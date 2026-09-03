from __future__ import annotations

from pathlib import Path

import yaml

from qkd_lab.models import BasisProbabilities, ChannelParameters, DetectorParameters, IntensitySetting


def load_yaml(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def bb84_objects(config: dict):
    source = config["source"]
    intensities = tuple(
        IntensitySetting(name, float(source[name]["mu"]), float(source[name]["probability"]))
        for name in ("signal", "decoy", "vacuum")
    )
    basis = BasisProbabilities(
        float(config["basis"]["p_x_alice"]),
        float(config["basis"]["p_x_bob"]),
    )
    channel = ChannelParameters(
        float(config["channel"]["length_km"]),
        float(config["channel"]["attenuation_db_per_km"]),
    )
    detector = DetectorParameters(
        efficiency=float(config["detector"]["efficiency"]),
        dark_probability=float(config["detector"]["dark_probability"]),
        misalignment=float(config["detector"]["misalignment"]),
        n_detectors=int(config["detector"].get("n_detectors", 2)),
    )
    return intensities, basis, channel, detector


def _mdi_intensities(section: dict):
    from qkd_lab.models import IntensitySetting

    return tuple(
        IntensitySetting(name, float(section[name]["mu"]), float(section[name]["probability"]))
        for name in ("signal", "decoy", "vacuum")
    )



def mdi_physical_objects(config: dict):
    # Lazy import keeps the BB84-only phases independent of the MDI package.
    from qkd_lab.protocols.mdi_qkd import MDIBasisProbabilities, MDIPhysicalParameters

    alice = _mdi_intensities(config["alice"])
    bob = _mdi_intensities(config["bob"])
    basis = MDIBasisProbabilities(
        float(config["basis"]["p_z_alice"]),
        float(config["basis"]["p_z_bob"]),
    )
    physical = MDIPhysicalParameters(
        alice_to_charlie_km=float(config["channel"]["alice_to_charlie_km"]),
        bob_to_charlie_km=float(config["channel"]["bob_to_charlie_km"]),
        attenuation_db_per_km=float(config["channel"]["attenuation_db_per_km"]),
        detector_efficiency=float(config["charlie"]["detector_efficiency"]),
        dark_probability=float(config["charlie"]["dark_probability"]),
        misalignment=float(config["charlie"]["misalignment"]),
    )
    return alice, bob, basis, physical


def mdi_objects(config: dict):
    # Lazy imports keep the early BB84 phases runnable before the MDI files are created.
    from qkd_lab.estimation.finite_key_mdi import MDIFiniteKeyBudget
    from qkd_lab.protocols.mdi_qkd import MDIBasisProbabilities, MDIPhysicalParameters

    alice, bob, basis, physical = mdi_physical_objects(config)
    f = config["finite_key"]
    budget = MDIFiniteKeyBudget(**{k: float(v) for k, v in f.items()})
    return alice, bob, basis, physical, budget