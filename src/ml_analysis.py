#!/usr/bin/env python3
"""
Offline ML Analysis of Cognitive Radio Experiments

Predicts throughput and PDR from experimental conditions.
Uses seed-grouped train/test split to avoid data leakage.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json

from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.inspection import permutation_importance

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

# ============================================================
# Configuration
# ============================================================
DATA_PATH = Path("results/calibrated_multi_seed_results.csv")
OUTPUT_DIR = Path("results/ml")
PLOTS_DIR = OUTPUT_DIR / "plots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

TARGETS = ["throughput_bits_per_step", "packet_delivery_ratio"]
SEED_COL = "seed"
TEST_SIZE = 0.2
RANDOM_STATE = 42
N_PERMUTATIONS = 30

# ============================================================
# Phase 1: Dataset Audit
# ============================================================
def audit_dataset(df):
    """Generate dataset audit report."""
    report = {
        "shape": list(df.shape),
        "columns": list(df.columns),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "missing_values": df.isnull().sum().to_dict(),
        "duplicates": int(df.duplicated().sum()),
        "environment_counts": df["environment"].value_counts().to_dict(),
        "strategy_counts": df["strategy"].value_counts().to_dict(),
        "seed_range": [int(df["seed"].min()), int(df["seed"].max())],
        "n_seeds": int(df["seed"].nunique()),
        "target_stats": {
            "throughput_bits_per_step": df["throughput_bits_per_step"].describe().to_dict(),
            "packet_delivery_ratio": df["packet_delivery_ratio"].describe().to_dict(),
        }
    }
    return report

# ============================================================
# Phase 2: Feature Engineering
# ============================================================
def prepare_features_targets(df):
    """
    Prepare features and targets for ML.

    Features available BEFORE experiment:
    - environment (categorical: Low, Medium, High)
    - strategy (categorical: 7 strategies)
    - seed (identifier, used for grouping only)

    Targets (measured AFTER experiment):
    - throughput_bits_per_step
    - packet_delivery_ratio

    DO NOT USE as features:
    - service_availability (post-experiment metric)
    - switches (post-experiment outcome)
    - attempted_packets (post-experiment outcome)
    """
    # Categorical features available before decision
    cat_features = ["environment", "strategy"]

    # Targets
    y = df[TARGETS].copy()

    # Features matrix
    X = df[cat_features].copy()

    # Groups for seed-grouped split
    groups = df[SEED_COL].values

    return X, y, groups, cat_features

# ============================================================
# Phase 3: Model Training & Evaluation
# ============================================================
def build_pipelines(cat_features):
    """Build preprocessing + model pipelines."""

    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(drop="first", sparse_output=False), cat_features),
        ],
        remainder="passthrough"
    )

    # Linear Regression baseline
    lr_pipeline = Pipeline([
        ("preprocessor", preprocessor),
        ("scaler", StandardScaler(with_mean=False)),
        ("model", LinearRegression())
    ])

    # Random Forest
    rf_pipeline = Pipeline([
        ("preprocessor", preprocessor),
        ("model", RandomForestRegressor(
            n_estimators=500,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=RANDOM_STATE,
            n_jobs=-1
        ))
    ])

    return lr_pipeline, rf_pipeline

def evaluate_model(y_true, y_pred, target_name):
    """Compute evaluation metrics."""
    return {
        "target": target_name,
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred))
    }

def train_and_evaluate(X, y, groups, cat_features, target_name):
    """Train both models on a single target with seed-grouped split."""

    # Seed-grouped split
    gss = GroupShuffleSplit(n_splits=1, test_size=TEST_SIZE, random_state=RANDOM_STATE)
    train_idx, test_idx = next(gss.split(X, y[target_name], groups=groups))

    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y[target_name].iloc[train_idx], y[target_name].iloc[test_idx]
    groups_train, groups_test = groups[train_idx], groups[test_idx]

    print(f"\n  {target_name}: Train seeds={len(np.unique(groups_train))}, Test seeds={len(np.unique(groups_test))}")

    # Build pipelines
    lr_pipe, rf_pipe = build_pipelines(cat_features)

    # Linear Regression
    lr_pipe.fit(X_train, y_train)
    lr_pred = lr_pipe.predict(X_test)
    lr_metrics = evaluate_model(y_test, lr_pred, target_name)

    # Random Forest
    rf_pipe.fit(X_train, y_train)
    rf_pred = rf_pipe.predict(X_test)
    rf_metrics = evaluate_model(y_test, rf_pred, target_name)

    # Baseline: mean predictor
    baseline_pred = np.full_like(y_test, y_train.mean())
    baseline_metrics = evaluate_model(y_test, baseline_pred, target_name)

    return {
        "target": target_name,
        "train_indices": train_idx.tolist(),
        "test_indices": test_idx.tolist(),
        "linear_regression": {
            "metrics": lr_metrics,
            "predictions": lr_pred.tolist(),
            "actual": y_test.tolist()
        },
        "random_forest": {
            "metrics": rf_metrics,
            "predictions": rf_pred.tolist(),
            "actual": y_test.tolist()
        },
        "baseline": {
            "metrics": baseline_metrics
        }
    }

# ============================================================
# Phase 4: Feature Importance & Permutation Importance
# ============================================================
def get_feature_names(pipeline, cat_features):
    """Get feature names from fitted pipeline."""
    preprocessor = pipeline.named_steps["preprocessor"]
    cat_encoder = preprocessor.named_transformers_["cat"]
    cat_names = cat_encoder.get_feature_names_out(cat_features).tolist()
    return cat_names

def compute_permutation_importance(pipeline, X_test, y_test, feature_names, target_name):
    """Compute permutation importance for Random Forest using transformed features."""
    # Extract the fitted preprocessor and model
    preprocessor = pipeline.named_steps["preprocessor"]
    model = pipeline.named_steps["model"]

    # Transform test features
    X_test_trans = preprocessor.transform(X_test)

    result = permutation_importance(
        model, X_test_trans, y_test,
        n_repeats=N_PERMUTATIONS,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        scoring="neg_mean_absolute_error"
    )

    importance_df = pd.DataFrame({
        "feature": feature_names,
        "importance_mean": result.importances_mean,
        "importance_std": result.importances_std
    }).sort_values("importance_mean", ascending=False)

    return importance_df

# ============================================================
# Phase 5: Visualization
# ============================================================
def plot_actual_vs_predicted(results, target_name, output_dir):
    """Plot actual vs predicted for both models."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    actual = results["linear_regression"]["actual"]
    lr_pred = results["linear_regression"]["predictions"]
    rf_pred = results["random_forest"]["predictions"]
    baseline_pred = [np.mean(actual)] * len(actual)

    for ax, preds, name, color in [
        (axes[0], baseline_pred, "Baseline (Mean)", "gray"),
        (axes[1], lr_pred, "Linear Regression", "blue"),
        (axes[2], rf_pred, "Random Forest", "green")
    ]:
        ax.scatter(actual, preds, alpha=0.6, color=color, s=30)
        min_val, max_val = min(actual), max(actual)
        ax.plot([min_val, max_val], [min_val, max_val], 'r--', lw=2)
        ax.set_xlabel("Actual")
        ax.set_ylabel("Predicted")
        ax.set_title(f"{name}\nR² = {r2_score(actual, preds):.3f}")
        ax.grid(True, alpha=0.3)

    plt.suptitle(f"{target_name} - Actual vs Predicted")
    plt.tight_layout()
    plt.savefig(output_dir / f"{target_name}_actual_vs_predicted.png", dpi=150)
    plt.close()

