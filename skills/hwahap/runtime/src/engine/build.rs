use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

use crate::plan::{Acceptance, Plan, Requirement, Test, Unit};
use crate::{validate, Error, Result};

#[derive(Debug, Clone, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct BuildRequest {
    /// User's exact instruction authorizing execution without planning; never infer this consent.
    pub user_instruction: String,
    pub objective: String,
    /// Remote target branch, for example main.
    pub base_branch: String,
    /// A new codex/ branch. Execution starts from the caller's current committed HEAD.
    pub branch: String,
    pub units: Vec<BuildUnit>,
    pub full_suite: String,
}

#[derive(Debug, Clone, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct BuildUnit {
    pub title: String,
    /// Complete behavior, constraints and observable success for this unit.
    pub acceptance: String,
    pub paths: Vec<String>,
    pub test_command: String,
}

impl BuildRequest {
    /// Construct and validate an execution contract without planning decisions or reviews.
    pub fn plan(&self, id: &str, base_commit: &str) -> Result<Plan> {
        if !self.branch.starts_with("codex/") || self.branch == self.base_branch {
            return Err(Error::Rejected(
                "BUILD needs a new codex/ branch distinct from its base".into(),
            ));
        }
        let mut plan = Plan::new(id, &self.base_branch, &self.objective);
        plan.execution_authorization = Some(self.user_instruction.clone());
        plan.base_commit = Some(base_commit.into());
        plan.full_suite = self.full_suite.clone();
        for (index, unit) in self.units.iter().enumerate() {
            let n = index + 1;
            let (r, a, u) = (format!("R{n}"), format!("A{n}"), format!("U{n}"));
            plan.goal.success.push(unit.acceptance.clone());
            plan.requirements.push(Requirement {
                id: r.clone(),
                statement: unit.acceptance.clone(),
                decision_ids: vec![],
            });
            plan.acceptance.push(Acceptance {
                id: a.clone(),
                requirement_ids: vec![r],
                observable: unit.acceptance.clone(),
            });
            plan.units.push(Unit {
                id: u.clone(),
                title: unit.title.clone(),
                paths: unit.paths.clone(),
                acceptance_ids: vec![a.clone()],
                depends_on: if n == 1 {
                    vec![]
                } else {
                    vec![format!("U{}", n - 1)]
                },
                probe: false,
            });
            plan.tests.push(Test {
                id: format!("T{n}"),
                command: unit.test_command.clone(),
                acceptance_ids: vec![a],
                unit_id: u,
            });
        }
        let errors = validate::build_blockers(&plan)?;
        if !errors.is_empty() {
            return Err(Error::Rejected(format!(
                "invalid BUILD contract: {errors:?}"
            )));
        }
        Ok(plan)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request() -> BuildRequest {
        BuildRequest {
            user_instruction: "Skip planning and implement the requested check".into(),
            objective: "Validate settings".into(),
            base_branch: "main".into(),
            branch: "codex/check".into(),
            full_suite: "cargo test".into(),
            units: vec![BuildUnit {
                title: "Reject invalid settings".into(),
                acceptance: "Invalid settings return an error without changing data".into(),
                paths: vec!["src".into()],
                test_command: "cargo test settings".into(),
            }],
        }
    }

    #[test]
    fn direct_contract_has_no_fabricated_planning_evidence() {
        let input = request();
        let plan = input.plan("build", "abc").unwrap();
        assert_eq!(
            plan.execution_authorization.as_ref(),
            Some(&input.user_instruction)
        );
        assert!(plan.decisions.is_empty() && plan.frozen.is_none());
        assert!(plan.reviews.critic.is_none() && plan.reviews.cold_consumer.is_none());
        assert!(!validate::freeze_blockers(&plan).unwrap().is_empty());
        assert!(validate::build_blockers(&plan).unwrap().is_empty());
        assert!(crate::render::plan_markdown(&plan)
            .unwrap()
            .contains("Planning omitted"));
        assert!(crate::prompts::implementer(&plan, &plan.units[0], &[])
            .contains(&input.units[0].acceptance));
    }

    #[test]
    fn direct_contract_rejects_missing_consent_scope_and_tests() {
        let mut input = request();
        input.user_instruction.clear();
        assert!(input.plan("build", "abc").is_err());
        input = request();
        input.units[0].paths = vec!["../outside".into()];
        assert!(input.plan("build", "abc").is_err());
        input = request();
        input.units[0].test_command.clear();
        assert!(input.plan("build", "abc").is_err());
        input = request();
        input.units.clear();
        assert!(input.plan("build", "abc").is_err());
    }
}
