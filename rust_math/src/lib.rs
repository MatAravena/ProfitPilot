use pyo3::prelude::*;
use rayon::prelude::*;

/// ProfitPilot Math — Rust-accelerated computations exposed to Python via PyO3.
///
/// Rules:
/// - All functions are stateless — pure input → output.
/// - Use rayon for parallelism on large arrays.
/// - All inputs validated — panic with clear messages on bad data.
/// - Never allocate more than needed.

// ── Technical Indicators ──────────────────────────────────────────────────────

/// Relative Strength Index (RSI)
#[pyfunction]
fn rsi(closes: Vec<f64>, period: usize) -> PyResult<Vec<f64>> {
    if closes.len() < period + 1 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("Need at least {} data points for RSI({})", period + 1, period)
        ));
    }

    let mut gains = vec![0.0_f64; closes.len()];
    let mut losses = vec![0.0_f64; closes.len()];

    for i in 1..closes.len() {
        let diff = closes[i] - closes[i - 1];
        if diff > 0.0 {
            gains[i] = diff;
        } else {
            losses[i] = -diff;
        }
    }

    let mut avg_gain: f64 = gains[1..=period].iter().sum::<f64>() / period as f64;
    let mut avg_loss: f64 = losses[1..=period].iter().sum::<f64>() / period as f64;

    let mut result = vec![f64::NAN; closes.len()];

    for i in period..closes.len() {
        if i > period {
            avg_gain = (avg_gain * (period as f64 - 1.0) + gains[i]) / period as f64;
            avg_loss = (avg_loss * (period as f64 - 1.0) + losses[i]) / period as f64;
        }
        result[i] = if avg_loss == 0.0 {
            100.0
        } else {
            100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
        };
    }

    Ok(result)
}

/// Simple Moving Average
#[pyfunction]
fn sma(values: Vec<f64>, period: usize) -> PyResult<Vec<f64>> {
    if values.len() < period {
        return Err(pyo3::exceptions::PyValueError::new_err("Not enough data for SMA"));
    }
    let mut result = vec![f64::NAN; values.len()];
    for i in (period - 1)..values.len() {
        result[i] = values[(i + 1 - period)..=i].iter().sum::<f64>() / period as f64;
    }
    Ok(result)
}

/// Exponential Moving Average
#[pyfunction]
fn ema(values: Vec<f64>, period: usize) -> PyResult<Vec<f64>> {
    if values.is_empty() {
        return Err(pyo3::exceptions::PyValueError::new_err("Empty values for EMA"));
    }
    let k = 2.0 / (period as f64 + 1.0);
    let mut result = vec![f64::NAN; values.len()];
    result[0] = values[0];
    for i in 1..values.len() {
        result[i] = values[i] * k + result[i - 1] * (1.0 - k);
    }
    Ok(result)
}

/// Average True Range (ATR) — volatility measure
#[pyfunction]
fn atr(highs: Vec<f64>, lows: Vec<f64>, closes: Vec<f64>, period: usize) -> PyResult<Vec<f64>> {
    let n = highs.len();
    if n != lows.len() || n != closes.len() {
        return Err(pyo3::exceptions::PyValueError::new_err("OHLC arrays must be same length"));
    }
    if n < 2 {
        return Err(pyo3::exceptions::PyValueError::new_err("Need at least 2 bars for ATR"));
    }

    let mut tr = vec![0.0_f64; n];
    tr[0] = highs[0] - lows[0];
    for i in 1..n {
        let hl = highs[i] - lows[i];
        let hcp = (highs[i] - closes[i - 1]).abs();
        let lcp = (lows[i] - closes[i - 1]).abs();
        tr[i] = hl.max(hcp).max(lcp);
    }

    // Wilder smoothing
    let mut result = vec![f64::NAN; n];
    let init_atr: f64 = tr[1..=period].iter().sum::<f64>() / period as f64;
    result[period] = init_atr;
    for i in (period + 1)..n {
        result[i] = (result[i - 1] * (period as f64 - 1.0) + tr[i]) / period as f64;
    }

    Ok(result)
}

// ── Statistics ────────────────────────────────────────────────────────────────

