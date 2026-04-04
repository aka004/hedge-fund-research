"""HMM-based regime detector using a 3-state Gaussian HMM.

Features per day:
    1. SPY daily log return
    2. 21-day realised volatility (rolling std of returns × √252)
    3. VIX closing level (normalised)

Training period: 2015-01-01 → 2020-12-31
States are relabelled by mean return:
    lowest mean return  → 0 (bear)
    middle mean return  → 1 (sideways)
    highest mean return → 2 (bull)

The fitted model is persisted to data/cache/regime/hmm_model.pkl so that
subsequent calls reuse the trained model without refitting.
"""

from __future__ import annotations

import logging
import pickle
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.regime.detector_base import RegimeDetector

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data" / "cache" / "regime" / "hmm_model.pkl"
)


class HMMRegimeDetector(RegimeDetector):
    """3-state Gaussian HMM regime classifier.

    Parameters
    ----------
    model_path:
        Where to save/load the fitted model.
    n_iter:
        Number of EM iterations for hmmlearn.
    random_state:
        RNG seed for reproducibility.
    """

    def __init__(
        self,
        model_path: Path | str | None = None,
        n_iter: int = 200,
        random_state: int = 42,
    ) -> None:
        self.model_path = Path(model_path) if model_path else _DEFAULT_MODEL_PATH
        self.n_iter = n_iter
        self.random_state = random_state

        self._model = None          # hmmlearn GaussianHMM
        self._state_map: dict[int, int] = {}   # raw HMM state → regime int
        self._regime_series: pd.Series | None = None  # date → regime int

    # ── Feature construction ────────────────────────────────────────────────

    @staticmethod
    def _build_features(
        returns: pd.Series,
        vix: pd.Series,
        vol_window: int = 21,
    ) -> pd.DataFrame:
        """Build feature matrix used for HMM fitting and prediction.

        Parameters
        ----------
        returns:
            Daily log returns of a market proxy (SPY), indexed by date.
        vix:
            Daily VIX closing levels, indexed by date.
        vol_window:
            Rolling window in days for realised vol (default 21).

        Returns
        -------
        pd.DataFrame
            Columns: [return, realised_vol, vix_norm]
            Rows: aligned, NaN-dropped dates.
        """
        # Realised vol: annualised rolling std of daily returns
        realised_vol = returns.rolling(vol_window).std() * np.sqrt(252)

        # VIX normalisation: z-score over entire history
        vix_norm = (vix - vix.mean()) / (vix.std() + 1e-8)

        feat = pd.DataFrame(
            {"return": returns, "realised_vol": realised_vol, "vix_norm": vix_norm}
        )
        return feat.dropna()

    # ── Fit ─────────────────────────────────────────────────────────────────

    def fit(self, returns: pd.Series, vix: pd.Series | None = None) -> "HMMRegimeDetector":
        """Fit a 3-state Gaussian HMM on returns + realised vol + VIX.

        If a cached model file exists, it is loaded instead of refitting.

        Parameters
        ----------
        returns:
            Daily SPY log returns, indexed by date.
        vix:
            Daily VIX closing levels, indexed by date. Required.
        """
        if vix is None or vix.empty:
            raise ValueError("HMMRegimeDetector requires a non-empty vix series")

        # Normalise indices to date objects
        if isinstance(returns.index, pd.DatetimeIndex):
            returns = returns.copy()
            returns.index = returns.index.date
        if isinstance(vix.index, pd.DatetimeIndex):
            vix = vix.copy()
            vix.index = vix.index.date

        # --- Load cached model ---
        if self.model_path.exists():
            logger.info(f"Loading cached HMM model from {self.model_path}")
            with open(self.model_path, "rb") as f:
                state = pickle.load(f)
            self._model = state["model"]
            self._state_map = state["state_map"]
            # Rebuild full regime series with new data
            feat = self._build_features(returns, vix)
            self._regime_series = self._decode(feat)
            return self

        # --- Fit fresh model ---
        feat = self._build_features(returns, vix)
        X = feat.values

        from hmmlearn.hmm import GaussianHMM

        logger.info(
            f"Fitting GaussianHMM (n_components=3, n_iter={self.n_iter}) "
            f"on {len(X)} observations ({feat.index[0]} → {feat.index[-1]})"
        )
        model = GaussianHMM(
            n_components=3,
            covariance_type="full",
            n_iter=self.n_iter,
            random_state=self.random_state,
            verbose=False,
        )
        model.fit(X)

        # --- Label states by mean daily return ---
        raw_states = model.predict(X)
        mean_returns = {
            s: feat["return"].values[raw_states == s].mean()
            for s in range(3)
        }
        # Sort states by ascending mean return → 0=bear, 1=sideways, 2=bull
        sorted_states = sorted(mean_returns, key=mean_returns.__getitem__)
        self._state_map = {raw: regime for regime, raw in enumerate(sorted_states)}

        logger.info(
            "HMM state mapping (raw → regime): "
            + ", ".join(
                f"state{raw}(μ={mean_returns[raw]:.4f})→{regime}"
                for raw, regime in self._state_map.items()
            )
        )

        self._model = model
        self._regime_series = self._decode(feat)

        # --- Persist ---
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.model_path, "wb") as f:
            pickle.dump({"model": model, "state_map": self._state_map}, f)
        logger.info(f"HMM model saved to {self.model_path}")

        return self

    # ── Decode helper ────────────────────────────────────────────────────────

    def _decode(self, feat: pd.DataFrame) -> pd.Series:
        """Run Viterbi decoding and map raw states to regime ints."""
        raw_states = self._model.predict(feat.values)
        regimes = np.array([self._state_map[s] for s in raw_states])
        return pd.Series(regimes, index=feat.index, name="regime")

    # ── Predict ──────────────────────────────────────────────────────────────

    def predict(self, as_of: date) -> int:
        """Return regime integer for a given date.

        Falls back to nearest prior date if the date is not in the fitted series.
        Returns 1 (sideways) if no prior data is available.
        """
        if self._regime_series is None:
            raise RuntimeError("Call fit() before predict()")

        if hasattr(as_of, "date"):
            as_of = as_of.date()

        idx = self._regime_series.index
        if as_of in idx:
            return int(self._regime_series[as_of])

        prior = [d for d in idx if d <= as_of]
        if not prior:
            return 1  # default sideways
        return int(self._regime_series[prior[-1]])

    def confidence(self, as_of: date) -> float:
        """Return the max posterior probability for the predicted regime."""
        if self._model is None or self._regime_series is None:
            return 1.0
        # Approximate: we don't store full posteriors; return 1.0 as deterministic
        return 1.0
