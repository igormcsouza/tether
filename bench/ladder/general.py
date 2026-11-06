"""Everyday non-coding work: content, qa, critique and extract, a few rising tiers each (imported by tasks.py).

The inputs are short self-contained texts in the workspace (no web, no `shop` project). Grading is
deterministic: `checks` are (label, fn(text) -> bool) on the deliverable (length, required facts,
banned words, numbers not in the source, per-answer regexes, JSON schema and values); `critique`
reuses the review grader (planted flaws recalled, false alarms cost points).
"""
import json
import re

from tasks import Task, add
from tether.schema import validate_output


# ---------------------------------------------------------------- check helpers
def nwords(text):
    return len(re.findall(r"\w[\w'’.,/:-]*", text))


def lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def words(lo, hi):
    return (f"{lo}-{hi} words", lambda t: lo <= nwords(t) <= hi)


def has(label, *pats):
    return (label, lambda t: all(re.search(p, t, re.I | re.S) for p in pats))


def lacks(label, *pats):
    return (label, lambda t: not any(re.search(p, t, re.I | re.M) for p in pats))


def numbers(text):
    return {n.replace(",", "") for n in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", text)}


def source_numbers(src):
    # ponytail: numbers under 10 are always allowed ("three bullets", "2 engineers"); invented ones are bigger
    return ("invented numbers", lambda t: all(n in numbers(src) or float(n) < 10 for n in numbers(t)))


def answers(text):
    """{n: answer} from lines like `Q1: ...`, `**Q2.** ...`, `3) ...`; continuation lines join their answer."""
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"\s*[-*#]*\s*\**\s*Q?(\d+)\s*\**\s*[.:)]\**\s*(.*)", line, re.I)
        if m:
            cur = int(m.group(1))
            out[cur] = m.group(2).strip()
        elif cur is not None and line.strip():
            out[cur] += "\n" + line.strip()
    return out


def ans(n, must, must_not=None):
    def ok(t):
        a = answers(t).get(n, "")
        return bool(a) and re.search(must, a, re.I | re.S) and not (must_not and re.search(must_not, a, re.I))
    return (f"Q{n}", ok)


NOT_IN = (r"(not (in|stated|mentioned|given|specified|covered|answered)|(doesn'?t|does not|do not|don'?t) "
          r"(say|mention|state|specify|cover|answer)|no (information|mention)|(isn'?t|is not) (stated|mentioned|covered))")


def parse_json(text):
    raw = text.strip()
    if raw.startswith("```"):  # same tolerance as tether's --output-schema gate
        raw = raw.strip("`").removeprefix("json").strip()
    try:
        return json.loads(raw)
    except ValueError:
        return None


def schema(s):
    return ("schema-valid JSON", lambda t: validate_output(t, s) is None)


def norm(v):
    if isinstance(v, str):
        return v.strip().lower()
    if isinstance(v, list):
        return [norm(x) for x in v]
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return round(float(v), 2)
    return v


def field(label, get, want):
    def ok(t):
        try:
            return norm(get(parse_json(t))) == norm(want)
        except (KeyError, TypeError, IndexError, AttributeError):
            return False
    return (label, ok)


def products_ok(t, want):
    """null where none is named, else a name starting with the expected one ("Lumen Desktop 2.0.3" is fine)."""
    d = parse_json(t)
    try:
        got = [x["product"] for x in d]
    except (KeyError, TypeError):
        return False
    return len(got) == len(want) and all(
        g is None if w is None else isinstance(g, str) and g.lower().startswith(w.lower()) for g, w in zip(got, want))


