# Manual test checklist (run against the test bot before each deploy)

Mark each line pass/fail. Dates assume you run it on the day; adjust the expected date labels.

## Setup and settings
1. `/start` → welcome, privacy notice, "Your currency is GBP", buttons GBP/EUR/USD/SGD, hint about `/currency CODE`.
2. Tap **EUR** → "Currency set to EUR." Then tap **GBP** to restore.
3. `/currency chf` → "Currency set to CHF." `/currency xx` → "Use a 3-letter code like GBP or CHF." Restore with `/currency gbp`.
4. The command menu (the `/` button) lists report, recent, undo, upcoming, recurring, notify, export, currency, deleteaccount, help.
5. `/help` → help text with examples and commands.

## Logging
6. `15 lunch` → "Logged £15.00 · Eating Out · Lunch · today" with [Undo] [Change category].
7. `lunch 4.50` → same pattern, £4.50.
8. `20 groceries yesterday` → "· yesterday".
9. `150 flights 31/12/26` → "Planned £150.00 · Travel · flights · 31 Dec 2026".
10. `12 xyzzy` → "Logged £12.00 · Other · xyzzy · today" plus "Pick a category:" and 12 buttons. Tap **Gifts** → message becomes "· Gifts ·". Then `3 xyzzy` → logs straight to Gifts (word learned).
11. On any logged entry, tap [Change category] → buttons; pick one → message updates.
12. `15,50 lunch` → the "Not quite!" cheat sheet (Review Focus 1: never £1,550)
13. `0 lunch` → "Amount must be more than 0 and at most 1,000,000."
14. `10 x 31/02` → "That date doesn't exist."
15. `hello` → example reply.

## Undo, recent, edit
16. `5 test` then tap its [Undo] → "Deleted £5.00 · Other · test · today".
17. `6 stale`, then `/recent` and tap [Delete] on "stale". Scroll up to the original "Logged £6.00 ... stale" message and tap its [Undo] → "That entry no longer exists." (Review Focus 5)
17b. Edit a message you already sent (long-press, Edit, change `6 stale` to `7 stale`) → "Edits to sent messages aren't tracked. Use /recent to change an entry."
18. `/undo` → shows latest entry with [Delete] [Keep]. Tap **Keep** → "Kept." `/undo` again, tap **Delete** → "Deleted ...".
19. `/recent` → up to 5 messages with [Edit] [Delete]. `/recent 12` → up to 12. `/recent 50` → "Use /recent, or /recent 10 for more (up to 20)."
20. Tap [Edit] on one → prompt. Send `hello` → example reply (still editing). Send `16 lunch` → "Updated £16.00 · Eating Out · lunch · today".
21. Tap [Edit] again, then `/cancel` → "Edit cancelled."

## Planning and recurring
22. `/upcoming` → "Planned payments: £150.00 in total" then the flights line with [Delete].
23. `/recurring 12 netflix monthly` → "Recurring £12.00 · Subscriptions · netflix · monthly from today".
24. `/recurring 12 netflix` → "Try /recurring 12 netflix monthly or /recurring 950 rent monthly 01/11."
25. `/recurring` twice (two copies of the list). Tap **Stop** on netflix in the first → "Stopped: £12.00 netflix monthly". Tap **Stop** on netflix in the second copy → "That entry no longer exists."
25b. `/recurring 5 coffee weekly 01/10/2006` → "Use a date from last year up to 10 years ahead."

## Reports
26. `/report` → chart image (pace + categories) then text: Spent, No-spend days, the "Comparisons start once you have a full month of data." note, By category, Where to save, Patterns, Coming up.
27. `/report week`, `/report lastmonth`, `/report year` → chart + text each, no errors.
28. `/report blah` → "Use /report, /report week, /report lastmonth or /report year."
29. `/notify off` → "Weekly and monthly summaries off." `/notify on` → "... on." `/notify` → current state.

## Data
30. `/export` → the encryption warning with [Send CSV] [Cancel]. **Send CSV** → `expenses.csv` arrives; it opens in Excel with £ intact and one row per entry.
31. `/export` then **Cancel** → "Export cancelled."

## Jobs (Task 12 step 4)
32. A planned entry dated today → "Due today: £X note" arrives once the hourly job runs after 09:00.
33. `/recurring 3 test weekly` (start today) → within the hourly run, "Recurring: £3.00 · Other · test · today" with [Undo] arrives.

## Robustness
34. Send 35 messages quickly (paste `1 x` repeatedly) → one "You're sending messages too fast..." then silence until a minute passes.
35. From a second Telegram account that never ran /start, send `15 lunch` → logged normally in GBP. (Review Focus 4)

## Last
36. `/deleteaccount` → warning with [Delete everything] [Cancel]. **Cancel** → "Cancelled. Nothing was deleted." Run again, **Delete everything** → "All your data has been deleted." Then `/recent` → "No entries yet."
