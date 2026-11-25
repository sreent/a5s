# Grading agents' work

For graders. Your grades are the evidence a5s goes on when it lets an agent act on its own, and when it takes that away again.

## What you grade

A sample is a change an agent asked for or made, kept for graders:

- each change people decided, approved or rejected, while the agent still asks first for that type of change;
- some of the changes it made on its own, about a hundred a quarter.

One sample in five is drawn twice, for a second grader. You're never offered a sample of your own team's agent, a change you asked for or decided, a change made for your own team or for someone you report to, the decisions of someone you report to, or one that names a record you may not see.

## Grade a sample

The Grading page, `/studio/grade`, lists *Agents' work to grade*. Each card says:

- which agent asked, or acted on its own, for which type of change, in which part, and when it was sampled;
- *What they asked*: the person's own words to the agent, with names masked until the data protection officer agrees to show them, and nothing for a run nobody asked for;
- whether the change was approved, rejected or made on its own;
- *What code flagged*, as its deciders read it, with a link to open its record.

![Samples to grade: who asked, what code flagged, and the grade](../guides/master-data/19-over-the-quarter-each-correction-mo-decided-is-d.png)

1. For each sample, choose **Right** if it's what a careful colleague would have done with what they knew, **Wrong** if not, or **Critical** if it could have done real harm. Choose a grade again to take it back.
2. Choose **Send the grades you chose**, and sign in again, with your second factor where your organisation asks for one. Your sign-in covers exactly the grades you send, up to 20 at a time.

You don't see the judge's verdict, who decided the change, or another grader's grade of the same sample, so each grade is your own.

## What your grades do

a5s keeps a cap for each agent, on each model, for each type of change, in each part. It starts at asking first, and an instance does only what both the cap and its settings allow.

- **Raising it.** Only once the grades show, with 95% confidence, that the agent is as accurate as its part asks: for a part that asks for 95%, that's 88 samples graded right with none wrong.
- **Lowering it.** At once on a critical grade, and when the grades fall short of what the part asks.
- **No one grader decides it.** No grader's grades count for more than everyone else's together, so one grader alone never raises a cap. Nobody raises it by hand.
- **Undoing counts.** A change someone undoes counts as a wrong grade of the agent's work.
- **The settings decide too.** Even with its cap raised, an agent acts on its own only where its part's settings let it.

## When a sample lapses

A sample nobody grades within 91 days lapses, and is no longer offered. If you had chosen a grade for one that lapsed, or that someone else graded first, the page says so and leaves it out of what you send.

## The judge

An agent's owners may give it a judge: an approved model that grades the same samples, with a reason, beside people. It never moves a cap, and you never see its verdict. Its owners see how often it agrees with you.

## Compare a new version's answers

When the data protection officer lets new versions answer beside the instances they'd replace, the Shadows page, `/studio/shadows`, shows *New versions, answering beside*. Each pair has what the person said, the answer they were sent, and the new version's answer, which went nowhere.

Choose **Better**, **As good**, **Worse** or **Wrong** for the new version's answer. One click grades it, with no sign-in. These grades move no cap: they tell the agent's owners whether to put the new version to work.

## If your grades didn't count

If a5s's own check refuses grades after you've sent them, your digest says why, and the samples wait to be graded again on the Grading page.

For how a5s works this out, see [autonomy](../agent-model.md#autonomy) and [the judge](../agent-model.md#the-judge).
