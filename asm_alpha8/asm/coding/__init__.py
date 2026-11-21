"""ASM coding intelligence: repository understanding through verified workflows."""
from .analyzer import CodebaseAnalyzer, RepositoryReport, FileReport, Diagnostic
from .planner import CodingTaskPlanner, CodingPlan
from .patches import PatchProposal, PatchError, PatchProposalBuilder, apply_proposal
from .testing import TestRunner, TestRun
from .procedures import ProcedureStore
from .agent import CodingAgent, CodingSession
from .diagnostics import FailureAnalyzer, FailureEvidence
from .repair import RepairCoordinator, CandidateResult
from .research import (CodingResearchLoop, Candidate, ResearchContext, ResearchResult,
                       Attempt, FailureLedger, tree_fingerprint)
from .sandbox import SafeTestRunner, SafeRun, scan_risk, new_risks, normalized_sha256
from .research import compare_attempts, compare_outcomes
from .faultloc import (FaultLocalizer, RepairWorkflow, Dossier, LocalizationReport, collect_spectrum,
                       enumerate_sites, generate_candidates)
from .counterexamples import analyze_candidates, perturb_inputs, perturb_values
from .verification import verify_patch, verification_target, build_inputs
from .semantics import SemanticAnalyzer, SemanticReport, Finding, FunctionSemantics, analyze_static, match_refs
from .understanding import (CodeUnderstanding, UnderstandingReport, FunctionInfo, ClassInfo,
                            ModuleInfo, CallEdge, analyze_function)

__all__ = [
    "CodebaseAnalyzer", "RepositoryReport", "FileReport", "Diagnostic",
    "CodingTaskPlanner", "CodingPlan", "PatchProposal", "PatchError", "PatchProposalBuilder",
    "apply_proposal", "TestRunner", "TestRun", "ProcedureStore",
    "CodingAgent", "CodingSession", "FailureAnalyzer", "FailureEvidence",
    "RepairCoordinator", "CandidateResult",
    "CodingResearchLoop", "Candidate", "ResearchContext", "ResearchResult",
    "Attempt", "FailureLedger", "tree_fingerprint",
    "CodeUnderstanding", "UnderstandingReport", "FunctionInfo", "ClassInfo", "ModuleInfo",
    "CallEdge", "analyze_function",
    "SafeTestRunner", "SafeRun", "scan_risk", "new_risks", "normalized_sha256",
    "compare_attempts", "compare_outcomes",
    "analyze_candidates", "perturb_inputs", "perturb_values",
    "verify_patch", "verification_target", "build_inputs",
    "FaultLocalizer", "RepairWorkflow", "Dossier", "LocalizationReport", "collect_spectrum",
    "enumerate_sites", "generate_candidates",
    "SemanticAnalyzer", "SemanticReport", "Finding", "FunctionSemantics", "analyze_static", "match_refs",
]