# ================================================================= CONTENT
C_BOIL = " Write only the finished text to {f}, nothing else in the file."
add(Task(
    "content-1", "content", 1,
    "Write a short announcement for the release of Lumen 2.0, a note-taking app. At most 80 words. It must "
    "mention offline sync, the price ($4 per month) and the release date, 12 March. Do not use the words "
    "\"revolutionary\", \"game-changer\" or \"seamless\"." + C_BOIL.format(f="post.md"),
    deliverable="post.md",
    checks=[words(1, 80), has("product name", r"Lumen 2\.0"), has("offline sync", r"offline"),
            has("price", r"\$ ?4\b"), has("date", r"(12(th)? March|March 12)"),
            lacks("banned words", r"revolutionary", r"game.?changer", r"seamless")],
))
ARTICLE = """# Riverton's bike-share turns three

Riverton launched its public bike-share in April 2023 with 40 stations and 400 bikes. Three years later the
network has grown to 95 stations and 1,100 bikes, 300 of them electric.

Riders made 1.2 million trips in 2025, up from 450,000 in the first year. The average trip lasted 14 minutes.
The city says 38% of trips replaced a car journey, based on a survey of 2,000 riders.

The program cost €3.1 million to set up. Annual running costs are €1.4 million, of which fares and
sponsorship cover €1.1 million; the city pays the rest.

Not everything went to plan. Electric bikes are out of service twice as often as regular ones, mostly because
of battery theft, and the eastern districts still have only 6 stations. The council has approved 20 new
stations there for 2026.

Mayor Lena Hoffmann called the program "a quiet success" and said fares will stay at €1 per 30 minutes.
"""
add(Task(
    "content-2", "content", 2,
    "Summarise article.md for a city newsletter in one paragraph of 50 to 90 words, no bullet points. Keep the "
    "trip numbers, the size of the network and the plan for the east. Use only numbers that are in the "
    "article." + C_BOIL.format(f="summary.md"),
    files={"article.md": ARTICLE}, deliverable="summary.md",
    checks=[words(50, 90), has("trips", r"1\.2 million"), has("network size", r"(95 stations|1,?100 bikes)"),
            has("plan for the east", r"(east.{0,120}\b20\b|\b20\b.{0,120}east)"),
            lacks("no bullets", r"^\s*([-*+]|\d+[.)])\s"), source_numbers(ARTICLE)],
))
NOTES = """Team sync, 4 Feb
- shipped Lumen 2.0 early!!
- 18,000 sign-ups first week, goal was 10k
- top request: dark mode (~40% of feedback), ships in April
- hiring: 2 backend engineers, remote OK, apply via lumen.example/jobs
- Dmitri's db migration still flaky, don't mention outside the team
- pricing change under discussion, NOT public yet
"""
add(Task(
    "content-3", "content", 3,
    "Turn the meeting notes in notes.md into a public LinkedIn post for the company page. Rules: 100 to 170 "
    "words; the first line is a headline written as `# <headline>` of at most 10 words; exactly 3 bullet "
    "points; the last line is a question to the readers; no hashtags; no emojis. Include the sign-up number, "
    "dark mode coming in April and the job opening with its link. Leave out anything the notes mark as "
    "internal or not public. Do not use the words synergy, leverage, delve or thrilled." + C_BOIL.format(f="post.md"),
    files={"notes.md": NOTES}, deliverable="post.md",
    checks=[words(100, 170),
            ("headline", lambda t: bool(lines(t)) and re.match(r"#\s+\S", lines(t)[0]) is not None
             and nwords(lines(t)[0]) <= 10),
            ("3 bullets", lambda t: len(re.findall(r"^\s*[-*+]\s", t, re.M)) == 3),
            ("ends with a question", lambda t: bool(lines(t)) and lines(t)[-1].endswith("?")),
            has("sign-ups", r"18,?000|18k"), has("dark mode in April", r"dark mode", r"April"),
            has("job link", r"lumen\.example/jobs"),
            lacks("internal kept out", r"Dmitri", r"migration", r"pricing"),
            lacks("banned words", r"synergy", r"leverag", r"delve", r"thrilled", r"(^|\s)#\w")],
))
INCIDENT = """INTERNAL - Incident report INC-208
Date: 21 Feb 2026, 14:05-14:52 UTC (47 minutes)
Impact: Lumen sync unavailable for all users; notes edited offline were kept and synced after recovery.
No data lost.
Root cause: Dmitri Volkov ran a schema migration on db-prod-3 without the usual canary step; the migration
locked the notes table.
Fix: migration rolled back at 14:49, sync recovered at 14:52.
Follow-up: canary step made mandatory (owner: Dmitri); add lock-timeout alerts.
Customer comms: apologise, explain in plain words, no internal names, hostnames or ticket numbers. Every
paying user gets a 10% credit on the March invoice automatically.
"""
add(Task(
    "content-4", "content", 4,
    "Rewrite the internal incident report in incident.md as an email to customers, following its "
    "\"Customer comms\" line. The first line is `Subject: ...`; at most 150 words; keep the date, how long sync "
    "was down, that no data was lost and the credit; sign off with `The Lumen team` as the last line."
    + C_BOIL.format(f="email.md"),
    files={"incident.md": INCIDENT}, deliverable="email.md",
    checks=[words(1, 150), ("subject line", lambda t: bool(lines(t)) and lines(t)[0].lower().startswith("subject:")),
            has("date", r"(21(st)? Feb|Feb\w* 21)"), has("duration", r"47 min"),
            has("no data lost", r"(no (data|notes?)\b.{0,20}lost|nothing was lost|(did not|didn'?t|not) lose)"),
            has("credit", r"10 ?%", r"March"), has("apology", r"(sorry|apologi)"),
            lacks("no internal details", r"Dmitri", r"Volkov", r"db-prod", r"INC-208", r"canary"),
            ("sign-off", lambda t: bool(lines(t)) and lines(t)[-1].lower().rstrip(".,!") == "the lumen team")],
))

