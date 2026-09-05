use super::*;
use crate::pr_review::ReviewProgress;

impl Engine {
    pub(super) async fn review_pr(
        &self,
        run: Run,
        _sessions: &dyn Sessions,
    ) -> Result<StepOutcome> {
        let plan = self.require_frozen_plan(&run)?;
        self.require_review_progress(&run, &plan)?;
        Ok(self.report(&run, self.describe(&run, Some(&plan))?))
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
