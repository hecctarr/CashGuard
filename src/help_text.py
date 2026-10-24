"""Plain-language help shown behind the ❓ button on every page, plus short glossary tips."""

GLOSSARY = {
    "cushion": "**Safety cushion** = the smallest amount of cash you always want in the bank "
               "(the 'minimum reserve'). You set it in Settings. Going below it is what CashGuard calls "
               "'running short'.",
    "futures": "**Simulated futures** = CashGuard plays out the next 30 days 1,000 times. Each time, sales "
               "and customer payments land a little differently, based on your real history. "
               "If cash drops below your safety cushion in 220 of the 1,000, the risk is 22%.",
    "risk": "**Chance of running short** = the share of simulated futures where cash drops below your "
            "safety cushion at least once in the next 30 days. 🟢 Low under 5% · 🟡 Medium 5–20% · "
            "🔴 High over 20%.",
    "band": "**Where cash will likely stay** = in 9 out of 10 simulated futures, cash stays inside this shaded "
            "band. The dark line is the most likely path.",
}

HOW_IT_WORKS = """
**1. Your bills and customers.** Invoices arrive on WhatsApp or are uploaded. Staff check the details.

**2. When will customers really pay?** CashGuard learns from each customer's past invoices how late they usually
pay (*survival analysis*, the same maths insurers use for "how long until…"). Customers with little history are
blended with the average customer (*credibility weighting*), so one invoice can't fool it.

**3. 1,000 possible next months.** It replays the next 30 days 1,000 times with realistic ups and downs in sales,
late payments and a surprise cost now and then (*Monte Carlo simulation*).

**4. One clear number.** The share of those futures where cash drops below your safety cushion is your
**chance of running short**. It then tries other pay dates (never after the due date) and suggests the safest.

**5. You decide.** CashGuard never pays anything. Every decision is saved in a log that can't be edited.
"""

PAGE_HELP = {
    "Dashboard": ("Your cash at a glance",
        "This is the Owner's home page. It answers one question: **will I have enough cash for the next 30 days?**\n\n"
        "- **Big card:** your chance of running short and the day the danger starts.\n"
        "- **Needs your attention:** what to do first: bills to review, customers to chase, things to know.\n"
        "- **Chart:** the most likely path of your cash, and the band it will stay in 9 times out of 10.\n"
        "- **Payment calendar:** every bill out and payment in. Red rows = cash would be below your safety cushion.",
        "The % comes from 1,000 simulated futures (Monte Carlo). Customer payment dates are drawn from each "
        "customer's own payment history (Kaplan-Meier survival curve + Bühlmann credibility). Daily sales are "
        "re-sampled from your past weekday and weekend sales."),
    "Review & decide": ("Should I pay this bill today?",
        "Pick a bill or a staff request. CashGuard shows the **risk if you pay today** and the **safest date** "
        "that is still on time, with a plain reason. Then you choose: pay now, schedule, or hold.\n\n"
        "Managers only see items inside the limits the Owner set. Nobody can approve their own submission.",
        "Each possible date is tested on the same 1,000 futures (same random seed), so the comparison is fair. "
        "The suggested date is the earliest date with Low risk; if none is Low, the date with the lowest risk. "
        "It is never after the due date."),
    "Invoices": ("All bills and customer invoices",
        "**Bills to pay** lists every supplier bill and its status; record a transfer here once it has gone out. "
        "**Customers owe you** shows who still owes money, when CashGuard expects them to pay, and whether they "
        "are usually on time.",
        "Expected payment date = due date + the customer's usual delay, learned from their past invoices "
        "(survival analysis). Customers with little history are blended with the average customer "
        "(credibility weighting), so one invoice can't fool it."),
    "What-if simulator": ("Try a bad month before it happens",
        "Move the sliders or press a preset (Bad month, Surprise repair) to see how your "
        "risk changes. Nothing here changes your real data.",
        "The same Monte Carlo model is re-run with your changes: sales scaled down, an extra cost added, or one "
        "customer's payment delayed by extra days."),
    "Does it work? (Test)": ("Proof that it helps",
        "We tested CashGuard on 50 made-up bill situations. For each one we compared 'pay straight away' with "
        "'pay on CashGuard's date' and counted how often cash ran short.",
        "Out-of-sample test: each situation is judged on 300 fresh futures drawn from the hidden rules that "
        "created the demo data, not from CashGuard's own model, so it can't mark its own homework. "
        "The page also checks the payment predictions against invoices the model never saw. All data is synthetic."),
    "Upload bill": ("Get invoices into CashGuard",
        "Invoices sent to the business WhatsApp land here automatically. You can also upload a photo or PDF. "
        "AI reads the supplier, amount and dates; **you check them** before saving. Suppliers without an "
        "invoice can fill in the WhatsApp form and CashGuard makes the PDF for them.",
        "Checks run before saving: duplicate invoice numbers, line items that don't add up, due dates in the "
        "past, unknown sender numbers and changed bank details (a common fraud pattern)."),
    "New expense request": ("Ask to spend money",
        "Choose what the money is for, the amount and why. Requests above your category limits are blocked "
        "automatically. The Owner (or a Manager, for small amounts) decides.",
        "Limits are per person, per category, per month. The Owner sets them in Settings."),
    "My submissions": ("What happened to my requests",
        "See the bills you uploaded, your expense requests and what was decided.", ""),
    "Audit log": ("Who did what, and when",
        "Every sign-in, upload, risk check and decision is written here. Entries can be added but **never edited "
        "or deleted**, so there is always a fair record.", ""),
    "Settings": ("Your rules",
        "Set your **safety cushion**, risk levels, Manager limits, staff spending limits and WhatsApp details. "
        "Under **Team & sign-in**, add people, reset passwords and remove accounts. Only the Owner can open this page.",
        "Passwords are never stored. CashGuard keeps only a salted PBKDF2-SHA256 hash."),
}
