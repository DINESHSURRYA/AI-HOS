"""High-performance, explainable forward-chaining rule engine for Prior Authorization."""
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import structlog

from app.models.policy import (
    Decision,
    MedicalNecessityCriteria,
    PayerPolicy,
    PolicyRule,
    PriorAuthDecision,
    PriorAuthRequest,
    RuleEvaluationDetail,
)

logger = structlog.get_logger()

DEFAULT_POLICIES_PATH = (
    Path(__file__).resolve().parents[1] / "policies" / "default_policies.json"
)


class RuleEngine:
    """
    Python-native forward-chaining rule engine for prior authorization decisions.
    Uses transparent weighted rule scoring + clinical medical necessity evidence analysis.
    """

    def __init__(self) -> None:
        self.policies: Dict[str, PayerPolicy] = {}
        self.logger = structlog.get_logger()

    def load_policy(self, policy: PayerPolicy) -> None:
        """Load or update a policy in memory."""
        self.policies[policy.policy_id] = policy
        self.logger.info("policy_loaded", policy_id=policy.policy_id, payer=policy.payer_id)

    def remove_policy(self, policy_id: str) -> bool:
        """Remove a policy from memory."""
        return self.policies.pop(policy_id, None) is not None

    def load_default_policies(self) -> int:
        """Load built-in payer policy JSON catalog if present."""
        if not DEFAULT_POLICIES_PATH.exists():
            return 0
        raw_list = json.loads(DEFAULT_POLICIES_PATH.read_text(encoding="utf-8"))
        count = 0
        for item in raw_list:
            policy = PayerPolicy.model_validate(item)
            if policy.policy_id not in self.policies:
                self.load_policy(policy)
                count += 1
        return count

    def evaluate_request(self, request: PriorAuthRequest) -> PriorAuthDecision:
        """
        Evaluate a prior auth request against matching payer policies.
        Returns a transparent decision (auto_approve, auto_deny, or escalate).
        """
        matching_policies = self._find_matching_policies(request)

        if not matching_policies:
            return PriorAuthDecision(
                request_id=request.request_id,
                payer_id=request.payer_id,
                procedure_code=request.procedure_code,
                diagnosis_codes=request.diagnosis_codes,
                decision=Decision.ESCALATE,
                confidence_score=0.0,
                reasoning=(
                    f"No matching payer policy found for payer '{request.payer_id}', "
                    f"CPT '{request.procedure_code}', and ICD-10 {request.diagnosis_codes}. "
                    "Escalated for manual utilization management review."
                ),
                required_documents=[
                    "Clinical progress note",
                    "Letter of medical necessity",
                    "Relevant diagnostic/imaging reports",
                ],
                suggested_diagnosis_codes=self._suggest_diagnoses(request),
                estimated_decision_time_hours=4 if request.urgency == "emergent" else 48,
            )

        best_policy = matching_policies[0]
        (
            final_score,
            rule_score,
            med_nec_score,
            matched_rules,
            failed_rules,
            rule_results,
            reasoning,
        ) = self._evaluate_policy(request, best_policy)

        urgency_override = False
        if request.urgency == "emergent" and final_score >= 0.50:
            decision = Decision.AUTO_APPROVE
            urgency_override = True
            reasoning += " | Emergent clinical urgency fast-track applied."
        elif final_score >= best_policy.auto_approve_threshold:
            decision = Decision.AUTO_APPROVE
        elif final_score <= best_policy.auto_deny_threshold:
            decision = Decision.AUTO_DENY
        else:
            decision = Decision.ESCALATE

        return PriorAuthDecision(
            request_id=request.request_id,
            payer_id=request.payer_id,
            procedure_code=request.procedure_code,
            diagnosis_codes=request.diagnosis_codes,
            decision=decision,
            confidence_score=round(final_score, 3),
            rule_score=round(rule_score, 3),
            medical_necessity_score=round(med_nec_score, 3) if med_nec_score is not None else None,
            matched_policy_id=best_policy.policy_id,
            matched_policy_title=best_policy.policy_title or best_policy.policy_id,
            matched_rules=matched_rules,
            failed_rules=failed_rules,
            rule_results=rule_results,
            reasoning=reasoning,
            required_documents=(
                self._get_required_docs(best_policy) if decision != Decision.AUTO_APPROVE else []
            ),
            suggested_diagnosis_codes=(
                self._suggest_diagnoses(request) if decision != Decision.AUTO_APPROVE else []
            ),
            urgency_override=urgency_override,
            estimated_decision_time_hours=(
                0 if decision in {Decision.AUTO_APPROVE, Decision.AUTO_DENY} else (12 if request.urgency == "urgent" else 48)
            ),
        )

    def _find_matching_policies(self, request: PriorAuthRequest) -> List[PayerPolicy]:
        """Find policies matching payer, CPT code, and at least one ICD-10 diagnosis."""
        matches: List[PayerPolicy] = []
        req_payer = request.payer_id.strip().upper()
        req_proc = request.procedure_code.strip().upper()
        req_diags = {d.strip().upper() for d in request.diagnosis_codes}

        for policy in self.policies.values():
            payer_match = policy.payer_id.strip().upper() == req_payer
            proc_match = any(
                req_proc == p.strip().upper() or req_proc.startswith(p.strip().upper())
                for p in policy.procedure_codes
            )
            policy_diags = {d.strip().upper() for d in policy.diagnosis_codes}
            diag_match = any(
                d in policy_diags or any(d.startswith(pd) for pd in policy_diags)
                for d in req_diags
            )

            if payer_match and proc_match and diag_match:
                matches.append(policy)

        matches.sort(key=lambda p: len(p.procedure_codes) + len(p.diagnosis_codes))
        return matches

    def _evaluate_policy(
        self,
        request: PriorAuthRequest,
        policy: PayerPolicy,
    ) -> Tuple[float, float, Optional[float], List[str], List[str], List[RuleEvaluationDetail], str]:
        """Evaluate weighted rules + medical necessity evidence."""
        context = {
            "procedure_code": request.procedure_code,
            "diagnosis_codes": request.diagnosis_codes,
            "age": request.patient_age,
            "gender": request.patient_gender,
            "previous_procedures": request.previous_procedures,
            "current_medications": request.current_medications,
            "urgency": request.urgency,
        }

        weighted_sum = 0.0
        total_weight = 0.0
        matched_rules: List[str] = []
        failed_rules: List[str] = []
        rule_results: List[RuleEvaluationDetail] = []
        reasoning_parts: List[str] = []

        for rule in policy.rules:
            score = self._evaluate_rule(rule, context)
            weighted_sum += score * rule.weight
            total_weight += rule.weight
            label = f"{rule.field}:{rule.operator}:{rule.value}"
            passed = score >= 0.5

            rule_results.append(
                RuleEvaluationDetail(
                    rule=label,
                    passed=passed,
                    score=score,
                    weight=rule.weight,
                    description=rule.description,
                )
            )

            if passed:
                matched_rules.append(label)
                reasoning_parts.append(f"PASS {rule.description or label}")
            else:
                failed_rules.append(label)
                reasoning_parts.append(f"FAIL {rule.description or label}")

        rule_score = (weighted_sum / total_weight) if total_weight > 0 else 1.0

        med_nec_score: Optional[float] = None
        if policy.medical_necessity is not None:
            med_nec_score, evidence_hits = self._check_medical_necessity(
                request, policy.medical_necessity
            )
            # Combine rule eligibility (55%) and medical necessity evidence (45%)
            # while ensuring failed hard rules still penalize overall score cleanly.
            if rule_score < 0.5:
                confidence = rule_score * 0.7 + med_nec_score * 0.3
            else:
                confidence = rule_score * 0.55 + med_nec_score * 0.45

            if evidence_hits:
                reasoning_parts.append(
                    f"Medical necessity evidence detected ({', '.join(evidence_hits[:5])}): {med_nec_score:.0%}"
                )
            else:
                reasoning_parts.append(
                    f"Limited medical necessity evidence in notes ({med_nec_score:.0%})"
                )
        else:
            confidence = rule_score

        confidence = max(0.0, min(1.0, confidence))
        reasoning = f"Policy {policy.policy_id} ({policy.payer_name}): " + "; ".join(
            reasoning_parts
        )
        return (
            confidence,
            rule_score,
            med_nec_score,
            matched_rules,
            failed_rules,
            rule_results,
            reasoning,
        )

    def _evaluate_rule(self, rule: PolicyRule, context: Dict[str, Any]) -> float:
        """Evaluate a single rule against request context."""
        field_value = context.get(rule.field)
        if field_value is None:
            return 0.0

        try:
            if rule.operator == "eq":
                return 1.0 if str(field_value).strip().upper() == str(rule.value).strip().upper() else 0.0
            if rule.operator == "ne":
                return 1.0 if str(field_value).strip().upper() != str(rule.value).strip().upper() else 0.0
            if rule.operator == "in":
                if isinstance(rule.value, list):
                    normalized = [str(v).strip().upper() for v in rule.value]
                    return 1.0 if str(field_value).strip().upper() in normalized else 0.0
                return 1.0 if field_value in rule.value else 0.0
            if rule.operator == "contains":
                if isinstance(field_value, list):
                    normalized = [str(v).strip().upper() for v in field_value]
                    return 1.0 if str(rule.value).strip().upper() in normalized else 0.0
                return 1.0 if str(rule.value).lower() in str(field_value).lower() else 0.0
            if rule.operator == "gt":
                return 1.0 if float(field_value) > float(rule.value) else 0.0
            if rule.operator == "lt":
                return 1.0 if float(field_value) < float(rule.value) else 0.0
            if rule.operator == "gte":
                return 1.0 if float(field_value) >= float(rule.value) else 0.0
            if rule.operator == "lte":
                return 1.0 if float(field_value) <= float(rule.value) else 0.0
        except (ValueError, TypeError):
            return 0.0
        return 0.0

    def _check_medical_necessity(
        self,
        request: PriorAuthRequest,
        criteria: MedicalNecessityCriteria,
    ) -> Tuple[float, List[str]]:
        """Analyze clinical notes & history for medical necessity evidence."""
        notes = (request.clinical_notes or "").strip()
        if not notes:
            return 0.30, []

        notes_lower = notes.lower()
        score = 0.25
        hits: List[str] = []

        evidence_keywords = [
            ("failed", 0.22),
            ("conservative", 0.18),
            ("physical therapy", 0.16),
            ("therapy", 0.10),
            ("nsaid", 0.12),
            ("ibuprofen", 0.10),
            ("naproxen", 0.10),
            ("meloxicam", 0.10),
            ("medication", 0.08),
            ("tried", 0.08),
            ("x-ray", 0.12),
            ("radiograph", 0.12),
            ("ekg", 0.14),
            ("bnp", 0.14),
            ("dyspnea", 0.15),
            ("shortness of breath", 0.15),
            ("edema", 0.14),
            ("swelling", 0.10),
            ("pain", 0.10),
            ("severe", 0.12),
            ("chronic", 0.10),
            ("worsening", 0.12),
            ("persistent", 0.12),
            ("snoring", 0.18),
            ("apnea", 0.18),
            ("screening", 0.25),
            ("preventive", 0.20),
            ("bleeding", 0.18),
            ("radiculopathy", 0.18),
            ("numbness", 0.14),
        ]

        for keyword, weight in evidence_keywords:
            if keyword in notes_lower:
                score += weight
                hits.append(keyword)

        # Check explicit duration evidence (e.g. "6 weeks", "3 months", "6 months")
        duration_match = re.search(
            r"\b(\d+)\s*(weeks?|months?|years?)\b", notes_lower
        )
        if duration_match:
            amount = int(duration_match.group(1))
            unit = duration_match.group(2)
            weeks_equiv = amount * (52 if unit.startswith("year") else 4 if unit.startswith("month") else 1)
            if weeks_equiv >= 6:
                score += 0.18
                hits.append(f"duration:{duration_match.group(0)}")
            elif weeks_equiv >= 2:
                score += 0.08
                hits.append(f"duration:{duration_match.group(0)}")

        # Medications in structured request also add supporting evidence
        if request.current_medications:
            score += 0.08
            hits.append("active_medications")

        return min(1.0, round(score, 3)), hits

    def _suggest_diagnoses(self, request: PriorAuthRequest) -> List[str]:
        """Suggest commonly covered ICD-10 diagnosis codes for a CPT procedure."""
        mappings = {
            "73706": ["M17.11", "M17.12", "M25.561", "S83.209A"],
            "73721": ["M17.11", "M17.12", "M25.561", "S83.209A"],
            "72148": ["M54.16", "M54.50", "M51.26"],
            "93306": ["I50.9", "I48.91", "I25.10", "I10"],
            "71250": ["J44.1", "J44.9", "J18.9"],
            "71046": ["J44.1", "J18.9", "J45.909"],
            "45378": ["Z12.11", "K21.9", "D64.9"],
            "27447": ["M17.11", "M17.12"],
            "95810": ["G47.33"],
            "80053": ["E11.9", "I10"],
        }
        return mappings.get(request.procedure_code.strip(), [])

    def _get_required_docs(self, policy: PayerPolicy) -> List[str]:
        docs = ["Signed clinical progress note", "Relevant diagnostic/imaging reports"]
        if policy.medical_necessity:
            for item in policy.medical_necessity.required_evidence:
                if item not in docs:
                    docs.append(item)
        return docs


_engine: Optional[RuleEngine] = None


def get_rule_engine() -> RuleEngine:
    """Get or create RuleEngine singleton with default policies loaded."""
    global _engine
    if _engine is None:
        _engine = RuleEngine()
        _engine.load_default_policies()
    return _engine


def reset_rule_engine(load_defaults: bool = True) -> RuleEngine:
    """Reset RuleEngine singleton (used in tests)."""
    global _engine
    _engine = RuleEngine()
    if load_defaults:
        _engine.load_default_policies()
    return _engine
