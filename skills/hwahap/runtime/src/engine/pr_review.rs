use super::*;
use crate::pr_review::{
    read_evidence, save_evidence, AttackReport, DefenseReport, ReviewProgress, ReviewStage,
};
use crate::session::SessionReceipt;
mod repair;

#[derive(serde::Serialize, serde::Deserialize)]
struct ReviewRecord<T> {
    report: T,
    receipt: SessionReceipt,
}

impl Engine {
    pub(super) fn refresh_review_report(
        &self,
        run: &Run,
        plan: &Plan,
        progress: &ReviewProgress,
    ) -> Result<()> {
        let cost = crate::cost::summary(&self.store)?;
        let report = format!("{}\n## PR review\n\nHead: `{}`; round: {}; repairs: {}; stage: {:?}.\n\nDetailed review and reproduction evidence remains local in `.hwahap/artifacts`.\n\n## Cost evidence\n\n```json\n{}\n```\n",
            self.report_markdown(plan, run), progress.binding.head, progress.round,
            progress.repairs, progress.stage, serde_json::to_string_pretty(&cost).map_err(|e| Error::Internal(e.to_string()))?);
        let pr = self.forge.update_draft(
            &self.store.worktree_path(),
            &plan.base_branch,
            &run.branch,
            &progress.binding.pr_url,
            &plan.goal.statement,
            &report,
        )?;
        if pr.head_sha != progress.binding.head {
            return Err(Error::BoundaryViolation(
                "PR head changed while refreshing report".into(),
            ));
        }
        self.store.write_report(&report)
    }

    /// Recheck only this run's published draft, including one created by an older pinned runtime.
    pub fn recheck_pr(&self) -> Result<StepOutcome> {
        let mut run = self
            .store
            .recover()?
            .ok_or_else(|| Error::Rejected("no run to recheck".into()))?;
        if !matches!(
            run.state,
            RunState::AwaitingAdjustOrShip { .. }
                | RunState::PrReview { .. }
                | RunState::Blocked { .. }
        ) {
            return Err(Error::Rejected("this run has no reviewable draft".into()));
        }
        let plan = self.require_frozen_plan(&run)?;
        let saved = ReviewProgress::load(&self.store)?;
        let digest = plan.digest()?;
        let url = run
            .state
            .pr_url()
            .map(str::to_string)
            .or_else(|| saved.as_ref().map(|p| p.binding.pr_url.clone()))
            .ok_or_else(|| Error::Rejected("no recorded draft to recheck".into()))?;
        let worktree = self.store.worktree_path();
        let head = self.git.run_in(&worktree, &["rev-parse", "HEAD"])?;
        if !self.git.is_clean(&worktree)?
            || self
                .git
                .run_in(&worktree, &["rev-parse", "--abbrev-ref", "HEAD"])?
                != run.branch
            || self
                .forge
                .existing_draft(&worktree, &plan.base_branch, &run.branch)?
                .as_deref()
                != Some(url.as_str())
            || self.forge.head_sha(&worktree, &url)? != head
            || saved
                .as_ref()
                .is_some_and(|p| p.binding.contract_digest != digest)
        {
            return Err(Error::BoundaryViolation(
                "recheck PR ownership, head or contract mismatch".into(),
            ));
        }
        // Retain the validated legacy draft before replacing its URL-bearing run state.
        if saved.is_none() {
            ReviewProgress {
                binding: crate::pr_review::ReviewBinding {
                    pr_url: url,
                    head,
                    contract_digest: digest,
                },
                round: 1,
                stage: ReviewStage::Attack,
                repairs: 0,
            }
            .save(&self.store)?;
        } else if let Some(mut previous) = saved {
            // Explicit recovery must not replay an immutable incomplete/legacy verdict.
            // Preserve repair checkpoints: their commit may already be prepared or published.
            let mut legacy = false;
            for team in ["attack", "defense"] {
                if let Some(record) =
                    read_evidence::<serde_json::Value>(&self.store, &previous.artifact(team)?)?
                {
                    legacy |= record.pointer("/report/security").is_none();
                }
            }
            if previous.stage != ReviewStage::Repair
                && (matches!(run.state, RunState::Blocked { .. }) || legacy)
            {
                previous.round = previous
                    .round
                    .checked_add(1)
                    .ok_or_else(|| Error::ExecutionLimit("review round overflow".into()))?;
                previous.stage = ReviewStage::Attack;
                previous.save(&self.store)?;
            }
        }
        run.reviewed_head = None;
        run.state = RunState::FinalVerifying;
        self.store.write_run(&*self.clock, &run)?;
        Ok(self.report(
            &run,
            "Rechecking the existing draft: full suite, then independent Astra attack and defense."
                .into(),
        ))
    }