def plot_residuals(results, target_name, output_dir):
    """Plot residuals for both models."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    actual = results["linear_regression"]["actual"]
    lr_pred = results["linear_regression"]["predictions"]
    rf_pred = results["random_forest"]["predictions"]

    for ax, preds, name, color in [
        (axes[0], lr_pred, "Linear Regression", "blue"),
        (axes[1], rf_pred, "Random Forest", "green")
    ]:
        residuals = np.array(actual) - np.array(preds)
        ax.scatter(preds, residuals, alpha=0.6, color=color, s=30)
        ax.axhline(y=0, color='r', linestyle='--', lw=2)
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Residual (Actual - Predicted)")
        ax.set_title(f"{name} Residuals")
        ax.grid(True, alpha=0.3)

    plt.suptitle(f"{target_name} - Residual Plots")
    plt.tight_layout()
    plt.savefig(output_dir / f"{target_name}_residuals.png", dpi=150)
    plt.close()

def plot_feature_importance(importance_df, target_name, output_dir):
    """Plot feature importance (permutation)."""
    plt.figure(figsize=(10, 6))
    plt.barh(range(len(importance_df)), importance_df["importance_mean"],
             xerr=importance_df["importance_std"], capsize=3)
    plt.yticks(range(len(importance_df)), importance_df["feature"])
    plt.xlabel("Permutation Importance (MAE increase)")
    plt.title(f"Feature Importance - {target_name} (Random Forest)")
    plt.gca().invert_yaxis()
    plt.tight_layout()
    plt.savefig(output_dir / f"{target_name}_feature_importance.png", dpi=150)
    plt.close()

def plot_performance_by_environment(df, output_dir):
    """Plot model performance stratified by environment."""
    # We'll create this from the test set predictions
    pass  # Implemented later with saved results

# ============================================================
# Main Execution
# ============================================================
def main():
    print("=" * 60)
    print("OFFLINE ML ANALYSIS - COGNITIVE RADIO EXPERIMENTS")
    print("=" * 60)

    # Load data
    df = pd.read_csv(DATA_PATH)
    print(f"\nLoaded dataset: {df.shape[0]} rows, {df.shape[1]} columns")

    # Phase 1: Audit
    print("\n[Phase 1] Dataset Audit...")
    audit_report = audit_dataset(df)
    with open(OUTPUT_DIR / "dataset_audit.json", "w") as f:
        json.dump(audit_report, f, indent=2, default=str)
    print(f"  Audit saved to {OUTPUT_DIR}/dataset_audit.json")

    # Phase 2: Feature Engineering
    print("\n[Phase 2] Feature Engineering...")
    X, y, groups, cat_features = prepare_features_targets(df)
    print(f"  Features: {cat_features}")
    print(f"  Targets: {TARGETS}")
    print(f"  Groups (seeds): {len(np.unique(groups))}")

    # Phase 3: Train & Evaluate
    print("\n[Phase 3] Training & Evaluation...")
    all_results = {}
    all_importance = {}

    for target in TARGETS:
        print(f"\n  Target: {target}")
        result = train_and_evaluate(X, y, groups, cat_features, target)
        all_results[target] = result

        # Print metrics
        for model_name in ["baseline", "linear_regression", "random_forest"]:
            m = result[model_name]["metrics"]
            print(f"    {model_name:20s}  MAE={m['mae']:.4f}  RMSE={m['rmse']:.4f}  R²={m['r2']:.4f}")

        # Phase 4: Feature Importance (Random Forest only)
        print(f"\n  [Phase 4] Permutation Importance for {target}...")
        # Re-fit RF on full train set for importance
        gss = GroupShuffleSplit(n_splits=1, test_size=TEST_SIZE, random_state=RANDOM_STATE)
        train_idx, test_idx = next(gss.split(X, y[target], groups=groups))
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y[target].iloc[train_idx], y[target].iloc[test_idx]

        _, rf_pipe = build_pipelines(cat_features)
        rf_pipe.fit(X_train, y_train)

        feature_names = get_feature_names(rf_pipe, cat_features)
        importance_df = compute_permutation_importance(rf_pipe, X_test, y_test, feature_names, target)
        all_importance[target] = importance_df

        print("  Top features:")
        for _, row in importance_df.head(10).iterrows():
            print(f"    {row['feature']:30s}  {row['importance_mean']:.4f} ± {row['importance_std']:.4f}")

        # Save importance
        importance_df.to_csv(OUTPUT_DIR / f"feature_importance_{target}.csv", index=False)

        # Phase 4: Visualization
        print(f"\n  [Phase 4] Generating plots for {target}...")
        plot_actual_vs_predicted(result, target, PLOTS_DIR)
        plot_residuals(result, target, PLOTS_DIR)
        plot_feature_importance(importance_df, target, PLOTS_DIR)

    # Save model comparison
    comparison_rows = []
    for target in TARGETS:
        for model_name in ["baseline", "linear_regression", "random_forest"]:
            m = all_results[target][model_name]["metrics"]
            comparison_rows.append({
                "target": target,
                "model": model_name,
                "mae": m["mae"],
                "rmse": m["rmse"],
                "r2": m["r2"]
            })
    comparison_df = pd.DataFrame(comparison_rows)
    comparison_df.to_csv(OUTPUT_DIR / "model_comparison.csv", index=False)
    print(f"\n  Model comparison saved to {OUTPUT_DIR}/model_comparison.csv")

    # Save detailed results
    for target in TARGETS:
        # Linear regression results
        lr_df = pd.DataFrame({
            "actual": all_results[target]["linear_regression"]["actual"],
            "predicted": all_results[target]["linear_regression"]["predictions"]
        })
        lr_df.to_csv(OUTPUT_DIR / f"linear_regression_results_{target}.csv", index=False)

        # Random forest results
        rf_df = pd.DataFrame({
            "actual": all_results[target]["random_forest"]["actual"],
            "predicted": all_results[target]["random_forest"]["predictions"]
        })
        rf_df.to_csv(OUTPUT_DIR / f"random_forest_results_{target}.csv", index=False)

    # Performance by environment (on test sets)
    print("\n[Phase 4] Performance by environment...")
    env_results = []
    for target in TARGETS:
        gss = GroupShuffleSplit(n_splits=1, test_size=TEST_SIZE, random_state=RANDOM_STATE)
        train_idx, test_idx = next(gss.split(X, y[target], groups=groups))
        test_df = df.iloc[test_idx].copy()
        test_df["lr_pred"] = all_results[target]["linear_regression"]["predictions"]
        test_df["rf_pred"] = all_results[target]["random_forest"]["predictions"]

        for env in ["Low", "Medium", "High"]:
            env_mask = test_df["environment"] == env
            if env_mask.sum() > 0:
                for model_name, pred_col in [("linear_regression", "lr_pred"), ("random_forest", "rf_pred")]:
                    mae = mean_absolute_error(test_df.loc[env_mask, target], test_df.loc[env_mask, pred_col])
                    rmse = np.sqrt(mean_squared_error(test_df.loc[env_mask, target], test_df.loc[env_mask, pred_col]))
                    r2 = r2_score(test_df.loc[env_mask, target], test_df.loc[env_mask, pred_col])
                    env_results.append({
                        "target": target,
                        "environment": env,
                        "model": model_name,
                        "mae": mae,
                        "rmse": rmse,
                        "r2": r2,
                        "n_samples": int(env_mask.sum())
                    })

    env_df = pd.DataFrame(env_results)
    env_df.to_csv(OUTPUT_DIR / "performance_by_environment.csv", index=False)
    print(f"  Performance by environment saved to {OUTPUT_DIR}/performance_by_environment.csv")

    # Plot performance by environment
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, target in zip(axes, TARGETS):
        subset = env_df[env_df["target"] == target]
        x = np.arange(len(subset["environment"].unique()))
        width = 0.35
        for i, model in enumerate(["linear_regression", "random_forest"]):
            model_data = subset[subset["model"] == model]
            ax.bar(x + (i - 0.5) * width, model_data["r2"], width, label=model, alpha=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(subset["environment"].unique())
        ax.set_ylabel("R²")
        ax.set_title(f"{target} - R² by Environment")
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "r2_by_environment.png", dpi=150)
    plt.close()

    print("\n" + "=" * 60)
    print("ML ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Outputs saved to: {OUTPUT_DIR}")
    print(f"Plots saved to: {PLOTS_DIR}")

if __name__ == "__main__":
    main()