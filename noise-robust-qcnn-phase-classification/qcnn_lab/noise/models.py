from __future__ import annotations

from dataclasses import dataclass

from qiskit_aer.noise import NoiseModel, ReadoutError, amplitude_damping_error, depolarizing_error, phase_damping_error


@dataclass(frozen=True)
class NoiseSpec:
    name: str
    depolarizing_1q: float = 0.0
    depolarizing_2q: float = 0.0
    amplitude_damping: float = 0.0
    phase_damping: float = 0.0
    readout: float = 0.0

    def validate(self) -> None:
        for field, value in self.__dict__.items():
            if field == "name":
                continue
            if not 0.0 <= float(value) < 1.0:
                raise ValueError(f"{field} must lie in [0,1)")


def noise_specs_from_config(config: dict) -> dict[str, NoiseSpec]:
    out = {}
    for name, data in config["profiles"].items():
        out[name] = NoiseSpec(name=name, **{k: float(v) for k, v in data.items()})
        out[name].validate()
    return out


def build_noise_model(spec: NoiseSpec) -> NoiseModel:
    spec.validate()
    model = NoiseModel()
    one = depolarizing_error(spec.depolarizing_1q, 1) if spec.depolarizing_1q > 0 else None
    damp = None
    if spec.amplitude_damping > 0:
        damp = amplitude_damping_error(spec.amplitude_damping)
    if spec.phase_damping > 0:
        phase = phase_damping_error(spec.phase_damping)
        damp = phase if damp is None else damp.compose(phase)
    if one is None:
        one = damp
    elif damp is not None:
        one = one.compose(damp)
    if one is not None:
        model.add_all_qubit_quantum_error(one, ["x", "sx", "h", "ry"])

    two = depolarizing_error(spec.depolarizing_2q, 2) if spec.depolarizing_2q > 0 else None
    if damp is not None:
        damp2 = damp.tensor(damp)
        two = damp2 if two is None else two.compose(damp2)
    if two is not None:
        model.add_all_qubit_quantum_error(two, ["cx", "cz", "ecr", "rxx", "ryy", "rzz"])

    if spec.readout > 0:
        p = spec.readout
        model.add_all_qubit_readout_error(ReadoutError([[1 - p, p], [p, 1 - p]]))
    return model