    pub(super) fn require_completed_reviews(&self, run: &Run, plan: &Plan) -> Result<()> {
        let p = self.require_review_progress(run, plan)?;
        if p.stage != ReviewStage::Complete || run.reviewed_head.as_ref() != Some(&p.binding.head) {
            return Err(Error::Rejected(
                "both current-head PR reviews must complete before SHIP".into(),
            ));
        }
        let a: ReviewRecord<AttackReport> = read_evidence(&self.store, &p.artifact("attack")?)?
            .ok_or_else(|| Error::Corrupt("missing attack report".into()))?;
        let d: ReviewRecord<DefenseReport> =
            read_evidence(&self.store, &p.artifact("defense")?)?
                .ok_or_else(|| Error::Corrupt("missing defense report".into()))?;
        d.report.validate(&a.report, &p.binding)?;
        Self::separate_reviewers(&a.receipt, &d.receipt)?;
        for (receipt, role) in [
            (&a.receipt, Role::UnitReviewer),
            (&d.receipt, Role::FinalReview),
        ] {
            receipt.verify_for(
                &SessionSpec {
                    cwd: self.store.worktree_path(),
                    role,
                    unit: None,
                    prompt: String::new(),
                },
                &self.config.profiles,
            )?;
        }
        if a.report.security.blocked()
            || d.report.security.blocked()
            || d.report.unresolved()
            || !d.report.repair_findings(&a.report).is_empty()
        {
            return Err(Error::Rejected(
                "incomplete security coverage or unresolved/confirmed PR findings prevent SHIP"
                    .into(),
            ));
        }
        Ok(())
    }
    pub(super) async fn review_pr(
        &self,
        mut run: Run,
        sessions: &dyn Sessions,
    ) -> Result<StepOutcome> {
        let plan = self.require_frozen_plan(&run)?;
        if ReviewProgress::load(&self.store)?.is_some_and(|p| p.stage == ReviewStage::Repair) {
            return self.repair_pr(run, sessions).await;
        }
        let mut progress = self.require_review_progress(&run, &plan)?;
        let diff = self.git.run_in(
            &self.store.worktree_path(),
            &[
                "diff",
                &format!(
                    "{}...HEAD",
                    plan.base_commit.as_deref().unwrap_or(&plan.base_branch)
                ),
            ],
        )?;
        let contract = render::plan_markdown(&plan)?;
        let attack: ReviewRecord<AttackReport> = self
            .review_record(
                sessions,
                Role::UnitReviewer,
                &progress,
                prompts::pr_attack(&progress.binding, &contract, &tail(&diff, 400_000)),
            )
            .await?;
        attack.report.validate(&progress.binding)?;
        self.require_review_progress(&run, &plan)?;
        save_evidence(&self.store, &progress.artifact("attack")?, &attack)?;
        progress.stage = ReviewStage::Defense;
        progress.save(&self.store)?;
        let defense: ReviewRecord<DefenseReport> = self
            .review_record(
                sessions,
                Role::FinalReview,
                &progress,
                prompts::pr_defense(&attack.report, &contract, &tail(&diff, 400_000)),
            )
            .await?;
        defense.report.validate(&attack.report, &progress.binding)?;
        Self::separate_reviewers(&attack.receipt, &defense.receipt)?;
        self.require_review_progress(&run, &plan)?;
        save_evidence(&self.store, &progress.artifact("defense")?, &defense)?;
        if attack.report.security.blocked()
            || defense.report.security.blocked()
            || defense.report.unresolved()
        {
            run.state = RunState::Blocked {
                reason: "PR review left incomplete security coverage or unresolved findings; evidence and draft are retained"
                    .into(),
            };
        } else if !defense.report.repair_findings(&attack.report).is_empty() {
            progress.stage = ReviewStage::Repair;
        } else {
            progress.stage = ReviewStage::Complete;
            run.reviewed_head = Some(progress.binding.head.clone());
            run.state = RunState::AwaitingAdjustOrShip {
                pr_url: progress.binding.pr_url.clone(),
                challenge: plan.digest()?.challenge(),
            };
        }
        progress.save(&self.store)?;
        self.refresh_review_report(&run, &plan, &progress)?;
        self.store.write_run(&*self.clock, &run)?;
        Ok(self.report(&run, self.describe(&run, Some(&plan))?))
    }

