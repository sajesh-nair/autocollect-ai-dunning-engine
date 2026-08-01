uv pip install joblib
uv pip install scikit-learn

uv run uvicorn main:app --reload


Linkedin Post
Last week we caught 761 risky invoices with 93% accuracy using our ML model.

The main problem after that is actually doing the follow-ups. You either spend hours manually writing emails to hundreds of people, or you send generic automated emails that everyone ignores.

So for Week 11, I built AutoCollect AI to fix this.

You just drop in the spreadsheet, and it pulls out those 761 flagged accounts with their risk scores. It drafts a short, natural email for each one so an operator can review it, tweak it if needed, and hit send in one click.

Since the original dataset doesn't have real customer emails, I connected it to a test inbox so you can see the live delivery in action.

Tech Stack: Python, Scikit-learn, FastAPI, Tailwind CSS, SMTP.

Check out the full workflow execution video below!