import csv
import numpy as np

INPUT = "results/refined_equal_power_calibration.csv"

def sigmoid(z):
    z = np.clip(z, -500, 500)
    return 1.0 / (1.0 + np.exp(-z))


def fit_logistic(x, y):
    # Standardize x for numerical stability.
    mean_x = np.mean(x)
    scale_x = np.std(x)
    z = (x - mean_x) / scale_x

    X = np.column_stack([np.ones(len(z)), z])
    beta = np.zeros(2)

    # Newton-Raphson maximum likelihood estimation.
    for _ in range(100):
        p = sigmoid(X @ beta)
        weights = np.maximum(p * (1 - p), 1e-9)

        gradient = X.T @ (y - p)
        hessian = X.T @ (weights[:, None] * X)

        step = np.linalg.solve(hessian, gradient)
        beta += step

        if np.linalg.norm(step) < 1e-9:
            break

    intercept = beta[0] - beta[1] * mean_x / scale_x
    slope = beta[1] / scale_x

    return intercept, slope


with open(INPUT, newline="") as f:
    rows = list(csv.DictReader(f))

print("=" * 75)
print("EMPIRICAL PACKET-SUCCESS LOGISTIC MODELS")
print("=" * 75)

models = {}

for modulation in ["BPSK", "QPSK", "16-QAM"]:

    group = [
        r for r in rows
        if r["modulation"] == modulation
    ]

    x = np.array(
        [float(r["noise_voltage"]) for r in group]
    )

    y = np.array(
        [
            float(r["packet_success"].lower() == "true")
            for r in group
        ]
    )

    intercept, slope = fit_logistic(x, y)
    models[modulation] = (intercept, slope)

    print(f"\n{modulation}")
    print(f"Trials: {len(y)}")
    print(f"Successes: {int(y.sum())}")
    print(f"Failures: {len(y) - int(y.sum())}")
    print(f"Intercept: {intercept:.6f}")
    print(f"Slope:     {slope:.6f}")

    if slope >= 0:
        print("WARNING: Unexpected non-negative noise coefficient.")

    for target in [0.90, 0.50, 0.10]:
        threshold = (
            np.log(target / (1 - target)) - intercept
        ) / slope

        print(f"Noise at {target:.0%} PDR: {threshold:.6f}")

print("\n" + "=" * 75)
print("MODEL SUMMARY")
print("=" * 75)

for name, (a, b) in models.items():
    print(
        f"{name:<8} | "
        f"PDR = sigmoid({a:.4f} {b:+.4f} * noise)"
    )