    async fn review_record<T: serde::de::DeserializeOwned>(
        &self,
        sessions: &dyn Sessions,
        role: Role,
        progress: &ReviewProgress,
        prompt: String,
    ) -> Result<ReviewRecord<T>> {
        let team = if role == Role::UnitReviewer {
            "attack"
        } else {
            "defense"
        };
        let record: ReviewRecord<T> = match read_evidence(&self.store, &progress.artifact(team)?)? {
            Some(record) => record,
            None => {
                let outcome = self.ask(sessions, role, None, prompt).await?;
                ReviewRecord {
                    report: serde_json::from_str(&outcome.final_message).map_err(|e| {
                        Error::BoundaryViolation(format!("invalid {team} report: {e}"))
                    })?,
                    receipt: outcome.receipt,
                }
            }
        };
        let spec = SessionSpec {
            cwd: self.store.worktree_path(),
            role,
            unit: None,
            prompt: String::new(),
        };
        record.receipt.verify_for(&spec, &self.config.profiles)?;
        Ok(record)
    }

    fn separate_reviewers(attack: &SessionReceipt, defense: &SessionReceipt) -> Result<()> {
        match (attack, defense) {
            (SessionReceipt::Native(a), SessionReceipt::Native(d))
                if a.agent_id != d.agent_id
                    && a.agent_id != "coordinator"
                    && d.agent_id != "coordinator"
                    && a.model_requested == "gpt-6-astra"
                    && d.model_requested == "gpt-6-astra" =>
            {
                Ok(())
            }
            (SessionReceipt::AdapterEcho(_), SessionReceipt::AdapterEcho(_)) => Ok(()),
            _ => Err(Error::BoundaryViolation(
                "PR review needs two distinct read-only Astra children".into(),
            )),
        }
    }

    pub(super) fn require_review_progress(&self, run: &Run, plan: &Plan) -> Result<ReviewProgress> {
        let progress = ReviewProgress::load(&self.store)?
            .ok_or_else(|| Error::Corrupt("missing published PR review state".into()))?;
        let worktree = self.store.worktree_path();
        if progress.binding.contract_digest != plan.digest()?
            || run.state.pr_url() != Some(progress.binding.pr_url.as_str())
            || self.git.run_in(&worktree, &["rev-parse", "HEAD"])? != progress.binding.head
            || self
                .git
                .run_in(&worktree, &["rev-parse", "--abbrev-ref", "HEAD"])?
                != run.branch
            || !self.git.is_clean(&worktree)?
            || self
                .forge
                .existing_draft(&worktree, &plan.base_branch, &run.branch)?
                .as_deref()
                != Some(progress.binding.pr_url.as_str())
            || self.forge.head_sha(&worktree, &progress.binding.pr_url)? != progress.binding.head
        {
            return Err(Error::BoundaryViolation(
                "PR, commit or contract changed during review".into(),
            ));
        }
        Ok(progress)
    }
}
