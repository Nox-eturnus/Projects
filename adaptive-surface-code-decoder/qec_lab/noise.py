from __future__ import annotations

import stim


def replace_depolarize1_with_pauli_channel(
    circuit: stim.Circuit,
    px: float,
    py: float,
    pz: float,
) -> stim.Circuit:
    if min(
        px,
        py,
        pz,
    ) < 0:
        raise ValueError(
            "Pauli probabilities must be non-negative."
        )

    if px + py + pz > 1:
        raise ValueError(
            "px + py + pz must be <= 1."
        )

    output = stim.Circuit()

    for instruction in circuit.flattened():
        if (
            instruction.name
            == "DEPOLARIZE1"
        ):
            output.append(
                "PAULI_CHANNEL_1",
                instruction.targets_copy(),
                [
                    px,
                    py,
                    pz,
                ],
                tag=instruction.tag,
            )
        else:
            output.append(
                instruction.name,
                instruction.targets_copy(),
                instruction.gate_args_copy(),
                tag=instruction.tag,
            )

    return output