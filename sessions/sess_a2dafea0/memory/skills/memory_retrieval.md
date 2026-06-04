# Memory Retrieval Strategy

Controls how inject_priors() allocates budget and prioritizes memory types.

## Budget Allocation (percentages, must sum to ~100)
failed_pct: 40
success_pct: 40
promising_pct: 20

## Entry Limits
failed_read_limit: 30
success_read_limit: 20
promising_read_limit: 10

## Relevance Scoring
applicability_boost: 0.2
min_budget_threshold: 80

## Per-Role Priority (comma-separated order)
role_planner: PROMISING,FAILED,SUCCESS
role_researcher: SUCCESS,FAILED,PROMISING
role_code: SUCCESS,FAILED
role_debug: FAILED,SUCCESS
role_analyst: SUCCESS,PROMISING
role_writer: PROMISING,SUCCESS

## General
inject_priors_max_chars: 2000