# ================================================================= QA
HANDBOOK = """# Northwind Coworking: member handbook

## §1 Plans
- Day pass: €20 per day, no booking needed.
- Flex: €180 per month, 10 days per month. Unused days do not roll over.
- Resident: €320 per month, a fixed desk and a locker.

## §2 Opening hours
The space is open Monday to Friday 7:00-21:00 and Saturday 9:00-17:00. It is closed on Sundays and public
holidays. Resident members have 24/7 access with their key card.

## §3 Meeting rooms
Flex members get 2 hours of meeting-room time per month, Resident members get 6 hours. Extra time costs €15
per hour. Rooms are booked in the member app, at most 14 days ahead.

## §4 Guests
Members may bring up to 2 guests per day. Guests sign in at reception and must leave by 18:00.

## §5 Cancellation
Flex and Resident plans are cancelled with 30 days' notice, by email to hello@northwind.example.

## §6 Amendments
From 1 May the day pass costs €25. All other prices stay the same.
"""
EMAIL = """From: Carla Diaz, community manager
Date: 20 May
To: all members

Two corrections to the handbook:
1. From 1 June members may bring up to 3 guests per day.
2. The handbook is wrong about meeting rooms for Residents: their allowance is 8 hours per month, not 6.
"""
Q_BOIL = (" Write the answers to answers.md, one per line as `Q1: <answer>`, `Q2: <answer>` and so on. Answer "
          "only from the text. Start a yes/no answer with Yes or No.")
