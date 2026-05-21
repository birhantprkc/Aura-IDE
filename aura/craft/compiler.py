from __future__ import annotations
import ast
from .types import ProposalCapsule, CraftIssue, CompiledPatch, CompilerBounce, CompilerReject, CraftDecision, filter_delta_issues
from .engine import CraftEngine
from .contract_gate import ContractGate
import dataclasses
from .reference_checker import ReferenceChecker
from .mutator import SafeMutator
from .formatter import CodeFormatter

class CompilerService:
    """The strict compiler boundary between LLM and user workspace.
    
    All LLM file writes must route through process_proposal().
    Tracks per-proposal retry state via a bounce counter.
    """
    
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self._attempts: dict[str, int] = {}
        self._engine = CraftEngine()
        self._contract_gate = ContractGate()
        self._ref_checker = ReferenceChecker()
        self._mutator = SafeMutator()
        self._formatter = CodeFormatter()
    
    def process_proposal(self, capsule: ProposalCapsule, workspace_root=None) -> CompiledPatch | CompilerBounce | CompilerReject:
        """Main entry point. Returns CompiledPatch on success, CompilerBounce
        for repairable rejections, CompilerReject when max retries exhausted."""
        
        # Simple proposal ID for phase 1
        proposal_id = capsule.path.as_posix()
        
        attempt = self._attempts.get(proposal_id, 0) + 1
        self._attempts[proposal_id] = attempt
        
        decision = self._run_pipeline(capsule, workspace_root=workspace_root)
        
        if decision.approved:
            self.reset_attempts(proposal_id)
            return CompiledPatch(
                capsule=capsule,
                cleaned_code=decision.cleaned_code,
                checks_passed=[c for c in ["craft_engine", "contract_gate" if capsule.contract else None, "reference_checker"] if c is not None],
            )
        
        if attempt <= self.max_retries:
            repair_instructions = self._build_repair_instructions(decision.issues)
            return CompilerBounce(
                capsule=capsule,
                issues=decision.issues,
                repair_instructions=repair_instructions,
                attempt_number=attempt,
                max_attempts=self.max_retries,
            )
            
        return CompilerReject(
            capsule=capsule,
            issues=decision.issues,
            total_attempts=attempt,
            reason=f"Rejected after {attempt} attempts due to unresolvable issues.",
        )
    
    def _run_pipeline(self, capsule: ProposalCapsule, workspace_root=None):
        """Run the compiler pipeline stages. In Phase 1, delegates to CraftEngine."""
        
        # Stage 0: SafeMutator
        cleaned = self._mutator.mutate(capsule.proposed_code, path=capsule.path)
        if cleaned != capsule.proposed_code:
            capsule.proposed_code = cleaned
            try:
                capsule.ast_tree = ast.parse(cleaned)
            except SyntaxError:
                pass
                
        # Stage 1: Existing CraftEngine checks
        decision = self._engine.process_proposal(capsule)
        
        # Stage 2: Contract Gate (runs for ALL files with a contract)
        if capsule.contract is not None:
            contract_issues = self._contract_gate.verify(capsule)
            if contract_issues:
                # Merge contract issues into the decision
                if decision.approved:
                    decision = CraftDecision(approved=False, issues=contract_issues, cleaned_code=capsule.proposed_code)
                else:
                    # Use a set to avoid duplicate issues, comparing by (code, line) for simplicity
                    existing_issues_set = {(issue.code, issue.line) for issue in decision.issues}
                    for new_issue in contract_issues:
                        if (new_issue.code, new_issue.line) not in existing_issues_set:
                            decision.issues.append(new_issue)
                            existing_issues_set.add((new_issue.code, new_issue.line))
                            
        # Stage 3: Reference Validation
        proposed_ref_issues = self._ref_checker.check(capsule, workspace_root=workspace_root)
        if proposed_ref_issues:
            original_ref_issues = []
            if not capsule.is_new_file and capsule.original_code:
                baseline_capsule = dataclasses.replace(
                    capsule,
                    proposed_code=capsule.original_code,
                    changed_line_ranges=[]
                )
                try:
                    baseline_capsule.ast_tree = ast.parse(capsule.original_code)
                except SyntaxError:
                    baseline_capsule.ast_tree = None
                
                original_ref_issues = self._ref_checker.check(baseline_capsule, workspace_root=workspace_root)

            filtered_ref_issues = filter_delta_issues(
                proposed_issues=proposed_ref_issues,
                original_issues=original_ref_issues,
                changed_ranges=capsule.changed_line_ranges,
                is_new_file=capsule.is_new_file
            )

            # Merge filtered reference issues into the decision
            if filtered_ref_issues:
                if decision.approved:
                    decision = CraftDecision(approved=False, issues=filtered_ref_issues, cleaned_code=capsule.proposed_code)
                else:
                    existing_issues_set = {(issue.code, issue.line) for issue in decision.issues}
                    for new_issue in filtered_ref_issues:
                        if (new_issue.code, new_issue.line) not in existing_issues_set:
                            decision.issues.append(new_issue)
                            existing_issues_set.add((new_issue.code, new_issue.line))
                        
        # Final Stage: CodeFormatter
        if decision.approved:
            decision.cleaned_code = self._formatter.format_code(decision.cleaned_code, workspace_root=workspace_root)
        
        return decision
    
    def _build_repair_instructions(self, issues: list[CraftIssue]) -> str:
        """Build human-readable repair instructions from issues list."""
        lines = ["Your code changes were rejected by the compiler. Please fix the following issues:"]
        for issue in issues:
            lines.append(f"- Line {issue.line}: [{issue.code}] {issue.message}")
            if issue.suggestion:
                lines.append(f"  Suggestion: {issue.suggestion}")
        return "\n".join(lines)
    
    def invalidate_workspace_index(self, workspace_root=None) -> None:
        """Clear cached workspace index in the reference checker."""
        self._ref_checker.invalidate_workspace_index(workspace_root)

    def reset_attempts(self, proposal_id: str) -> None:
        """Clear retry tracking for a proposal."""
        self._attempts.pop(proposal_id, None)

# Module-level singleton
compiler_service = CompilerService()