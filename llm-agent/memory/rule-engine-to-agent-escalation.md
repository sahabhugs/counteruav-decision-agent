---
name: rule-engine-to-agent-escalation
description: Rule-engine→LLM Agent escalation flow for low-confidence threat assessment
metadata:
  type: project
---

## Architecture

The counter-UAV decision system has a two-tier architecture:
1. **Java Rule Engine** (rule-engine/): Performs IFN-TOPSIS threat assessment + Drools rule matching. When confidence < 0.80 threshold, escalates to LLM Agent.
2. **Python LLM Agent** (llm-agent/): Provides deep ReAct-based reasoning for low-confidence scenarios.

## Escalation Flow

1. Rule engine `ThreatEvaluator` calculates threat scores via IFN-TOPSIS
2. `ConfidenceGate.calculateConfidence()` computes 5-dimension weighted confidence (rule consistency 0.30, sensor quality 0.25, classification 0.20, coverage 0.15, historical 0.10)
3. If confidence < 0.80 (or special triggers: EVT open-set, complex threat, unknown drone), `LLMClientService.sendToLLMAgent()` POSTs to `/api/llm/decide`
4. Python agent runs ReAct loop, returns decision with confidence
5. Java side uses `Math.max(ruleConfidence, agentConfidence)` for final confidence

## Key Modules (Python side)

- `llm-agent/src/rule_engine.py`: [[rule-engine-integration-module]] — Python implementation of the confidence gate + escalation logic, mirrors Java ConfidenceGate/LLMClientService
- `llm-agent/src/main.py`: [[main-py-escalation-handling]] — Enhanced /api/llm/decide to inject escalation context into system prompt and track confidence improvement
- `llm-agent/src/react_engine.py`: [[react-engine-escalation-context]] — Updated _build_system_prompt to include escalation context section when called due to low confidence
- `llm-agent/tests/test_rule_engine.py`: 45 tests covering confidence calculation, escalation triggers, request/response compatibility, integration flows, and edge cases

## Configuration

- `CONFIDENCE_THRESHOLD` (config.py): 0.80 — triggers LLM escalation
- `RULE_ENGINE_URL` (config.py): http://localhost:8080 — Java rule engine endpoint
- Python agent listens on port 8001 (`/api/llm/decide`)
- Java LLMClientService calls `http://localhost:8001/api/llm/decide`

**Why:** The confidence gate ensures the system doesn't make irreversible decisions with insufficient evidence. When the rule engine's assessment is uncertain, the LLM agent provides deeper analysis.

**How to apply:** When modifying the escalation flow, ensure both Java and Python sides agree on the request/response contract. The Java payload must include `task_id`, `trigger_reason`, `situation` (with `targets`, `devices`, `environment`), `task_description`, and `threat_level`. The Python response must include `decision.threat_assessment.confidence` for the Java side to extract. Tests in test_rule_engine.py validate this compatibility.