add(Task(
    "qa-1", "qa", 1,
    "Answer from handbook.md. Q1: What does the Flex plan cost per month? Q2: What are the opening hours on "
    "Saturday? Q3: How many guests may a member bring per day?" + Q_BOIL,
    files={"handbook.md": HANDBOOK}, deliverable="answers.md",
    checks=[ans(1, r"180"), ans(2, r"9(:00)?\s*(am)?\s*(-|–|to|until)\s*17|9\s*am.*5\s*pm"), ans(3, r"\b2\b|two")],
))
add(Task(
    "qa-2", "qa", 2,
    "Answer from handbook.md. Q1: How many hours of meeting-room time do Resident members get per month? "
    "Q2: How much notice is needed to cancel a Flex plan? Q3: Can a Flex member carry unused days over to the "
    "next month? Q4: Is there parking for members? If the handbook does not answer a question, write "
    "`Not in the document.`" + Q_BOIL,
    files={"handbook.md": HANDBOOK}, deliverable="answers.md",
    checks=[ans(1, r"\b6\b|six"), ans(2, r"30 days|thirty days"), ans(3, r"^\W*no\b"), ans(4, NOT_IN, r"^\W*yes")],
))
add(Task(
    "qa-3", "qa", 3,
    "Answer from handbook.md; read all of it, later sections can change earlier ones. Q1: What does a day pass "
    "cost on 10 May? Q2: A Flex member uses 5 hours of meeting rooms in one month. What do they pay for "
    "meeting rooms that month? Q3: Can a Flex member work in the space at 22:00 on a Tuesday? Q4: Is there a "
    "phone booth? Q5: Can a guest stay until 19:00? Give a number as the answer where one is asked. If the "
    "handbook does not answer a question, write `Not in the document.`" + Q_BOIL,
    files={"handbook.md": HANDBOOK}, deliverable="answers.md",
    checks=[ans(1, r"\b25\b", r"\b20\b"), ans(2, r"\b45\b", r"\b75\b"), ans(3, r"^\W*no\b"),
            ans(4, NOT_IN, r"^\W*yes"), ans(5, r"^\W*no\b")],
))
add(Task(
    "qa-4", "qa", 4,
    "Answer from handbook.md and email.md as of 15 June; a later source wins over an earlier one. After each "
    "answer give its source in brackets: [handbook §N] or [email]. Q1: How many guests may a member bring per "
    "day? Q2: How many meeting-room hours do Resident members get per month? Q3: What does the Resident plan "
    "cost? Q4: How much does a locker cost for a Flex member? Q5: How far ahead can a meeting room be booked? "
    "If neither document answers a question, write `Not in the documents.`" + Q_BOIL,
    files={"handbook.md": HANDBOOK, "email.md": EMAIL}, deliverable="answers.md",
    checks=[ans(1, r"\b3\b.*email|email.*\b3\b", r"\b2\b"), ans(2, r"\b8\b.*email|email.*\b8\b", r"\b6\b"),
            ans(3, r"320.*(§ ?1\b|section 1\b)"), ans(4, NOT_IN, r"€"),
            ans(5, r"14.*(§ ?3\b|section 3\b)")],
))

# ================================================================= CRITIQUE (item recall, like review)
K_BOIL = (" Write your critique to critique.md as a list, one bullet per real problem, most serious first. "
          "Report only real problems, not style.")
