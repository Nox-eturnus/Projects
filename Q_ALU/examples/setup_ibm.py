"""One-time setup: save IBM Quantum credentials locally.

Run this ONCE to store your credentials in ~/.qiskit/qiskit-ibm.json.
After that, the interactive calculator can submit jobs to real hardware.

Usage:
    python examples/setup_ibm.py
"""
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

from qiskit_ibm_runtime import QiskitRuntimeService

# Replace these with your own credentials from IBM Quantum / IBM Cloud.
your_api_key = "PASTE_YOUR_API_KEY_HERE"
your_crn = "PASTE_YOUR_CRN_HERE"

QiskitRuntimeService.save_account(
    channel="ibm_cloud",
    token=your_api_key,
    instance=your_crn,
    name="qgss-2025",
    overwrite=True
)

print("Credentials saved!")

# Verify the connection
service = QiskitRuntimeService(name="qgss-2025")
print("\nSaved accounts:")
print(service.saved_accounts())

print("\nVerifying connection ...")
try:
    backends = service.backends()
    print(f"\nConnected - {len(backends)} backend(s) available.")
except Exception as e:
    print(f"\nConnection failed: {e}")