/// Sharpe Ratio (annualized)
#[pyfunction]
fn sharpe_ratio(returns: Vec<f64>, risk_free_rate: f64, periods_per_year: f64) -> PyResult<f64> {
    if returns.len() < 2 {
        return Err(pyo3::exceptions::PyValueError::new_err("Need at least 2 returns for Sharpe"));
    }
    let n = returns.len() as f64;
    let mean: f64 = returns.iter().sum::<f64>() / n;
    let variance: f64 = returns.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / (n - 1.0);
    let std_dev = variance.sqrt();
    if std_dev == 0.0 {
        return Ok(0.0);
    }
    let daily_rf = risk_free_rate / periods_per_year;
    Ok(((mean - daily_rf) / std_dev) * periods_per_year.sqrt())
}

/// Maximum Drawdown — returns (max_dd_pct, peak_index, trough_index)
#[pyfunction]
fn max_drawdown(equity_curve: Vec<f64>) -> PyResult<(f64, usize, usize)> {
    if equity_curve.is_empty() {
        return Err(pyo3::exceptions::PyValueError::new_err("Empty equity curve"));
    }
    let mut peak = equity_curve[0];
    let mut peak_idx = 0usize;
    let mut max_dd = 0.0_f64;
    let mut trough_idx = 0usize;

    for (i, &val) in equity_curve.iter().enumerate() {
        if val > peak {
            peak = val;
            peak_idx = i;
        }
        let dd = (peak - val) / peak;
        if dd > max_dd {
            max_dd = dd;
            trough_idx = i;
        }
    }
    Ok((max_dd, peak_idx, trough_idx))
}

// ── Monte Carlo ───────────────────────────────────────────────────────────────

/// Monte Carlo simulation of portfolio returns.
/// Returns Vec of final equity values across `n_simulations` paths.
#[pyfunction]
fn monte_carlo_returns(
    daily_returns: Vec<f64>,
    n_simulations: usize,
    n_days: usize,
    initial_equity: f64,
) -> PyResult<Vec<f64>> {
    if daily_returns.len() < 2 {
        return Err(pyo3::exceptions::PyValueError::new_err("Need at least 2 return observations"));
    }

    let n = daily_returns.len() as f64;
    let mean: f64 = daily_returns.iter().sum::<f64>() / n;
    let variance: f64 = daily_returns.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / (n - 1.0);
    let std_dev = variance.sqrt();

    // Parallel simulations via rayon
    let finals: Vec<f64> = (0..n_simulations)
        .into_par_iter()
        .map(|_| {
            let mut equity = initial_equity;
            for _ in 0..n_days {
                // Box-Muller transform for normal random sample
                let u1: f64 = fastrand::f64().max(f64::EPSILON);
                let u2: f64 = fastrand::f64();
                let z = (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos();
                let daily_return = mean + std_dev * z;
                equity *= 1.0 + daily_return;
            }
            equity
        })
        .collect();

    Ok(finals)
}

// ── Feature Computation ───────────────────────────────────────────────────────

/// Compute all standard lag features for ML models.
/// Returns a flat Vec of features in consistent order.
#[pyfunction]
fn compute_lag_features(closes: Vec<f64>, lags: Vec<usize>) -> PyResult<Vec<f64>> {
    let n = closes.len();
    if n == 0 {
        return Err(pyo3::exceptions::PyValueError::new_err("Empty closes array"));
    }
    let latest = closes[n - 1];
    let features: Vec<f64> = lags
        .iter()
        .map(|&lag| {
            if lag >= n {
                f64::NAN
            } else {
                let prev = closes[n - 1 - lag];
                if prev == 0.0 { f64::NAN } else { (latest - prev) / prev }
            }
        })
        .collect();
    Ok(features)
}

// ── Module Registration ───────────────────────────────────────────────────────

#[pymodule]
fn profitpilot_math(_py: Python, m: &PyModule) -> PyResult<()> {
    // Indicators
    m.add_function(wrap_pyfunction!(rsi, m)?)?;
    m.add_function(wrap_pyfunction!(sma, m)?)?;
    m.add_function(wrap_pyfunction!(ema, m)?)?;
    m.add_function(wrap_pyfunction!(atr, m)?)?;
    // Statistics
    m.add_function(wrap_pyfunction!(sharpe_ratio, m)?)?;
    m.add_function(wrap_pyfunction!(max_drawdown, m)?)?;
    // Monte Carlo
    m.add_function(wrap_pyfunction!(monte_carlo_returns, m)?)?;
    // Features
    m.add_function(wrap_pyfunction!(compute_lag_features, m)?)?;
    Ok(())
}
