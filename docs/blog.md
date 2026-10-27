# Forecasting Two Months of Sales for 365 Stores: What Worked, What Didn't, and the Feature I Had to Throw Away

*How I built a leakage-free LightGBM forecaster that beats SARIMAX and Prophet, and shipped it as a phone-friendly app and a REST API.*

**By Guntuku Hariprasad** · Code: [github.com/dot-hpg/sales-forecasting](https://github.com/dot-hpg/sales-forecasting) · Live app: [sales-forecasting-hpg.streamlit.app](https://sales-forecasting-hpg.streamlit.app)

---

Every retail chain asks the same question each month: *how much will each store sell next?* Get it wrong in one direction and you are paying for stock that expires on the shelf and staff who stand around. Get it wrong in the other and you lose sales to empty shelves and long queues.

In this project I forecast **daily sales for 365 stores, 61 days ahead** (1 June to 31 July 2019) from 17 months of history. This post walks through the whole pipeline: the data checks, what the exploratory analysis and hypothesis tests revealed, the ten models I compared, the one very tempting feature I had to drop, and how the final model ended up in a web app you can use from your phone.

## The data

The training file has **188,340 rows**: 365 stores × 516 days, from 1 January 2018 to 31 May 2019. Each row has:

- **Store attributes:** store type (S1 to S4), location type (L1 to L5) and region (R1 to R4)
- **Plan inputs:** a holiday flag and a discount flag
- **Outcomes:** the number of orders (`#Order`) and **sales**, the target

The test file has 22,265 rows for June and July 2019. It contains the holiday calendar and the discount plan, **but no orders and no sales**. That one detail shapes the whole project, and I will come back to it.

### Data quality first

The data was unusually clean: no missing values, no duplicates and a complete store × date grid. Store attributes never change and holidays are one chain-wide calendar. Two things still needed a decision:

1. **19 rows with zero sales**, all with zero orders and in runs of two to three days. These are store closures, not demand. I dropped them from training and from MAPE (a zero in the denominator makes MAPE meaningless).
2. **3.1% of rows are high outliers** by the IQR rule. Before deleting anything I checked *when* they happen: 73% of them are discount days. They are real promotion peaks, the exact behaviour the model needs to learn, so I kept them and modelled log-sales to limit their pull.

The lesson: an outlier rule finds unusual rows, but it can't tell you whether they are errors. Only the context can.

## What the data says

![Daily chain sales, 2018 to May 2019](https://raw.githubusercontent.com/dot-hpg/sales-forecasting/main/reports/figures/06_daily_sales_trend.png)

The exploratory analysis gave a clear picture of what moves sales:

| Driver | Effect |
|---|---|
| Discount days | **+32%** on average; +33.5% within the same store, and higher in **364 of 365** stores |
| Holidays | **−19%**; **−48%** from the second day of a multi-day holiday |
| Weekends | Sunday **+15%**, Saturday **+9%**; Friday is the weakest day (−7%) |
| Store type | S4 averages 59.9K per day, S2 only 27.5K |
| Location type | L2 averages 59.2K per day, L5 only 25.2K |
| Region | Small: 39.7K to 46.8K per day |
| Orders | Correlation with sales **r = 0.94** |

A few findings surprised me.

**Holidays reduce sales.** I expected holiday shopping peaks. In this chain, holidays mean closed offices and quieter neighbourhoods, and the second day of a long holiday is almost half as busy as a normal day.

**Discounts are chain-wide campaigns, not store decisions.** On 49% of days, either more than 90% or fewer than 10% of stores are on discount at the same time. That made "share of stores on discount today" a useful feature, because it separates a big national campaign from a scattered local one.

**S4 stores are busy, not premium.** S4 has the highest sales but the *lowest* average basket value. Its sales come from many small orders, which matters for staffing more than for stock mix.

**There is no long-term trend.** The series is stationary (ADF p = 0.007) with seasonal highs in January, May, July and December. But **May 2019 was a record month, +10% on May 2018**, right at the end of the history. Keep that in mind for the results.

![Sales by store type, location and region](https://raw.githubusercontent.com/dot-hpg/sales-forecasting/main/reports/figures/03_sales_by_segment.png)

## Hypothesis testing without fooling yourself

The brief asked for t-tests, ANOVA, Kruskal-Wallis and correlation tests on discounts, holidays, store types, regions and orders. Running them is easy. Running them honestly takes two extra steps.

**1. With 188,000 rows, everything is "significant".** Almost every p-value came out below 1e-300, which tells you nothing about whether an effect matters. So every test in the notebook reports an **effect size** next to the p-value: Cohen's d for t-tests, η² for ANOVA, ε² for Kruskal-Wallis and rank-biserial r for Mann-Whitney.

**2. Store-days are not independent.** Store 12's Monday and Tuesday are related, so treating 188,000 rows as independent samples overstates the evidence (pseudo-replication). I repeated each key test on **store-level means**, for example a paired t-test and Wilcoxon test comparing each store's discount and non-discount average. That gives 365 honest data points.

| Hypothesis | Tests | Result |
|---|---|---|
| Discounts raise sales | Welch t, Mann-Whitney, paired t, Wilcoxon | Reject H0: +33.5% per store, d = 0.69 |
| Holidays change sales | same | Reject H0: −19.1%, lower in every store |
| Store type matters | ANOVA, Welch ANOVA, Kruskal-Wallis, Tukey | Reject H0: η² = 0.72 between stores |
| Location type matters | same | Reject H0: η² = 0.70 |
| Region matters | same | Reject H0, **but small**: η² = 0.03 to 0.05 |
| Weekends sell more | t, Mann-Whitney, paired tests | Reject H0: +17.5% per store |
| Orders correlate with sales | Pearson, Spearman | Reject H0: r = 0.94 |
| Discount uplift differs by segment | Two-way ANOVA on log-sales | Reject H0, **negligible**: 30 to 34% everywhere |

The region result is the best example of why effect sizes matter. Region is "statistically significant" with a p-value of 2e-4 even at store level, yet it explains about 3% of the variance. For the business, the honest answer is "region barely matters; format and location do."

## The feature I had to throw away

`#Order` correlates with sales at **0.94**. Put it in a model and the error collapses. It is also useless.

The number of orders on a day is only known **after that day ends**, at the same moment as sales. The test file doesn't contain it, and a store manager planning July has no idea how many orders July will bring. A model that uses it is answering "if I told you today's orders, what were today's sales?", which nobody needs answered. This is **target leakage**, and it is the most common way forecasting projects look great in a notebook and fail in production.

I applied the same rule to every feature: *is this value known on the day the forecast is made?* That led to a second, quieter decision. I wanted each store's recent sales level as a feature (rolling 7, 28 and 91-day means), but the forecast for 31 July is made on 31 May, with no actual sales for June and July. So every rolling feature is **shifted by 61 days**, the full forecast horizon. The model trains on exactly the information it will have at prediction time. There is a unit test in the repo that fails if any feature uses data from inside the horizon.

The final feature set:

| Group | Features |
|---|---|
| Plan inputs | Holiday, Discount |
| Store identity | Store id (categorical), store type, location type, region |
| Calendar | Weekday, weekend, month, start and end of month |
| Holiday proximity | Days since and until a holiday, holiday yesterday and tomorrow |
| Campaign context | Discount yesterday and tomorrow, consecutive discount days, share of stores on discount |
| Store level | Rolling 7, 28 and 91-day mean of log-sales, shifted 61 days |

## Validating like it's the real thing

A random train/test split would let the model learn from August to predict July. Instead I used **rolling-origin cross-validation** with three folds, each forecasting **61 days**, the real horizon: December to January, February to March, and April to May. Every model was trained only on data before its fold.

My main metric is **WAPE** (weighted absolute percentage error: total absolute error divided by total sales). It reads as "the share of sales we get wrong", and unlike MAPE it isn't blown up by a few small days. I report MAE, RMSE, MAPE and R² as well.

## Ten models, one winner

I started with simple baselines, since a model that can't beat them isn't worth deploying, and worked up from there.

| Model (mean of 3 folds) | WAPE % | MAPE % | RMSE | R² |
|---|---|---|---|---|
| Store 91-day average | 23.6 | 31.0 | 14,486 | 0.44 |
| Seasonal naive (weekday mean) | 22.8 | 30.5 | 13,894 | 0.49 |
| Weekday mean × discount/holiday ratio | 18.7 | 23.6 | 11,887 | 0.62 |
| Linear regression (Ridge) | 18.9 | 22.4 | 11,849 | 0.63 |
| Random forest | 18.4 | 20.8 | 11,644 | 0.64 |
| XGBoost | 15.4 | 17.4 | 10,060 | 0.73 |
| **LightGBM** | **15.3** | **17.4** | **10,008** | **0.73** |

![Model leaderboard](https://raw.githubusercontent.com/dot-hpg/sales-forecasting/main/reports/figures/14_model_leaderboard.png)

Two things stand out. First, a hand-built baseline (the weekday average scaled by discount and holiday ratios) already beats linear regression. The structure of this problem is mostly multiplicative effects, and a good baseline captures most of it. Second, the gradient-boosted trees pull clearly ahead, cutting a third of the naive error. XGBoost and LightGBM are tied. I picked LightGBM because it trained twice as fast, which matters when you retrain every month.

**What about classical time-series models?** SARIMA, Prophet and Holt-Winters model a single series, and fitting 365 of them is slow and fragile. So I compared them where they are strongest, on **total chain sales per day**, against the LightGBM store forecasts summed up:

| Chain-level model | WAPE % |
|---|---|
| **LightGBM (sum of 365 store forecasts)** | **10.4** |
| SARIMAX(1,0,1)(1,0,1)₇ + discount, holiday | 14.2 |
| Prophet + discount, holiday | 17.2 |
| Holt-Winters (damped, weekly) | 18.1 |

One global model trained across all stores beats specialised time-series models on their home turf. It sees 365 versions of every holiday and campaign instead of one, and learns shared patterns that a single series cannot.

**What didn't help**, which is just as useful to know:

- **Raw lags and day-of-year** made WAPE *worse* (15.9%). With only 17 months of history, day-of-year lets the model memorise 2018 quirks.
- **Hyperparameter tuning**: a random search over eight configurations landed between 15.4% and 15.8%, never beating the defaults. I kept the defaults.
- **Removing store id** raised WAPE to 18.6% and **removing the campaign features** raised it to 18.1%, confirming both groups earn their place.
- **LSTM**: I chose not to. With 516 days per store and demand driven by known events, boosted trees are stronger, cheaper and easier to explain. A deep model would need far more history to compete.

## The final test

For the final check, I trained on data up to 31 March 2019 and forecast **1 April to 31 May 2019**, 61 days ahead, through the exact same code path the app uses.

| Level | WAPE | R² |
|---|---|---|
| Store × day | 16.8% | 0.67 |
| Store × week | 13.2% | 0.73 |
| **Store × 61-day total** | **10.5%** | **0.83** |
| Chain × day | 11.6% | 0.42 |

![Hold-out: actual vs forecast](https://raw.githubusercontent.com/dot-hpg/sales-forecasting/main/reports/figures/15_holdout_actual_vs_forecast.png)

For the decisions a planner actually makes, store-level totals for the month, the forecast is **about 90% accurate**, and the error is even across store types, locations and regions (14 to 18%).

The forecast is **9.8% low** on this hold-out. Remember the record May? The model had never seen a month like it. Earlier folds had biases from −10.5% to +4.5%, so this isn't a fixed offset to correct. It is level drift, and the fix is operational: **retrain monthly and alert if bias exceeds ±5%**.

What does the model rely on? Store type and store identity set the level (40% of the gain together), then discount, location, month and the holiday features shape the days. Region contributes almost nothing, which matches the hypothesis tests exactly. I like it when the EDA and the model tell the same story.

![SHAP summary](https://raw.githubusercontent.com/dot-hpg/sales-forecasting/main/reports/figures/19_shap_summary.png)

Retrained on all the data, the model forecasts **989.8M in total sales for June and July 2019**, 2.6% below the same months of 2018.

## From notebook to something people can use

A forecast in a notebook helps nobody, so I deployed it two ways.

**A Streamlit web app** ([live here](https://sales-forecasting-hpg.streamlit.app)), designed to work on a phone, because store managers don't sit at desks. It has four tabs:

- **Store forecast**: pick any of the 365 stores, a horizon from 7 to 120 days and a discount plan (company plan, none, weekends only or every day), and add extra holidays. It shows the forecast chart, the comparison with last year, a daily table and a CSV download. It also runs a **no-discount scenario** in the background and tells you how much the discount plan is worth. That turns the forecaster into a campaign-planning tool.
- **Chain view**: the June and July forecast for the whole chain, filterable by store type, location and region.
- **Insights** and **Model**: the key EDA effects, hold-out accuracy and feature importance.

![The app on a phone](https://raw.githubusercontent.com/dot-hpg/sales-forecasting/main/reports/app_screenshots/app_mobile_store.png)

**A Flask REST API**, as the brief asked, for systems rather than people. `POST /predict` takes JSON rows with a store id, a date, a holiday flag and a discount flag, and returns predicted sales. Invalid input returns a clear HTTP 400. It ships with a Dockerfile and a Render blueprint. Both the app and the API use the same `forecasting` package, so there is exactly one implementation of the features. That is the simplest way to make sure training and serving can't drift apart. Thirteen pytest tests cover the features, the leakage guard, the model and the API.

## What the business should do

The analysis points to concrete actions:

1. **Run discounts on weaker days and months.** Discounts lift sales about 33% almost everywhere, so use them where there is spare capacity: Tuesday to Friday, February and November. Measure each campaign against the model's no-discount scenario rather than against last week.
2. **Mind the pre-campaign dip.** Many stores sell less on the day before a campaign, as customers wait. Announce campaigns on the day they start.
3. **Cut back for holidays, especially long ones.** Reduce staff and fresh stock on holidays (−19%), and more from the second day (−48%).
4. **Staff up for weekends** (+17.5% per store).
5. **Plan stock at store-week or store-month level**, where the forecast is 87 to 90% accurate, and keep about a 17% buffer for single days where stock-outs are costly.
6. **Prioritise S4 and S3 formats in L2 and L1 locations**, and review the S2 and L5 stores that sell less than half as much.
7. **Retrain monthly, monitor bias, and collect better data**: discount depth, prices, footfall and local events would sharpen the campaign estimates most.

## Lessons learned

- **Ask "would I know this on the day?" of every feature.** The most predictive column in the dataset was the one I couldn't use.
- **Validate the way you will forecast.** Rolling 61-day folds made the cross-validation scores match the final hold-out closely.
- **Report effect sizes.** With big data, a p-value only tells you the sample was large.
- **Build strong baselines.** A two-line baseline beat linear regression and set an honest bar for everything else.
- **One global model beats many local ones** when series share structure.
- **Ship it.** A phone-friendly app with a scenario switch is worth more to a planner than a better decimal in a notebook.

The full notebook, code, app and API are on GitHub at [dot-hpg/sales-forecasting](https://github.com/dot-hpg/sales-forecasting). If you try the app, I'd love to hear what you would add next.

*Tags: Data Science, Time Series Forecasting, Machine Learning, LightGBM, Retail Analytics*
