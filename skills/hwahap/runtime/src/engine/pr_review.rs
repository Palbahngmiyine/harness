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
        if defense.report.unresolved() {
            run.state = RunState::Blocked {
                reason: "PR defense left unresolved findings; evidence and draft are retained"
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

    fn require_review_progress(&self, run: &Run, plan: &Plan) -> Result<ReviewProgress> {
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
