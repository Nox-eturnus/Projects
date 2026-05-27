from __future__ import annotations

from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager


def run_on_ideal_simulator(circuit, shots: int = 1024):
    from qiskit_aer import AerSimulator
    from qiskit_ibm_runtime import SamplerV2 as Sampler

    backend = AerSimulator()
    pm = generate_preset_pass_manager(backend=backend, optimization_level=1)
    isa_circuit = pm.run(circuit)
    sampler = Sampler(mode=backend)
    result = sampler.run([isa_circuit], shots=shots).result()
    return result[0].data


def run_on_noisy_ibm_style_simulator(circuit, shots: int = 1024):
    from qiskit_ibm_runtime import SamplerV2 as Sampler
    from qiskit_ibm_runtime.fake_provider import FakeManilaV2

    backend = FakeManilaV2()
    pm = generate_preset_pass_manager(backend=backend, optimization_level=1)
    isa_circuit = pm.run(circuit)
    sampler = Sampler(mode=backend)
    result = sampler.run([isa_circuit], shots=shots).result()
    return result[0].data


def run_on_real_hardware(circuit, backend_name: str | None = None, shots: int = 1024):
    """Submit a circuit to a real IBM QPU.

    Requires credentials saved via ``examples/setup_ibm.py`` (one-time).
    Returns a RuntimeJob — call ``job.result()`` to block until complete.
    """
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

    # This automatically loads credentials saved under the name 'qgss-2025'
    service = QiskitRuntimeService(name="qgss-2025")
    backend = service.backend(backend_name) if backend_name else service.least_busy(
        operational=True,
        simulator=False,
    )
    print(f"Selected backend: {backend.name} ({backend.num_qubits} qubits)")
    
    # 1. Use maximum optimization (level 3) to reduce CNOT depth and SWAP gates
    pm = generate_preset_pass_manager(backend=backend, optimization_level=3)
    isa_circuit = pm.run(circuit)
    
    sampler = Sampler(mode=backend)
    
    # 2. Enable Error Suppression & Mitigation
    # Dynamical Decoupling: protects qubits from decaying while they wait for other gates
    sampler.options.dynamical_decoupling.enable = True
    sampler.options.dynamical_decoupling.sequence_type = "XX"
    
    # Pauli Twirling: turns structured coherent errors into easier-to-manage random noise
    sampler.options.twirling.enable_gates = True
    sampler.options.twirling.enable_measure = True
    
    job = sampler.run([isa_circuit], shots=shots)
    print(f"Job submitted: {job.job_id()}")
    return job
