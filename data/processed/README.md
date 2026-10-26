# Processed data guide

Every file here is produced by `python scripts/train.py` or by the notebook, and is ready to load into Tableau Public (CSV, comma-separated, dates in `YYYY-MM-DD` format).

| File | Rows | Grain | Use it for |
|---|---|---|---|
| `sales_clean.csv` | 188,340 | store × day, Jan 2018 to May 2019 | Main Tableau source: trends, segments, discount and holiday impact, orders vs sales |
| `actual_and_forecast.csv` | 210,605 | store × day, Jan 2018 to Jul 2019 | One timeline with actuals (`Type = Actual`) and the June-July 2019 forecast (`Type = Forecast`) |
| `holdout_predictions.csv` | 22,265 | store × day, Apr to May 2019 | Forecast accuracy dashboard: actual vs forecast, error, absolute % error |
| `test_forecast.csv` | 22,265 | store × day, Jun to Jul 2019 | Final forecast for `TEST_FINAL.csv` (has the original `ID`) |
| `store_master.csv` | 365 | store | Store attributes plus average daily sales, total sales, average orders, % of days on discount |
| `model_comparison.csv` | 1 row per model | model | Cross-validated scores of every model (mean of 3 folds) |
| `model_comparison_by_fold.csv` | 1 row per model and fold | model × fold | Scores per fold |
| `chain_model_comparison.csv` | 4 | model | Chain-level comparison: LightGBM vs SARIMAX, Prophet, Holt-Winters |
| `hypothesis_results.csv` | 28 | test | All hypothesis tests with statistics, p-values, effect sizes and conclusions |
| `tuning_trials.csv` | 8 | trial | Hyper-parameter search results |
| `feature_importance.csv` | 22 | feature | Share of LightGBM gain per feature |
| `sales_history.parquet` | 188,340 | store × day | Compact history the app and API load (not needed for Tableau) |

## Column dictionary (`sales_clean.csv`)

| Column | Meaning |
|---|---|
| `ID`, `Store_id`, `Store_Type`, `Location_Type`, `Region_Code`, `Date` | As in the raw data |
| `Holiday` | 1 = public holiday |
| `Discount` | 1 = the store ran a discount that day |
| `Orders` | Number of orders (`#Order` in the raw data) |
| `Sales` | Sales value |
| `Avg_Order_Value` | Sales / Orders (empty when Orders = 0) |
| `Weekday`, `Month`, `Is_Weekend` | Calendar helpers |
| `Discount_Flag`, `Holiday_Flag` | Readable labels for filters and colours |

## Suggested Tableau calculated fields
* **Discount uplift %**: `AVG(IF [Discount]=1 THEN [Sales] END) / AVG(IF [Discount]=0 THEN [Sales] END) - 1`
* **WAPE %** (on `holdout_predictions.csv`): `SUM(ABS([Error])) / SUM([Sales])`
* **Bias %**: `SUM([Error]) / SUM([Sales])`
