use super::*;

impl Engine {
    pub(super) fn prepare_plan_worktree(&self, run: &Run, plan: &Plan) -> Result<String> {
        let branch = if run.branch.is_empty() {
            format!("hwahap/{}", plan.goal_id)
        } else {
            run.branch.clone()
        };
        let worktree = self.store.worktree_path();
        let source = match &plan.source_head {
            Some(head) => head.clone(),
            None => self.git.run(&["rev-parse", &plan.base_branch])?,
        };
        if worktree.symlink_metadata().is_ok() {
            self.check_plan_worktree(&branch, Some(&source))?;
        } else if !run.branch.is_empty() {
            return Err(Error::Rejected(
                "the owned BUILD worktree is missing".into(),
            ));
        } else if self.git.branch_exists(&branch)? {
            if self.git.run(&["rev-parse", &branch])? != source {
                return Err(Error::Rejected(
                    "the interrupted PLAN branch no longer matches its source".into(),
                ));
            }
            self.git.run(&[
                "worktree",
                "add",
                worktree
                    .to_str()
                    .ok_or_else(|| Error::Rejected("non-UTF8 worktree".into()))?,
                &branch,
            ])?;
            self.check_plan_worktree(&branch, Some(&source))?;
        } else {
            self.git.add_worktree(&worktree, &branch, &source)?;
            self.check_plan_worktree(&branch, Some(&source))?;
        }
        Ok(branch)
    }

    pub(super) fn check_plan_worktree(&self, branch: &str, head: Option<&str>) -> Result<()> {
        let worktree = self.store.worktree_path();
        if worktree
            .symlink_metadata()
            .map_err(|e| Error::io(&worktree, e))?
            .file_type()
            .is_symlink()
            || self.git.run_in(
                &worktree,
                &["rev-parse", "--path-format=absolute", "--git-common-dir"],
            )? != self
                .git
                .run(&["rev-parse", "--path-format=absolute", "--git-common-dir"])?
            || self
                .git
                .run_in(&worktree, &["rev-parse", "--show-toplevel"])?
                != worktree
                    .canonicalize()
                    .map_err(|e| Error::io(&worktree, e))?
                    .to_string_lossy()
            || self
                .git
                .run_in(&worktree, &["rev-parse", "--abbrev-ref", "HEAD"])?
                != branch
            || !self.git.is_clean(&worktree)?
            || head.is_some_and(|expected| {
                self.git
                    .run_in(&worktree, &["rev-parse", "HEAD"])
                    .as_deref()
                    .ok()
                    != Some(expected)
            })
        {
            return Err(Error::Rejected(
                "PLAN worktree ownership, source or clean state changed".into(),
            ));
        }
        Ok(())
    }
}
