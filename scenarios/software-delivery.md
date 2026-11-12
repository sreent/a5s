# Software Delivery Scenario

**Status:** A read-only MVP is implemented for local development and tests: synthetic issues and pull requests, an engineering handbook in a Markdown vault, a dedicated dev assistant, and need-to-know for security issues. Held changes, such as assigning a reviewer, remain future work.

An engineering team works in an issue tracker and code review. Engineers fix bugs by their due dates and review each other's pull requests; leads own their parts of the code; product reports what customers need. It tests a5s where the people it serves are technical and its records change many times a day, and where the riskiest asks, such as merging or handling a secret, must never be the agent's.

## The contract

| Interface | In software delivery |
| --- | --- |
| Directory | The identity provider: engineers, their leads, security and product, by team; and the team that runs a5s, who own its agent, with the people from outside it who approve its releases |
| Settings | a5s's own settings store. The parts are parts of the code, such as backend and frontend, each owned by its tech lead |
| Tools | The issue tracker's issues and the code review's pull requests, with their checks and reviewers, customers' comments through a5s's reader, and the engineering handbook, read only, and drafts |
| Records | Issues, with their due dates, and pull requests, with the date each review is due |
| Governed process | The code review's branch protection and required reviews, and the issue tracker's workflow: a5s merges and approves nothing |
| Decision surface | The code review and the issue tracker themselves |
| Tests | [`tests/test_software_delivery.py`](../tests/test_software_delivery.py), against a fake issue tracker and code review, and live on a real model; and on a5s's containers, through Matrix, with its release approved by its own people ([`deploy/smoke-scenario.sh`](../deploy/smoke-scenario.sh)) |

## Who sees what

- An issue or pull request is its team's to see, and its assignee's, author's, reporter's and reviewers'.
- An issue labelled security is the security team's and its assignee's alone, until it's fixed: a5s leaves it out of searches for anyone else, and refuses it by name.
- What customers write on an issue reaches the agent only as a5s's reader fills a fixed form from it: what it asks for, and the dates and keys it names.

## The agent

| Agent | Works for | Starts at | Does |
| --- | --- | --- | --- |
| Dev assistant (`dev-assistant`) | Engineers, their leads and product | Level 1 | Answers about issues, pull requests, checks and reviews, and how the team works, from the handbook; saves drafts such as pull request descriptions and release notes for people to post; and chases the fixes and reviews people owe, by when they're due |

It never merges, approves a review, changes an issue, runs code or handles a secret: the code review's own controls decide those, and people make them.
