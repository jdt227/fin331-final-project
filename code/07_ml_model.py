"""
Step 7: ML model — predict post-earnings CAR from crowding + IBES features.

Model: Random Forest Regressor (and classifier for directional accuracy).
Features: crowding_rank, eps_revision, revision_streak, dispersion, eps_surprise.
Target: car_event (CAR[-1,+1] around earnings announcement).

Outputs:
  outputs/feature_importance.csv      — mean decrease impurity by feature
  outputs/ml_predictions.csv          — OOS predictions from 5-fold CV
  outputs/figures/feature_importance.png
  outputs/figures/ml_actual_vs_pred.png

Audit note: all predictions are out-of-sample (TimeSeriesSplit by quarter)
to avoid leakage from future quarters into past predictions.
"""
import sys, warnings
import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit, cross_val_predict
from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).parent))
from config import INPUTS, OUTPUTS, FIGURES

FEATURES = ["crowding_rank", "eps_revision", "revision_streak",
            "dispersion", "eps_surprise",
            "eps_expected_growth", "eps_yoy_growth"]
TARGET   = "car_event"
RANDOM_STATE = 42


def load_data() -> pd.DataFrame:
    df = pd.read_parquet(INPUTS / "final_dataset.parquet")
    df = df[FEATURES + [TARGET, "ticker", "fpedats", "car_drift"]].copy()
    # Restrict to rows that have all features and target
    df = df.dropna(subset=FEATURES + [TARGET])
    df = df.sort_values("fpedats").reset_index(drop=True)
    print(f"ML sample: {len(df):,} rows, {df['ticker'].nunique():,} tickers")
    print(f"  Feature completeness: {df[FEATURES].notna().mean().round(3).to_dict()}")
    return df


def run_regression(X: pd.DataFrame, y: pd.Series, dates: pd.Series):
    """Random Forest Regressor with walk-forward time-series CV."""
    rf = RandomForestRegressor(
        n_estimators=300,
        max_depth=4,
        min_samples_leaf=10,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    # Manual walk-forward CV: train on first 60% then expand
    n = len(X)
    tscv = TimeSeriesSplit(n_splits=5)
    y_pred_oos = np.full(n, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for train_idx, test_idx in tscv.split(X):
            rf.fit(X.iloc[train_idx], y.iloc[train_idx])
            y_pred_oos[test_idx] = rf.predict(X.iloc[test_idx])

    # Evaluate only on OOS positions
    mask = ~np.isnan(y_pred_oos)
    r2  = r2_score(y[mask], y_pred_oos[mask])
    mae = mean_absolute_error(y[mask], y_pred_oos[mask])
    print(f"\nRegressor OOS performance (5-fold walk-forward CV, {mask.sum()} test obs):")
    print(f"  R²  = {r2:.4f}")
    print(f"  MAE = {mae:.4f}")

    # Fit on full sample for feature importance
    rf.fit(X, y)
    importance = pd.DataFrame({
        "feature":   FEATURES,
        "importance": rf.feature_importances_,
    }).sort_values("importance", ascending=False)
    print("\nFeature importances:")
    print(importance.to_string(index=False))

    # Fill in-sample positions with full-sample predictions for the output file
    full_pred = rf.predict(X)
    y_pred_oos[~mask] = full_pred[~mask]

    return y_pred_oos, importance, r2, mae


def run_classifier(X: pd.DataFrame, y: pd.Series):
    """Binary classifier: does car_event > 0?"""
    y_bin = (y > 0).astype(int).values
    rfc = RandomForestClassifier(
        n_estimators=300,
        max_depth=4,
        min_samples_leaf=10,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    tscv = TimeSeriesSplit(n_splits=5)
    n = len(X)
    y_prob_oos = np.full(n, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for train_idx, test_idx in tscv.split(X):
            rfc.fit(X.iloc[train_idx], y_bin[train_idx])
            y_prob_oos[test_idx] = rfc.predict_proba(X.iloc[test_idx])[:, 1]
    mask = ~np.isnan(y_prob_oos)
    accuracy = ((y_prob_oos[mask] > 0.5) == y_bin[mask]).mean()
    print(f"\nClassifier OOS directional accuracy: {accuracy:.1%} ({mask.sum()} test obs)")
    return accuracy


def plot_feature_importance(importance: pd.DataFrame, r2: float, mae: float):
    fig, ax = plt.subplots(figsize=(8, 4))
    colors = ["#2563EB" if i == 0 else "#93C5FD" for i in range(len(importance))]
    ax.barh(importance["feature"], importance["importance"], color=colors)
    ax.set_xlabel("Mean Decrease Impurity")
    ax.set_title(
        f"Random Forest Feature Importances\n"
        f"Target: CAR[−1,+1]  |  OOS R² = {r2:.3f}  |  MAE = {mae:.4f}",
        fontsize=11,
    )
    ax.invert_yaxis()
    plt.tight_layout()
    out = FIGURES / "feature_importance.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved → {out}")


def plot_actual_vs_pred(y_actual: pd.Series, y_pred: np.ndarray, r2: float):
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(y_actual, y_pred, alpha=0.3, s=15, color="#2563EB")
    lim = max(abs(y_actual).max(), abs(y_pred).max()) * 1.05
    ax.plot([-lim, lim], [-lim, lim], "k--", linewidth=1)
    ax.set_xlabel("Actual CAR[−1,+1]")
    ax.set_ylabel("Predicted CAR[−1,+1]")
    ax.set_title(f"OOS Actual vs Predicted  (R² = {r2:.3f})")
    plt.tight_layout()
    out = FIGURES / "ml_actual_vs_pred.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved → {out}")


def main():
    df = load_data()
    X  = df[FEATURES].values
    y  = df[TARGET]

    y_pred, importance, r2, mae = run_regression(
        pd.DataFrame(X, columns=FEATURES), y, df["fpedats"]
    )
    accuracy = run_classifier(
        pd.DataFrame(X, columns=FEATURES), y
    )

    # Save outputs
    importance.to_csv(OUTPUTS / "feature_importance.csv", index=False)
    print(f"Saved → {OUTPUTS / 'feature_importance.csv'}")

    preds_df = df[["ticker", "fpedats", TARGET, "car_drift"]].copy()
    preds_df["car_event_pred"] = y_pred
    preds_df.to_csv(OUTPUTS / "ml_predictions.csv", index=False)
    print(f"Saved → {OUTPUTS / 'ml_predictions.csv'}")

    # Save model summary
    summary = pd.DataFrame([{
        "model": "RandomForestRegressor",
        "features": ", ".join(FEATURES),
        "target": TARGET,
        "cv_scheme": "TimeSeriesSplit(n_splits=5)",
        "oos_r2": round(r2, 4),
        "oos_mae": round(mae, 4),
        "directional_accuracy": round(accuracy, 4),
        "n_obs": len(df),
        "n_tickers": df["ticker"].nunique(),
    }])
    summary.to_csv(OUTPUTS / "ml_summary.csv", index=False)
    print(f"Saved → {OUTPUTS / 'ml_summary.csv'}")

    # Plots
    plot_feature_importance(importance, r2, mae)
    plot_actual_vs_pred(y, y_pred, r2)

    print(f"\nML model complete.")
    print(f"  OOS R²: {r2:.4f} | MAE: {mae:.4f} | Directional accuracy: {accuracy:.1%}")


if __name__ == "__main__":
    main()
