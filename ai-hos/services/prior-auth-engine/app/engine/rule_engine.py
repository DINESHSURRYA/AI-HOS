"""High-performance rule engine for prior authorization."""
from typing import List, Dict, Any, Tuple
from app.models.policy import (
    PayerPolicy, PolicyRule, PriorAuthRequest, 
    PriorAuthDecision, Decision
)
import numpy as np
from datetime import datetime
import re
import structlog

logger = structlog.get_logger()


class RuleEngine:
    """
    Forward-chaining rule engine for prior auth decisions.
    Replaces Drools with Python-native implementation for easier deployment.
    """
    
    def __init__(self):
        self.policies: Dict[str, PayerPolicy] = {}
        self.logger = structlog.get_logger()
    
    def load_policy(self, policy: PayerPolicy):
        """Load a policy into the engine."""
        self.policies[policy.policy_id] = policy
        self.logger.info("policy_loaded", policy_id=policy.policy_id)
    
    def evaluate_request(
        self, 
        request: PriorAuthRequest
    ) -> PriorAuthDecision:
        """
        Evaluate a prior auth request against all matching policies.
        
        Returns decision with confidence score and explanation.
        """
        # Find matching policies
        matching_policies = self._find_matching_policies(request)
        
        if not matching_policies:
            # No policy found - escalate with suggestions
            return PriorAuthDecision(
                request_id=request.request_id,
                decision=Decision.ESCALATE,
                confidence_score=0.0,
                reasoning="No matching policy found for procedure/diagnosis combination",
                suggested_diagnosis_codes=self._suggest_diagnoses(request)
            )
        
        # Evaluate against best matching policy
        best_policy = matching_policies[0]
        score, matched_rules, reasoning = self._evaluate_policy(
            request, best_policy
        )
        
        # Determine decision based on thresholds
        if score >= best_policy.auto_approve_threshold:
            decision = Decision.AUTO_APPROVE
        elif score <= best_policy.auto_deny_threshold:
            decision = Decision.AUTO_DENY
        else:
            decision = Decision.ESCALATE
        
        return PriorAuthDecision(
            request_id=request.request_id,
            decision=decision,
            confidence_score=round(score, 3),
            matched_policy_id=best_policy.policy_id,
            matched_rules=matched_rules,
            reasoning=reasoning,
            required_documents=self._get_required_docs(request, best_policy),
            estimated_decision_time_hours=48 if decision == Decision.ESCALATE else 0
        )
    
    def _find_matching_policies(
        self, 
        request: PriorAuthRequest
    ) -> List[PayerPolicy]:
        """Find policies matching procedure and diagnosis."""
        matches = []
        
        for policy in self.policies.values():
            # Check procedure code match
            proc_match = (
                request.procedure_code in policy.procedure_codes or
                any(request.procedure_code.startswith(p) for p in policy.procedure_codes)
            )
            
            # Check diagnosis match (any code matches)
            diag_match = any(
                d in policy.diagnosis_codes for d in request.diagnosis_codes
            )
            
            # Check payer match
            payer_match = request.payer_id == policy.payer_id
            
            if proc_match and diag_match and payer_match:
                matches.append(policy)
        
        # Sort by specificity (most specific first)
        matches.sort(key=lambda p: len(p.procedure_codes) + len(p.diagnosis_codes))
        return matches
    
    def _evaluate_policy(
        self, 
        request: PriorAuthRequest, 
        policy: PayerPolicy
    ) -> Tuple[float, List[str], str]:
        """
        Evaluate request against policy rules.
        
        Returns: (confidence_score, matched_rules, reasoning)
        """
        rule_scores = []
        matched_rules = []
        reasoning_parts = []
        
        context = {
            "procedure_code": request.procedure_code,
            "diagnosis_codes": request.diagnosis_codes,
            "age": request.patient_age,
            "gender": request.patient_gender,
            "previous_procedures": request.previous_procedures,
            "current_medications": request.current_medications,
        }
        
        for rule in policy.rules:
            score = self._evaluate_rule(rule, context)
            weighted_score = score * rule.weight
            rule_scores.append(weighted_score)
            
            if score > 0.5:
                matched_rules.append(f"{rule.field}:{rule.operator}:{rule.value}")
                reasoning_parts.append(
                    f"{rule.field} {rule.operator} {rule.value}: {score:.2f}"
                )
        
        # Calculate harmonic mean of rule scores (punishes missing rules)
        if rule_scores:
            confidence = len(rule_scores) / sum(1/s if s > 0 else 1 for s in rule_scores)
            confidence = min(1.0, confidence / len(rule_scores))
        else:
            confidence = 0.0
        
        # Medical necessity check
        if policy.medical_necessity:
            med_nec_score = self._check_medical_necessity(
                request, policy.medical_necessity
            )
            confidence *= med_nec_score
        
        reasoning = f"Policy {policy.policy_id}: " + "; ".join(reasoning_parts)
        
        return confidence, matched_rules, reasoning
    
    def _evaluate_rule(
        self, 
        rule: PolicyRule, 
        context: Dict[str, Any]
    ) -> float:
        """Evaluate a single rule against context."""
        field_value = context.get(rule.field)
        
        if field_value is None:
            return 0.0
        
        try:
            if rule.operator == "eq":
                return 1.0 if str(field_value) == str(rule.value) else 0.0
            elif rule.operator == "ne":
                return 1.0 if str(field_value) != str(rule.value) else 0.0
            elif rule.operator == "in":
                return 1.0 if field_value in rule.value else 0.0
            elif rule.operator == "contains":
                return 1.0 if rule.value in field_value else 0.0
            elif rule.operator == "gt":
                return 1.0 if float(field_value) > float(rule.value) else 0.0
            elif rule.operator == "lt":
                return 1.0 if float(field_value) < float(rule.value) else 0.0
            elif rule.operator == "gte":
                return 1.0 if float(field_value) >= float(rule.value) else 0.0
            elif rule.operator == "lte":
                return 1.0 if float(field_value) <= float(rule.value) else 0.0
        except (ValueError, TypeError):
            return 0.0
        
        return 0.0
    
    def _check_medical_necessity(
        self, 
        request: PriorAuthRequest,
        criteria: Any
    ) -> float:
        """Check medical necessity from clinical notes."""
        if not request.clinical_notes:
            return 0.5  # Neutral if no notes
        
        notes_lower = request.clinical_notes.lower()
        score = 0.5
        
        # Check for evidence keywords
        evidence_keywords = {
            "failed": 0.2,
            "conservative": 0.2,
            "therapy": 0.1,
            "medication": 0.1,
            "tried": 0.1,
            "weeks": 0.1,
            "months": 0.1,
            "pain": 0.1,
            "severe": 0.1,
        }
        
        for keyword, weight in evidence_keywords.items():
            if keyword in notes_lower:
                score += weight
        
        return min(1.0, score)
    
    def _suggest_diagnoses(self, request: PriorAuthRequest) -> List[str]:
        """Suggest alternative diagnosis codes."""
        # Simplified - in production use mapping tables
        suggestions = []
        proc = request.procedure_code
        
        # Common mappings
        mappings = {
            "73706": ["M17.11", "M17.12", "M25.561"],  # MRI knee -> OA
            "71020": ["J44.1", "J18.9"],  # Chest X-ray -> COPD, Pneumonia
            "80053": ["E11.9", "I10"],  # CMP -> Diabetes, HTN
        }
        
        if proc in mappings:
            suggestions = mappings[proc]
        
        return suggestions
    
    def _get_required_docs(
        self, 
        request: PriorAuthRequest, 
        policy: PayerPolicy
    ) -> List[str]:
        """Determine required documentation for escalation."""
        docs = ["Clinical notes", "Imaging reports"]
        
        if policy.medical_necessity:
            docs.extend(policy.medical_necessity.required_evidence)
        
        return docs


# Singleton
_engine = None

def get_rule_engine() -> RuleEngine:
    """Get rule engine singleton."""
    global _engine
    if _engine is None:
        _engine = RuleEngine()
    return _engine
