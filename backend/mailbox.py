"""Inspect locally recorded mail; never exposed over HTTP."""

import argparse
from main import db

parser = argparse.ArgumentParser(description="Show recent development emails")
parser.add_argument("--latest", action="store_true")
args = parser.parse_args()
with db() as conn:
    rows = conn.execute("SELECT recipients,subject,body FROM outbox ORDER BY created DESC LIMIT ?",
                        (1 if args.latest else 10,)).fetchall()
for row in rows:
    print(f"To: {row['recipients']}\nSubject: {row['subject']}\n\n{row['body']}\n")
