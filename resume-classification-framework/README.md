# Resume Classification Decision Framework

## Overview

This module contains a structured decision framework used to classify resumes into functional departments based on experience, skill patterns, and role consistency.

This framework was developed as an improvement over an earlier benchmarking-based approach, shifting toward a **manual, rule-based classification system** to increase accuracy and interpretability.

---

## Structure

* `decision_table.csv` → Core classification logic including:

  * 1st Match (Primary Department)
  * 2nd Match (Secondary Department)
  * Skill patterns
  * Supporting rationale

---

## Methodology

The classification follows a **dual-match system**:

* **1st Match (Primary Function)**
  Determined by the dominant and repeated experience across roles.

* **2nd Match (Secondary Function)**
  Determined by supporting skills, tools, or partial exposure.

---

## Key Rules

* Experience > Major
* Repetition > One-off roles
* Function > Industry
* Specialized domains override general ones (e.g., Healthcare > Management)

---

## Example Logic

| Scenario                                | Classification                         |
| --------------------------------------- | -------------------------------------- |
| Generalist with coordination + outreach | Management + Marketing                 |
| Quantitative finance + analytics tools  | Finance + ISOM                         |
| Healthcare operations background        | Healthcare Administration + Management |

---

## Notes

* This framework excludes raw resume data to ensure privacy and compliance.
* Designed to simulate structured decision-making similar to consulting-style candidate evaluation.

---
