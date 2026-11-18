# Software Delivery Scenario

**Status:** Implemented for local development and tests: synthetic issues and pull requests, behind the forge's MCP server, an engineering handbook in a Markdown vault, a dedicated dev assistant, need-to-know for security issues, and asking someone to review a pull request, held for its repository's owners.

An engineering team works in an issue tracker and code review. Engineers fix bugs by their due dates and review each other's pull requests; leads own their parts of the code; product reports what customers need. It tests a5s where the people it serves are technical and its records change many times a day, and where the riskiest asks, such as merging or handling a secret, must never be the agent's.

## The contract

| Interface | In software delivery |
| --- | --- |
| Directory | The identity provider: engineers, their leads, security and product, by team; and the team that runs a5s, who own its agent, with the people from outside it who approve its releases |
| Settings | a5s's own settings store. The parts are parts of the code, such as backend and frontend, each owned by its tech lead |
| Tools | The issue tracker's issues and the code review's pull requests, with their checks and reviewers, and customers' comments through a5s's reader, through the forge's MCP server, which the scenario's [`mcp.yaml`](software-delivery/mcp.yaml) declares, with asking someone to review a pull request; and the engineering handbook, read only, and drafts |
| Records | Issues, with their due dates, and pull requests, with the date each review is due |
| Governed process | The code review's branch protection and required reviews, and the issue tracker's workflow: a5s merges and approves nothing |
| Decision surface | The code review and the issue tracker themselves |
| Tests | [`tests/test_software_delivery.py`](../tests/test_software_delivery.py), against a fake issue tracker and code review, and live on a real model; and on a5s's containers, through Matrix, with its release approved by its own people ([`deploy/smoke-scenario.sh`](../deploy/smoke-scenario.sh)) |

The evaluation also covers release readiness across records and policy, approved reviews with failing checks, reopened fixes, ambiguous and unknown issues, changing records between task slices, cancellation, and multi-turn scope changes. Critical live questions run twice, with semantic assertions beside scorecards of latency, model calls, tokens, permission denials and forbidden tools ([`tests/scorecards.py`](../tests/scorecards.py)). The approved model list has no prices, so token use is measured but monetary cost is not claimed.

## Who sees what

- An issue or pull request is its team's to see, and its assignee's, author's, reporter's and reviewers'.
- An issue labelled security is the security team's and its assignee's alone, until it's fixed: a5s leaves it out of searches for anyone else, and refuses it by name.
- What customers write on an issue reaches the agent only as a5s's reader fills a fixed form from it: what it asks for, and the dates and keys it names.

## The agent

| Agent | Works for | Starts at | Does |
| --- | --- | --- | --- |
| Dev assistant (`dev-assistant`) | Engineers, their leads and product | Asks first | Answers about issues, pull requests, checks and reviews, and how the team works, from the handbook; saves drafts such as pull request descriptions and release notes for people to post; asks for a review when someone wants one, which the repository's owners decide; takes on confirmed, resumable review tasks; and chases the fixes and reviews people owe, by when they're due. Built again in the studio, from nothing, as dev-helper ([its guide](../docs/guides/software-delivery/guide.md)) |

It never merges, approves a review, changes an issue, runs code or handles a secret: the code review's own controls decide those, and people make them.

## Through MCP

The forge's tools, with its CI's checks, come through the forge's MCP server, as an organisation's would ([phase 5](../docs/phase-5.md)): searching issues and pull requests, reading one, what customers wrote on an issue, and asking someone to review an open pull request, declared in [`mcp.yaml`](software-delivery/mcp.yaml) in a5s's own words, and nothing else of the server's. In this made-up team the server is [`deploy/systems/forge.py`](../deploy/systems/forge.py), on the scenario's synthetic data, beside the gateway on its own machine: the tests start it once, and the scenario's containers run it in the gateway's network ([`deploy/compose.delivery.yaml`](../deploy/compose.delivery.yaml)). What stays the team's own code is its directory, who may see each issue and pull request, the reviews and fixes people owe, a draft for a person to post, and its handbook.

Asking someone to review a pull request is a change of type `assign-reviewer`: where the agent asks first, a5s holds it for the owners of the pull request's repository, its part, never anyone it's for, and asks the forge once they approve it, once for a5s's key, which the made-up forge honours. The forge keeps whom it was asked to review each pull request in the folder `A5S_SYSTEMS_STATE` names, which the scenario's code lays over its data, as master data does SAP's: so the reviewer a5s asked may read the pull request, and is chased for the review, and the forge carries on from there when it starts again. Someone who may not see a pull request can't ask for its review ([`tests/test_delivery_reviews.py`](../tests/test_delivery_reviews.py)).
