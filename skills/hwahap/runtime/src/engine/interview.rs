use super::*;

impl Engine {
    pub(super) fn capture_frontier(plan: &mut Plan) -> Result<()> {
        if plan.interactive {
            plan.question_frontier = frontier::derive(plan)?.ready;
            for surface in crate::plan::SURFACES {
                if plan
                    .open_items
                    .iter()
                    .any(|o| o.id == format!("NA-{surface}"))
                {
                    plan.question_frontier.push(surface.id().into());
                }
            }
        }
        Ok(())
    }

    pub(super) async fn refine(
        &self,
        mut run: Run,
        sessions: &dyn Sessions,
    ) -> Result<StepOutcome> {
        let mut plan = self.require_plan()?;
        let prompt = format!("{}\n\nINTERVIEW ROUND FOLLOW-UP: Recompute decisions implied by the answers, including concrete desired and rejected examples. Return an empty proposal only after checking the remaining branches. Pending interpretation items: {}",
            prompts::decisions(&plan, &[]), serde_json::to_string(&plan.open_items).map_err(|e| Error::Internal(e.to_string()))?);
        let result = self.ask(sessions, Role::Recommender, None, prompt).await?;
        self.apply_decisions(&mut plan, &result.final_message)?;
        Self::capture_frontier(&mut plan)?;
        self.save_plan(&plan)?;
        run.state = RunState::Deciding;
        self.store.write_run(&*self.clock, &run)?;
        if crate::dialogue::QuestionBatch::derive(&plan)?.is_none() {
            return self.decide(run, None);
        }
        Ok(self.report(&run, self.describe(&run, Some(&plan))?))
    }
}
