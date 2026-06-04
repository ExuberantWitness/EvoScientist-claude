# Distillation Strategy

Controls how IDE/IVE/ESE extract insights from interactions.

## IDE (Idea Direction Evolution)
ide_promising_method: median
ide_fail_threshold_ratio: 0.5
ide_bottom_third_ratio: 0.33

## IVE (Idea Validation Evolution)
ive_priority_level: HIGH
ive_auto_trigger_on_score_below: 0.3

## ESE (Experiment Strategy Evolution)
ese_success_threshold: 0.6
ese_applicability_tagging: auto

## Merge & Dedup
dedup_overlap_threshold: 0.8
merge_keep_higher_score: true

## General
baseline_score: 0.3
