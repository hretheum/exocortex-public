---
type: runbook_l
lang: en
counterpart: ../../pl/templates/runbook-l.md
hypothesis: "<slug>"
variant: L-a            # L-a own infrastructure | L-b cloud in the EU | L-c hybrid by data class
source_results: []      # ids of the pilot results the numbers were computed from
human_validated: false
---

# Deployment in a large organisation: <solution name>

This document describes how to carry out a deployment. It is not a record of one. Every number has a formula and a link to a pilot result.

## 1. Goal, scope and what the document does not cover

## 2. Scale parameters

| Parameter | Measured in the pilot | Target volume | Result at scale | Formula |
|---|---|---|---|---|
| cost per unit | | | annual budget | |
| share of cases needing manual review | | | cases per month, staff | |
| latency (95th percentile) | | | hardware requirements | |
| index and graph size | | | memory, disk | |

## 3. Architecture

Description of the chosen variant and a comparison with the other two: cost, control over data, time to deploy, vendor dependence.

## 4. Data and compliance

Data classification, legal basis for processing, data protection impact assessment, retention periods, risk class under the AI Act with reasons.

## 5. Security

Prompt injection, data exfiltration through tools, access to knowledge scopes by role, logs and audit.

## 6. Model upkeep

Model and prompt registry, quality tests in CI on a regression set from the pilot, monitoring of quality and drift, procedure for changing models, human involvement.

## 7. Organisation

Division of responsibility, roles, training, business owner, support.

## 8. Staged rollout

Waves with a control group, indicators with balancing pairs, guard metrics, criteria for moving between waves.

## 9. Business case

A comparison of options, including one where nothing changes, costs over several years, a cautious scenario with lower benefits and higher costs, and the payback period.

## 10. Risks, stopping condition, rollback plan
