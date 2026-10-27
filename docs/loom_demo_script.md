# Loom demo script: Product Sales Forecasting (5 minutes)

**Target length:** 4:45 to 5:00 · about 700 spoken words · speak at a relaxed pace.

## Before you hit record

- [ ] Open these tabs, in this order:
  1. GitHub repo: https://github.com/dot-hpg/sales-forecasting (scrolled to the top of the README)
  2. Notebook on GitHub: `notebooks/Product_Sales_Forecasting.ipynb`
  3. Live app: https://sales-forecasting-hpg.streamlit.app (load it once first so it is awake; Streamlit apps sleep after inactivity)
  4. Tableau Public dashboard: `[TABLEAU LINK]`
- [ ] In the app, start on the **Store forecast** tab with **Store 1**, **61 days**, **Company plan**.
- [ ] Loom: "Screen + Cam", full browser window, close notifications, browser zoom 100 to 110%.
- [ ] Optional: open the app on your phone too, to show it at the end.

---

## 0:00 to 0:25 · Intro (screen: README top)

> Hi, I'm Hariprasad. In this demo I'll show my Product Sales Forecasting project. The goal is to forecast daily sales for 365 retail stores, 61 days ahead, so the business can plan stock, staff and discount campaigns. I'll cover the data and key insights, how I chose the model, and then the live app you can use from a phone.

## 0:25 to 1:20 · Data and insights (screen: Tableau dashboard, or README section 2.2)

*Action: show the trend chart, then the segment and discount/holiday views. Click one filter, for example Store Type = S4.*

> The data has about 188,000 rows: every store, every day, from January 2018 to May 2019, with store type, location, region, holiday and discount flags, orders and sales.
>
> Three things drive sales. Discounts lift sales by about 33%, and that holds in 364 of the 365 stores. Holidays cut sales by 19%, and by almost half from the second day of a long holiday. And weekends are the peak, with Sunday 15% above average.
>
> Store format and location set the level. S4 stores sell more than twice as much as S2. Region, on the other hand, barely matters.

## 1:20 to 2:00 · Hypothesis tests (screen: notebook, hypothesis results table)

*Action: scroll to the hypothesis testing summary table.*

> I tested eight hypotheses with t-tests, ANOVA, Kruskal-Wallis and correlation tests. With 188,000 rows almost every p-value is tiny, so I report an effect size for each test, and I repeated the key tests on store averages so the samples are independent. That's why I can say region is statistically significant but practically small: it explains only about 3% of the variance.

## 2:00 to 3:00 · Modelling (screen: notebook model leaderboard, then README results)

*Action: show the leaderboard chart, then the hold-out actual vs forecast chart.*

> One important decision: the number of orders is 94% correlated with sales, but it's only known after the day ends, so using it would be leakage. I excluded it, and I shifted every rolling sales feature by 61 days, so the model only sees what's known when the forecast is made.
>
> I validated with rolling 61-day folds and compared ten models, from simple baselines through linear regression, random forest, XGBoost and LightGBM. LightGBM won with 15.3% error against 22.8% for a naive forecast. On total chain sales it also beat SARIMAX, Prophet and Holt-Winters.
>
> On a final hold-out of April and May 2019, store-level two-month totals are within about 10%, so roughly 90% accurate for planning.

## 3:00 to 4:20 · Live app (screen: Streamlit app)

*Action: Store forecast tab. Point at the three numbers, the chart and the blue info box.*

> Here's the deployed app. I pick a store, a horizon and a discount plan. For Store 1 over the next 61 days, it forecasts about 2.2 million, and compares that with the same days last year. The orange dots are discount days and the grey bands are holidays.

*Action: change Discount plan to "No discount", then to "Every day", then back to "Company plan".*

> The blue box is the most useful part for the business. The app also runs a no-discount scenario, so it tells you how much the discount plan is worth. If I switch plans, the forecast and the uplift update instantly. That turns the forecast into a campaign-planning tool.

*Action: open "Daily forecast table", tap the CSV download button.*

> There's a daily table and a CSV download for the planning team.

*Action: Chain view tab. Filter Store Type = S4, then switch "Break down by" to Location Type.*

> The chain view shows the June and July forecast for the whole chain, 989.8 million, which I can filter by store type, location and region.

*Action: Model tab, briefly.*

> And the model tab shows the hold-out accuracy and what drives the forecast.

## 4:20 to 4:45 · Deployment and code (screen: README sections 5 and 6)

> There's also a Flask REST API that takes JSON and returns predictions, with a Dockerfile for deployment, and 13 automated tests, including one that checks for leakage. The app and the API share the same forecasting code.

*Optional: show the app on your phone to camera for two seconds.*

## 4:45 to 5:00 · Close (screen: README top)

> To sum up: run discounts on weaker weekdays, cut back for holidays, staff up for weekends, and retrain the model monthly. Everything, including the notebook, the app, the dashboard and my blog post, is linked in the GitHub README. Thanks for watching.

---

## Tips

- If you run long, shorten the hypothesis section (1:20 to 2:00) to one sentence; the app section matters most.
- The Store 1 figure (about 2.2M, discount plan worth about +6%) comes from the current model. If you retrain, read the numbers off the screen instead.
- After recording, set the Loom to "Anyone with the link can view", and send me the link so I can add it to the submission PDF.
