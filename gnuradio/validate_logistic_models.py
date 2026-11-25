import csv
import numpy as np

INPUT = "results/expanded_equal_power_calibration.csv"

def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))


def fit_logistic(x, y):
    mean_x = np.mean(x)
    scale_x = np.std(x)
    z = (x - mean_x) / scale_x

    X = np.column_stack([np.ones(len(z)), z])
    beta = np.zeros(2)

    for _ in range(100):
        p = sigmoid(X @ beta)
        w = np.maximum(p * (1 - p), 1e-9)

        gradient = X.T @ (y - p)
        hessian = X.T @ (w[:, None] * X)

        step = np.linalg.solve(hessian, gradient)
        beta += step

        if np.linalg.norm(step) < 1e-9:
            break

    return beta, mean_x, scale_x


def predict(x, model):
    beta, mean_x, scale_x = model
    z = (x - mean_x) / scale_x
    return sigmoid(beta[0] + beta[1] * z)


with open(INPUT, newline="") as f:
    rows = list(csv.DictReader(f))

print("=" * 72)
print("LEAVE-ONE-SEED-OUT CROSS-VALIDATION")
print("=" * 72)

for modulation in ["BPSK", "QPSK", "16-QAM"]:

    group = [r for r in rows if r["modulation"] == modulation]

    x = np.array([float(r["noise_voltage"]) for r in group])
    y = np.array([
        float(r["packet_success"].lower() == "true")
        for r in group
    ])
    seeds = np.array([int(r["seed"]) for r in group])

    predictions = np.zeros(len(y))

    for seed in np.unique(seeds):
        train = seeds != seed
        test = seeds == seed

        model = fit_logistic(x[train], y[train])
        predictions[test] = predict(x[test], model)

    brier = np.mean((y - predictions) ** 2)

    clipped = np.clip(predictions, 1e-12, 1 - 1e-12)
    log_loss = -np.mean(
        y * np.log(clipped) +
        (1 - y) * np.log(1 - clipped)
    )

    accuracy = np.mean((predictions >= 0.5) == y)

    print(f"\n{modulation}")
    print(f"Trials:             {len(y)}")
    print(f"Seeds:              {len(np.unique(seeds))}")
    print(f"Cross-val Brier:    {brier:.5f}")
    print(f"Cross-val log loss: {log_loss:.5f}")
    print(f"Cross-val accuracy: {accuracy:.2%}")