BUDGET = """# Community garden: budget request

We ask the council for €7,500 to open the garden in spring.

| Item | Cost |
|---|---|
| Raised beds (10) | €3,000 |
| Tools and shed | €2,500 |
| Water connection | €2,000 |
| Soil and seeds | €1,500 |
| **Total** | **€7,500** |

Volunteers from the residents' association will run the garden, so there are no staff costs.
"""
add(Task(
    "critique-1", "critique", 1, "Review the budget request in budget.md." + K_BOIL,
    files={"budget.md": BUDGET}, deliverable="critique.md",
    rubric=[("total does not add up", [r"(9[,.]?000|do(es)?n'?t add up|does not add up|adds? up to|sum|miscalculat|arithmetic)"])],
))
LIBRARY = """# Proposal: open the library until 22:00

We surveyed 12 people at the Tuesday book club and 11 of them want later opening. So 92% of our 8,000
members want the library open until 22:00.

Plan:
1. Week 1: announce the new hours in the newsletter.
2. Week 2: start the late opening with the extra evening staff.
3. Week 3: hire two extra evening staff.
4. Week 4: review the visitor count.

Cost: two part-time staff, €3,200 per month, paid from the events budget, which has €40,000 left for the
remaining 7 months of the year.
"""
add(Task(
    "critique-2", "critique", 2, "Review the proposal in proposal.md before it goes to the board." + K_BOIL,
    files={"proposal.md": LIBRARY}, deliverable="critique.md",
    rubric=[("unrepresentative sample", [r"(12|book club|sample|survey|92)", r"(small|bias|self.?select|representative|generali[sz]|selection|extrapolat)"]),
            ("staff hired after opening", [r"(week ?2|week ?3|hire|hiring|staff)", r"(before|after|order|sequence|not yet|only hired|depend)"])],
    herrings=[r"(events budget|40[,.]?000|3[,.]?200).{0,80}(not enough|insufficient|too small|run out|exceed)"],
))
FRESHBOX = """# Idea: FreshBox, salad delivery for offices

- We deliver a fresh salad to office workers at lunch for €5.
- Each delivery costs us €4 for ingredients plus €2.50 for the courier.
- New customers get a 14-day free trial.
- Market: 50,000 office workers in the city. If 10% order every working day we sell 5,000 salads a day.
- We will reach that within 3 months with no marketing budget, through word of mouth.
- Only our founder, Ana, knows the recipes and the suppliers.
"""
add(Task(
    "critique-3", "critique", 3, "A friend asks for honest feedback on the business idea in idea.md." + K_BOIL,
    files={"idea.md": FRESHBOX}, deliverable="critique.md",
    rubric=[("loses money per salad", [r"(cost|courier|ingredient|margin|unit economics|price)", r"(6[.,]50?|1[.,]50|loss|lose|losing|negative|more than|exceeds|unprofitable|below cost)"]),
            ("adoption assumption", [r"(10 ?%|5[,.]?000|word of mouth|3 months|three months|no marketing|adoption)", r"(unrealistic|optimistic|assum|unlikely|aggressive|unsupported|no evidence|ambitious)"]),
            ("key person", [r"(Ana|founder|recipes|suppliers)", r"(single point|key.?person|depend|bus factor|risk|only one|knows)"])],
    herrings=[r"(free trial|14.day).{0,60}(too short|too long)", r"5[,.]?000.{0,60}(wrong|incorrect|miscalculat|should be)"],
))
MEMO = """# Memo: make remote work permanent

Since we allowed remote work in March 2025, revenue rose 18%. Remote work clearly caused the growth, so we
should make it permanent for everyone.

We asked the teams that switched to remote work and are still with us: all of them report higher
satisfaction, so remote work makes every team happier.

Productivity in our best quarter, Q3 2025, was 25% above the 2024 average.

Making remote work permanent costs nothing: we only need to give up the office lease and buy every employee a
€1,200 home-office kit.

The office lease ends in June 2026, so the timing is good. Our competitor Acme went fully remote in 2023.
"""
add(Task(
    "critique-4", "critique", 4, "Review the reasoning in memo.md before leadership votes on it." + K_BOIL,
    files={"memo.md": MEMO}, deliverable="critique.md",
    rubric=[("correlation is not causation", [r"(revenue|18 ?%|growth|caus)", r"(correlat|caus|confound|other factors|coincid|post hoc)"]),
            ("survivorship", [r"(still with us|satisf|left|teams)", r"(survivor|left|attrition|selection|those who|quit|departed)"]),
            ("cherry-picked quarter", [r"(Q3|best quarter|25 ?%)", r"(cherry|best quarter|single quarter|one quarter|selective|pick|outlier)"]),
            ("costs nothing contradiction", [r"(costs? nothing|free|1[,.]?200|kit)", r"(contradict|not free|isn'?t free|1[,.]?200|inconsisten|not nothing)"])],
    herrings=[r"lease.{0,60}(bad|wrong|too (late|early))"],
))

# ================================================================= EXTRACT (JSON)
E_BOIL = " Write only the JSON to data.json (no comments, no prose)."
MAIL = """From: Priya Raman <priya.raman@kestrel-labs.example>
To: sales@lumen.example
Subject: Demo next week?

Hi,
I'm the operations lead at Kestrel Labs. Could we do a product demo on Thursday 14 March 2026 at 10:30?
Our team is 40 people.

Thanks,
Priya
"""
S1 = {"type": "object", "required": ["name", "email", "company", "meeting_date", "team_size"],
      "properties": {"name": {"type": "string"}, "email": {"type": "string"}, "company": {"type": "string"},
                     "meeting_date": {"type": "string"}, "team_size": {"type": "integer"}}}
