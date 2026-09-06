import numpy as np

from qcnn_lab.qcnn.architecture import build_qcnn, get_architecture, parameter_count, raw_circuit_metrics


def test_shared_qcnn_parameter_count_is_logarithmic_layers():
    arch = get_architecture("light_shared_line")
    assert parameter_count(4, arch) == 12
    assert parameter_count(8, arch) == 18


def test_qcnn_builds_to_one_output():
    arch = get_architecture("light_shared_line")
    p = np.zeros(parameter_count(8, arch))
    qc, output = build_qcnn(8, p, arch)
    assert qc.num_qubits == 8
    assert output == 7
    assert raw_circuit_metrics(8, arch)["two_qubit_operations"] > 0