add(Task(
    "extract-1", "extract", 1,
    "Extract the sender from email.txt as a JSON object with the keys name, email, company, meeting_date "
    "(YYYY-MM-DD) and team_size (an integer)." + E_BOIL,
    files={"email.txt": MAIL}, deliverable="data.json",
    checks=[schema(S1), field("name", lambda d: d["name"], "Priya Raman"),
            field("email", lambda d: d["email"], "priya.raman@kestrel-labs.example"),
            field("company", lambda d: d["company"], "Kestrel Labs"),
            field("meeting_date", lambda d: d["meeting_date"], "2026-03-14"),
            field("team_size", lambda d: d["team_size"], 40)],
))
INVOICE = """INVOICE 2026-0117                    Harbor Print Co.
Bill to: Lumen GmbH                  Date: 3 Feb 2026

  2 x Poster A2, matte ............. 18.50 each
500 x Business cards ................ 0.12 each
  1 x Design fee ................... 95.00
  3 x Roll-up banner ............... 64.00 each

Shipping: 12.00
"""
S2 = {"type": "object", "required": ["invoice_number", "date", "items", "shipping", "total"],
      "properties": {"invoice_number": {"type": "string"}, "date": {"type": "string"},
                     "items": {"type": "array", "items": {"type": "object", "required": ["description", "quantity", "unit_price"],
                               "properties": {"description": {"type": "string"}, "quantity": {"type": "integer"},
                                              "unit_price": {"type": "number"}}}},
                     "shipping": {"type": "number"}, "total": {"type": "number"}}}
add(Task(
    "extract-2", "extract", 2,
    "Extract invoice.txt as a JSON object: invoice_number (string), date (YYYY-MM-DD), items (a list of "
    "{description, quantity (integer), unit_price (number)} in invoice order), shipping (number) and total "
    "(number: the amount due, items plus shipping; the invoice does not print it)." + E_BOIL,
    files={"invoice.txt": INVOICE}, deliverable="data.json",
    checks=[schema(S2), field("invoice_number", lambda d: d["invoice_number"], "2026-0117"),
            field("date", lambda d: d["date"], "2026-02-03"),
            field("quantities", lambda d: [i["quantity"] for i in d["items"]], [2, 500, 1, 3]),
            field("unit prices", lambda d: [i["unit_price"] for i in d["items"]], [18.5, 0.12, 95, 64]),
            field("shipping", lambda d: d["shipping"], 12), field("total", lambda d: d["total"], 396)],
))
TICKETS = """#4411 | from: Jonas Weber | 2026-02-10
Lumen Desktop crashes on start since the update. I can't open any notes and I have a deadline today.
I want a refund for this month.

#4412 | from: m.costa@example.com (Marta Costa) | 2026-02-10
How do I export a notebook to PDF in Lumen Mobile?

#4413 | from: Li Wei | 2026-02-11
Sync between my phone and laptop stopped working, everything else works. It's been a week, please refund
this month.

#4414 | from: Sam O'Neill | 2026-02-11
Is there a student discount?

#4415 | from: Jonas Weber | 2026-02-12
Following up on #4411: still crashing, I still cannot use it at all. Lumen Desktop 2.0.3 on Windows.
"""
S3 = {"type": "array", "items": {"type": "object",
      "required": ["id", "customer", "priority", "product", "refund_requested"],
      "properties": {"id": {"type": "integer"}, "customer": {"type": "string"},
                     "priority": {"enum": ["low", "medium", "high"]}, "refund_requested": {"type": "boolean"}}}}
add(Task(
    "extract-3", "extract", 3,
    "Turn the support tickets in tickets.txt into a JSON array, one object per ticket in file order, with: id "
    "(integer, without #), customer (the person's name), priority, product, refund_requested (boolean). "
    "priority is \"high\" when the customer cannot use the product at all, \"medium\" when one feature is "
    "broken, \"low\" for a question. product is the product named in that ticket (e.g. \"Lumen Desktop\"), "
    "or null when the ticket names none." + E_BOIL,
    files={"tickets.txt": TICKETS}, deliverable="data.json",
    checks=[schema(S3), field("ids", lambda d: [x["id"] for x in d], [4411, 4412, 4413, 4414, 4415]),
            field("customers", lambda d: [x["customer"] for x in d],
                  ["Jonas Weber", "Marta Costa", "Li Wei", "Sam O'Neill", "Jonas Weber"]),
            field("priorities", lambda d: [x["priority"] for x in d], ["high", "low", "medium", "low", "high"]),
            ("products", lambda t: products_ok(t, ["Lumen Desktop", "Lumen Mobile", None, None, "Lumen Desktop"])),
            field("refunds", lambda d: [x["refund_requested"] for x in d], [True, False, True, False, False])],
))
