//! The state machine: PLAN, FREEZE, autonomous CODING, draft PR, ADJUST or SHIP.
//!
//! Everything the host can ask for arrives here through three entry points — [`Engine::step`],
//! [`Engine::status`], [`Engine::ship`] — and every decision about what happens next is made here
//! rather than by the calling model. That is the point of having only three tools.
//!
//! Agent sessions reach the engine through the [`Sessions`] trait, not through the ACP client
//! directly. In production that trait is a live `codex-acp` session; in tests it is a script. The
//! engine cannot tell the difference, which is what makes the whole cycle — including crash
//! recovery, out-of-scope resets, rework, and plan conflicts — testable without a model.

use std::future::Future;
use std::path::{Path, PathBuf};
use std::pin::Pin;

use crate::acp::{SessionOutcome, SessionSpec};
use crate::agentresult::{ReviewResult, Verdict, WorkerResult, WorkerStatus};
use crate::answer::{parse_message, Directive};
use crate::canonical::Digest;
use crate::clock::{Clock, SystemClock};
use crate::config::Config;
use crate::error::{Error, Result};
use crate::forge::Forge;
use crate::git::{paths_outside, Git};
use crate::plan::{Answer, Frozen, Plan, PlanReview, Selection, Surface, SurfaceStatus, Unit};
use crate::profile::Role;
use crate::state::{Next, Run, RunState, Store};
use crate::{frontier, prompts, proposal, render, validate};

/// How many implementation attempts one unit gets before the run is blocked.
///
/// Attempt 1 implements, attempt 2 reworks against findings, and attempt 3 only happens when the
/// diagnosis says there is a specific reason it would succeed. Beyond that a fourth try is just the
/// same failure again at the user's expense.
const MAX_ATTEMPTS: u32 = 3;

/// A source of agent sessions.
///
/// Boxed futures rather than `async fn` in the trait, because the engine holds it behind `dyn` so
/// that a scripted implementation can stand in for a live adapter.
pub trait Sessions: Send + Sync {
    fn run<'a>(
        &'a self,
        spec: &'a SessionSpec,
    ) -> Pin<Box<dyn Future<Output = Result<SessionOutcome>> + Send + 'a>>;
}

/// What a tool call reports back.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StepOutcome {
    pub run_id: String,
    pub phase: String,
    pub state: String,
    pub next: String,
    pub message: String,
    pub plan_digest: Option<String>,
    pub pr_url: Option<String>,
}

/// One repository's engine.
pub struct Engine {
    repo_root: PathBuf,
    store: Store,
    git: Git,
    forge: Forge,
    config: Config,
    clock: Box<dyn Clock>,
}

impl Engine {
    /// Opens the engine for a repository, creating `.hwahap/` if needed.
    pub fn open(repo_root: &Path) -> Result<Engine> {
        let git = Git::open(repo_root)?;
        let store = Store::open(repo_root)?;
        let config = Config::load(store.root())?;
        Ok(Engine {
            repo_root: repo_root.to_path_buf(),
            store,
            git,
            forge: Forge::default(),
            config,
            clock: Box::new(SystemClock),
        })
    }

    /// Replaces the clock and the forge, for tests.
    pub fn with_parts(mut self, clock: Box<dyn Clock>, forge: Forge) -> Engine {
        self.clock = clock;
        self.forge = forge;
        self
    }

    /// Reads the run without changing anything.
    pub fn status(&self) -> Result<StepOutcome> {
        match self.store.read_run()? {
            None => Ok(StepOutcome {
                run_id: String::new(),
                phase: "plan".into(),
                state: "no_run".into(),
                next: "await_user".into(),
                message: "No Hwahap run is active in this repository. Send an implementation \
                          request to start one."
                    .into(),
                plan_digest: None,
                pr_url: None,
            }),
            Some(run) => {
                let plan = self.store.read_plan()?;
                Ok(self.report(&run, self.describe(&run, plan.as_ref())?))
            }
        }
    }

    /// Starts or advances the run, opening a live adapter only for the states that need one.
    pub async fn step(
        &self,
        request: Option<&str>,
        user_input: Option<&str>,
    ) -> Result<StepOutcome> {
        match self.resolve(request)? {
            Resolved::Started(outcome) => Ok(outcome),
            Resolved::Advance(run) if run.state.needs_sessions() => self.with_sessions(run).await,
            Resolved::Advance(run) => self.advance(run, user_input),
        }
    }

    /// The same dispatch against a supplied session source.
    ///
    /// This is what makes the whole cycle testable: a scripted `Sessions` drives crash recovery,
    /// out-of-scope resets, rework, and plan conflicts without a model or an adapter process.
    pub async fn step_with(
        &self,
        sessions: &dyn Sessions,
        request: Option<&str>,
        user_input: Option<&str>,
    ) -> Result<StepOutcome> {
        match self.resolve(request)? {
            Resolved::Started(outcome) => Ok(outcome),
            Resolved::Advance(run) if run.state.needs_sessions() => self.drive(run, sessions).await,
            Resolved::Advance(run) => self.advance(run, user_input),
        }
    }

    fn resolve(&self, request: Option<&str>) -> Result<Resolved> {
        let existing = self.store.recover()?;
        match (existing, request) {
            (None, Some(request)) => Ok(Resolved::Started(self.start(request)?)),
            (None, None) => Err(Error::Rejected(
                "there is no active Hwahap run in this repository; call hwahap_step again with \
                 `request` set to the user's implementation request"
                    .into(),
            )),
            (Some(run), Some(request)) if run.state.is_terminal() => {
                // A finished run does not block the next one, but it is not silently overwritten:
                // the previous run's files are archived first.
                self.store.archive(&*self.clock)?;
                Ok(Resolved::Started(self.start(request)?))
            }
            (Some(run), Some(_)) => Err(Error::Rejected(format!(
                "a Hwahap run is already active in this repository ({}, state {}). Finish or abandon \
                 it before starting another; Hwahap allows one active run per repository.",
                run.run_id,
                run.state.name()
            ))),
            (Some(run), None) => Ok(Resolved::Advance(run)),
        }
    }

    /// Marks the draft pull request ready, after re-checking everything it depends on.
    pub fn ship(&self, confirmation: &str) -> Result<StepOutcome> {
        let mut run = self
            .store
            .read_run()?
            .ok_or_else(|| Error::Rejected("there is no Hwahap run to ship".into()))?;
        let plan = self.require_plan()?;

        let RunState::AwaitingAdjustOrShip { pr_url, challenge } = run.state.clone() else {
            return Err(Error::Rejected(format!(
                "this run is in state {} and has nothing to ship; a draft pull request must exist \
                 first",
                run.state.name()
            )));
        };

        let parsed = parse_message(confirmation);
        let typed = parsed.directives.iter().find_map(|d| match d {
            Directive::Ship { challenge } => Some(challenge.clone()),
            _ => None,
        });
        let Some(typed) = typed else {
            return Err(Error::Rejected(format!(
                "that is not a ship confirmation. The user must type exactly:\n\nSHIP {challenge}"
            )));
        };
        if typed != challenge {
            return Err(Error::Rejected(format!(
                "the confirmation names {typed}, but this run's challenge is {challenge}. \
                 Something changed since the summary was shown; re-read it before shipping."
            )));
        }

        // Everything below is re-checked now rather than trusted from when the PR was opened.
        if plan.frozen.as_ref().map(|f| &f.digest) != run.plan_digest.as_ref() {
            return Err(Error::Rejected(
                "the frozen plan has changed since this pull request was created; ship is refused"
                    .into(),
            ));
        }
        let head = self.forge.head_sha(&self.repo_root, &pr_url)?;
        if Some(&head) != run.reviewed_head.as_ref() {
            return Err(Error::Rejected(format!(
                "the pull request head is now {head}, but the final review looked at {}. Re-run the \
                 cycle before shipping.",
                run.reviewed_head.as_deref().unwrap_or("nothing")
            )));
        }
        if !self.forge.checks_passed(&self.repo_root, &pr_url)? {
            return Err(Error::Rejected(
                "the pull request's required checks have not all succeeded; ship is refused".into(),
            ));
        }

        self.forge.mark_ready(&self.repo_root, &pr_url)?;
        run.state = RunState::Shipped {
            pr_url: pr_url.clone(),
        };
        self.store.write_run(&*self.clock, &run)?;
        Ok(self.report(
            &run,
            format!("{pr_url} is now ready for review. Hwahap does not merge; that is yours."),
        ))
    }

    // ---------------------------------------------------------------- planning

    fn start(&self, request: &str) -> Result<StepOutcome> {
        if request.trim().is_empty() {
            return Err(Error::Rejected(
                "the implementation request is empty".into(),
            ));
        }
        let base_branch = self.git.current_branch()?;
        let goal_id = goal_id(&self.clock.now(), request);
        let plan = Plan::new(&goal_id, &base_branch, request.trim());
        self.store.write_plan(&plan)?;
        self.store
            .write_plan_markdown(&render::plan_markdown(&plan)?)?;

        let run = Run {
            schema: crate::plan::SCHEMA.to_string(),
            run_id: goal_id.clone(),
            goal_id,
            revision: 1,
            state: RunState::Inspecting,
            accepted_units: Vec::new(),
            plan_digest: None,
            branch: String::new(),
            reviewed_head: None,
            seq: 0,
        };
        self.store.write_run(&*self.clock, &run)?;
        Ok(self.report(
            &run,
            "Hwahap is reading the repository before asking anything.".into(),
        ))
    }

    /// The states that need no agent session.
    fn advance(&self, run: Run, user_input: Option<&str>) -> Result<StepOutcome> {
        match run.state.clone() {
            RunState::Deciding => self.decide(run, user_input),
            RunState::AwaitingConfirmation { challenge } => {
                self.freeze(run, &challenge, user_input)
            }
            RunState::AwaitingAdjustOrShip { .. } => self.adjust(run, user_input),
            RunState::Shipped { .. } | RunState::Blocked { .. } | RunState::PlanConflict { .. } => {
                let plan = self.store.read_plan()?;
                let message = self.describe(&run, plan.as_ref())?;
                Ok(self.report(&run, message))
            }
            other => Err(Error::Internal(format!(
                "state {} needs an agent session and cannot be advanced without one",
                other.name()
            ))),
        }
    }

    /// Runs the states that need a live adapter.
    async fn with_sessions(&self, run: Run) -> Result<StepOutcome> {
        let profiles = self.config.profiles.clone();
        crate::acp::with_link(&self.config.adapter, &profiles, async move |link| {
            self.drive(run, &link).await
        })
        .await
    }

    /// The state dispatch that needs sessions. Split out so tests can drive it with a script.
    pub async fn drive(&self, run: Run, sessions: &dyn Sessions) -> Result<StepOutcome> {
        match run.state.clone() {
            RunState::Inspecting => self.inspect(run, sessions).await,
            RunState::Proving => self.prove(run, sessions).await,
            RunState::Coding { .. } => self.code(run, sessions).await,
            RunState::FinalVerifying => self.finalize(run, sessions).await,
            other => Err(Error::Internal(format!(
                "state {} does not need an agent session",
                other.name()
            ))),
        }
    }

    async fn inspect(&self, mut run: Run, sessions: &dyn Sessions) -> Result<StepOutcome> {
        let mut plan = self.require_plan()?;

        let facts = self
            .ask(
                sessions,
                Role::FactFinder,
                None,
                prompts::fact_finder(&format!(
                    "Everything a planner needs to know about this repository before designing: \
                     {}",
                    plan.goal.statement
                )),
            )
            .await?;
        let facts = proposal::FactsProposal::parse(&facts.final_message, &plan)?;
        plan.facts.extend(facts.facts);

        let decisions = self
            .ask(
                sessions,
                Role::Recommender,
                None,
                prompts::decisions(&plan, &[]),
            )
            .await?;
        self.apply_decisions(&mut plan, &decisions.final_message)?;

        self.save_plan(&plan)?;
        run.state = RunState::Deciding;
        self.store.write_run(&*self.clock, &run)?;
        Ok(self.report(&run, self.describe(&run, Some(&plan))?))
    }

    fn decide(&self, mut run: Run, user_input: Option<&str>) -> Result<StepOutcome> {
        let mut plan = self.require_plan()?;

        if let Some(input) = user_input {
            let parsed = parse_message(input);
            if let Some(rejection) = parsed.rejection_message() {
                return Ok(self.report(&run, rejection));
            }
            self.record_answers(&mut plan, &parsed.directives)?;
            self.save_plan(&plan)?;
        }

        let frontier = frontier::derive(&plan)?;
        if !frontier.ready.is_empty() {
            let message = render::frontier_markdown(&plan, &frontier.ready)?;
            self.store.write_run(&*self.clock, &run)?;
            return Ok(self.report(&run, message));
        }
        if !frontier.blocked.is_empty() {
            run.state = RunState::Blocked {
                reason: format!(
                    "these decisions can never be answered because their prerequisites cannot be: \
                     {}",
                    frontier
                        .blocked
                        .iter()
                        .map(|b| format!("{} waits on {:?}", b.id, b.waiting_on))
                        .collect::<Vec<_>>()
                        .join("; ")
                ),
            };
            self.store.write_run(&*self.clock, &run)?;
            return Ok(self.report(&run, self.describe(&run, Some(&plan))?));
        }

        run.state = RunState::Proving;
        self.store.write_run(&*self.clock, &run)?;
        Ok(self.report(
            &run,
            "Every question is answered. Hwahap is now proving the plan before asking you to \
             confirm it."
                .into(),
        ))
    }

    async fn prove(&self, mut run: Run, sessions: &dyn Sessions) -> Result<StepOutcome> {
        let mut plan = self.require_plan()?;

        if plan.units.is_empty() {
            let structure = self
                .ask(
                    sessions,
                    Role::PlanSynthesis,
                    None,
                    prompts::structure(&plan),
                )
                .await?;
            let structure = proposal::StructureProposal::parse(&structure.final_message, &plan)?;
            plan.requirements = structure.requirements;
            plan.acceptance = structure.acceptance;
            plan.units = structure.units;
            plan.tests = structure.tests;
            plan.full_suite = structure.full_suite;
            self.save_plan(&plan)?;
        }

        let markdown = render::plan_markdown(&plan)?;
        let reviewed = plan.review_digest()?;

        let cold = self
            .ask(
                sessions,
                Role::ColdConsumer,
                None,
                prompts::cold_consumer(&markdown),
            )
            .await?;
        let cold = ReviewResult::parse(&cold.final_message)?;
        plan.reviews.cold_consumer = Some(PlanReview {
            plan_digest: reviewed.clone(),
            ts: self.clock.now(),
            passed: cold.verdict == Verdict::Pass,
            findings: cold.findings.clone(),
        });

        let critic = self
            .ask(
                sessions,
                Role::PlanCritic,
                None,
                prompts::plan_critic(&markdown),
            )
            .await?;
        let critic = ReviewResult::parse(&critic.final_message)?;
        plan.reviews.critic = Some(PlanReview {
            plan_digest: reviewed,
            ts: self.clock.now(),
            passed: critic.verdict == Verdict::Pass,
            findings: critic.findings.clone(),
        });
        self.save_plan(&plan)?;

        let mut findings = cold.findings;
        findings.extend(critic.findings);
        if !findings.is_empty() {
            // A finding is not closed by rewording: it becomes another question for the user, so
            // the plan goes back to Decide with the findings driving the next round.
            let more = self
                .ask(
                    sessions,
                    Role::Recommender,
                    None,
                    prompts::decisions(&plan, &findings),
                )
                .await?;
            self.apply_decisions(&mut plan, &more.final_message)?;
            self.save_plan(&plan)?;
            run.state = RunState::Deciding;
            self.store.write_run(&*self.clock, &run)?;
            return Ok(self.report(
                &run,
                format!(
                    "The plan review raised {} finding(s), so there are more decisions to make:\n\n{}",
                    findings.len(),
                    findings
                        .iter()
                        .map(|f| format!("- {f}"))
                        .collect::<Vec<_>>()
                        .join("\n")
                ),
            ));
        }

        let blockers = validate::freeze_blockers(&plan)?;
        if !blockers.is_empty() {
            run.state = RunState::Deciding;
            self.store.write_run(&*self.clock, &run)?;
            return Ok(self.report(
                &run,
                format!(
                    "The plan is not yet complete:\n\n{}",
                    blockers
                        .iter()
                        .map(|b| format!("- {} — {}", b.code, b.detail))
                        .collect::<Vec<_>>()
                        .join("\n")
                ),
            ));
        }

        let challenge = plan.challenge()?;
        self.store
            .write_plan_markdown(&render::plan_markdown(&plan)?)?;
        run.state = RunState::AwaitingConfirmation {
            challenge: challenge.clone(),
        };
        self.store.write_run(&*self.clock, &run)?;
        Ok(self.report(
            &run,
            format!(
                "The plan is complete. Read `.hwahap/plan.md`.\n\nAfter Hwahap freezes it, it will \
                 implement, test, review, and open a draft pull request without asking you \
                 anything else. To confirm, type exactly:\n\nCONFIRM PLAN {challenge}"
            ),
        ))
    }

    fn freeze(
        &self,
        mut run: Run,
        challenge: &str,
        user_input: Option<&str>,
    ) -> Result<StepOutcome> {
        let mut plan = self.require_plan()?;
        let Some(input) = user_input else {
            return Ok(self.report(
                &run,
                format!("Waiting for the user to type exactly:\n\nCONFIRM PLAN {challenge}"),
            ));
        };

        let parsed = parse_message(input);
        let typed = parsed.directives.iter().find_map(|d| match d {
            Directive::ConfirmPlan { challenge } => Some(challenge.clone()),
            _ => None,
        });
        let Some(typed) = typed else {
            // Answers can still arrive here: the user may have changed their mind while reading.
            if parsed
                .directives
                .iter()
                .any(|d| matches!(d, Directive::Decision { .. } | Directive::Surface { .. }))
            {
                self.record_answers(&mut plan, &parsed.directives)?;
                self.save_plan(&plan)?;
                run.state = RunState::Deciding;
                self.store.write_run(&*self.clock, &run)?;
                return Ok(self.report(
                    &run,
                    "That changed an answer, so the plan is no longer the one you were about to \
                     confirm. Hwahap is re-deriving the remaining questions."
                        .into(),
                ));
            }
            return Ok(self.report(
                &run,
                format!(
                    "That is not a confirmation. To freeze the plan the user must type \
                     exactly:\n\nCONFIRM PLAN {challenge}"
                ),
            ));
        };

        if typed != challenge {
            return Ok(self.report(
                &run,
                format!(
                    "The confirmation names {typed}, but this plan's challenge is {challenge}. The \
                     plan changed after that challenge was shown; re-read `.hwahap/plan.md` and \
                     confirm the current one."
                ),
            ));
        }

        let digest = plan.digest()?;
        plan.frozen = Some(Frozen {
            digest: digest.clone(),
            confirmed_at: self.clock.now(),
            answer_text: input.trim().to_string(),
        });
        self.store.write_plan(&plan)?;
        self.store
            .write_plan_markdown(&render::plan_markdown(&plan)?)?;

        // Checked here, at the boundary of the autonomous phase, rather than at delivery time.
        // Discovering a missing GitHub login after an hour of unattended coding wastes the run.
        self.forge.require_auth(&self.repo_root)?;

        let branch = format!("hwahap/{}", plan.goal_id);
        let worktree = self.store.worktree_path();
        if !self.git.branch_exists(&branch)? {
            self.git
                .add_worktree(&worktree, &branch, &plan.base_branch)?;
        }

        let order = validate::unit_order(&plan)?;
        let first = order
            .first()
            .cloned()
            .ok_or_else(|| Error::Rejected("the frozen plan has no units to build".into()))?;

        run.plan_digest = Some(digest);
        run.branch = branch;
        run.state = RunState::Coding {
            unit: first,
            attempt: 1,
        };
        self.store.write_run(&*self.clock, &run)?;
        Ok(self.report(
            &run,
            format!(
                "Plan frozen. Hwahap is building {} unit(s) on `{}` and will report when the draft \
                 pull request is ready.",
                order.len(),
                run.branch
            ),
        ))
    }

    // ------------------------------------------------------------------ coding

    async fn code(&self, mut run: Run, sessions: &dyn Sessions) -> Result<StepOutcome> {
        let plan = self.require_plan()?;
        let worktree = self.store.worktree_path();
        let order = validate::unit_order(&plan)?;

        for unit_id in order {
            if run.accepted_units.contains(&unit_id) {
                continue;
            }
            let unit = plan
                .unit(&unit_id)
                .ok_or_else(|| Error::Internal(format!("unit {unit_id} vanished from the plan")))?;

            match self.build_unit(&plan, unit, &worktree, sessions).await? {
                UnitOutcome::Accepted => {
                    run.accepted_units.push(unit_id.clone());
                    run.state = RunState::Coding {
                        unit: unit_id,
                        attempt: 1,
                    };
                    self.store.write_run(&*self.clock, &run)?;
                }
                UnitOutcome::Conflict(detail) => {
                    run.state = RunState::PlanConflict {
                        unit: unit_id,
                        detail: detail.clone(),
                    };
                    self.store.write_run(&*self.clock, &run)?;
                    return Ok(self.report(
                        &run,
                        format!(
                            "The frozen plan cannot hold:\n\n{detail}\n\nNo code was written for \
                             that unit. Answer the affected decisions again to continue."
                        ),
                    ));
                }
                UnitOutcome::Blocked(reason) => {
                    run.state = RunState::Blocked {
                        reason: reason.clone(),
                    };
                    self.store.write_run(&*self.clock, &run)?;
                    return Ok(self.report(&run, reason));
                }
            }
        }

        run.state = RunState::FinalVerifying;
        self.store.write_run(&*self.clock, &run)?;
        Ok(self.report(
            &run,
            "Every unit is accepted. Hwahap is running the full suite and the final review.".into(),
        ))
    }

    async fn build_unit(
        &self,
        plan: &Plan,
        unit: &Unit,
        worktree: &Path,
        sessions: &dyn Sessions,
    ) -> Result<UnitOutcome> {
        let checkpoint = self.git.run_in(worktree, &["rev-parse", "HEAD"])?;
        let mut findings: Vec<String> = Vec::new();

        for attempt in 1..=MAX_ATTEMPTS {
            self.git.reset_hard(worktree, &checkpoint)?;
            let role = if attempt == 1 {
                Role::Implementer
            } else {
                Role::Rework
            };
            let outcome = self
                .ask(
                    sessions,
                    role,
                    Some(unit.id.clone()),
                    prompts::implementer(plan, unit, &findings),
                )
                .await?;
            self.store.write_artifact(
                &format!("{}-attempt-{attempt}.md", unit.id),
                &outcome.transcript,
            )?;

            let result = match WorkerResult::parse(&outcome.final_message) {
                Ok(result) => result,
                Err(e) => {
                    findings = vec![e.to_string()];
                    continue;
                }
            };

            match result.status {
                WorkerStatus::PlanConflict => {
                    let changed = self.git.changed_paths(worktree)?;
                    if !changed.is_empty() {
                        // A conflict that also wrote code is not a conflict report; it is an
                        // unreviewed change, and it goes back the way any other rejection does.
                        findings = vec![format!(
                            "you reported a plan conflict but changed {changed:?}; a plan conflict \
                             must leave the working tree untouched"
                        )];
                        continue;
                    }
                    return Ok(UnitOutcome::Conflict(
                        result.conflict.unwrap_or(result.summary),
                    ));
                }
                WorkerStatus::Failed => {
                    findings = vec![format!(
                        "the previous attempt reported failure: {}",
                        result.summary
                    )];
                }
                WorkerStatus::Completed => {
                    match self.verify_unit(plan, unit, worktree, sessions).await? {
                        Ok(()) => {
                            let sha = self.git.commit_all(
                                worktree,
                                &format!(
                                    "hwahap({}): {}\n\nplan-digest: {}\nunit: {}",
                                    unit.id,
                                    unit.title,
                                    plan.digest()?,
                                    unit.id
                                ),
                            )?;
                            let _ = sha;
                            return Ok(UnitOutcome::Accepted);
                        }
                        Err(rejected) => findings = rejected,
                    }
                }
            }

            if attempt == MAX_ATTEMPTS - 1 {
                let diagnosis = self
                    .ask(
                        sessions,
                        Role::FailureDiagnosis,
                        Some(unit.id.clone()),
                        prompts::failure_diagnosis(unit, attempt, &findings.join("\n")),
                    )
                    .await?;
                let diagnosis = ReviewResult::parse(&diagnosis.final_message)?;
                if diagnosis.verdict == Verdict::Fail {
                    self.git.reset_hard(worktree, &checkpoint)?;
                    return Ok(UnitOutcome::Blocked(format!(
                        "{} could not be built after {attempt} attempts:\n{}",
                        unit.id,
                        diagnosis
                            .findings
                            .iter()
                            .map(|f| format!("- {f}"))
                            .collect::<Vec<_>>()
                            .join("\n")
                    )));
                }
            }
        }

        self.git.reset_hard(worktree, &checkpoint)?;
        Ok(UnitOutcome::Blocked(format!(
            "{} failed {MAX_ATTEMPTS} attempts:\n{}",
            unit.id,
            findings.join("\n")
        )))
    }

    /// Host-side verification. Nothing here believes the agent.
    #[allow(clippy::type_complexity)]
    async fn verify_unit(
        &self,
        plan: &Plan,
        unit: &Unit,
        worktree: &Path,
        sessions: &dyn Sessions,
    ) -> Result<std::result::Result<(), Vec<String>>> {
        let changed = self.git.changed_paths(worktree)?;
        if changed.is_empty() {
            return Ok(Err(vec![
                "the attempt reported completion but changed nothing".to_string(),
            ]));
        }
        let outside = paths_outside(&unit.paths, &changed);
        if !outside.is_empty() {
            return Ok(Err(vec![format!(
                "these paths are outside {}'s declared scope {:?} and were discarded: {outside:?}",
                unit.id, unit.paths
            )]));
        }

        for test in plan.tests_for(&unit.id) {
            let output = self.run_command(worktree, &test.command).await?;
            if !output.success {
                return Ok(Err(vec![format!(
                    "`{}` failed:\n{}",
                    test.command,
                    tail(&output.combined, 4_000)
                )]));
            }
        }

        // The reviewer is read-only. That is enforced by comparing the tree before and after,
        // because a permission callback that is never invoked proves nothing.
        // Stage first: a unit's new files are untracked, and `git diff HEAD` does not show
        // untracked content. A reviewer handed an empty diff would pass everything.
        self.git.run_in(worktree, &["add", "-A"])?;
        let before = self.git.changed_paths(worktree)?;
        let diff = self.git.run_in(worktree, &["diff", "--cached", "HEAD"])?;
        let review = self
            .ask(
                sessions,
                Role::UnitReviewer,
                Some(unit.id.clone()),
                prompts::unit_reviewer(plan, unit, &tail(&diff, 200_000)),
            )
            .await?;
        let after = self.git.changed_paths(worktree)?;
        if before != after {
            return Ok(Err(vec![
                "the review session changed the working tree, so its verdict was discarded"
                    .to_string(),
            ]));
        }

        let review = ReviewResult::parse(&review.final_message)?;
        if review.verdict == Verdict::Fail {
            return Ok(Err(review.findings));
        }
        Ok(Ok(()))
    }

    async fn finalize(&self, mut run: Run, sessions: &dyn Sessions) -> Result<StepOutcome> {
        let plan = self.require_plan()?;
        let worktree = self.store.worktree_path();

        let suite = self.run_command(&worktree, &plan.full_suite).await?;
        if !suite.success {
            run.state = RunState::Blocked {
                reason: format!(
                    "every unit was accepted but the full suite `{}` failed:\n{}",
                    plan.full_suite,
                    tail(&suite.combined, 4_000)
                ),
            };
            self.store.write_run(&*self.clock, &run)?;
            return Ok(self.report(&run, self.describe(&run, Some(&plan))?));
        }

        let diff = self.git.run_in(
            &worktree,
            &["diff", &format!("{}...HEAD", plan.base_branch)],
        )?;
        let review = self
            .ask(
                sessions,
                Role::FinalReview,
                None,
                prompts::final_review(&render::plan_markdown(&plan)?, &tail(&diff, 400_000)),
            )
            .await?;
        let review = ReviewResult::parse(&review.final_message)?;
        if review.verdict == Verdict::Fail {
            run.state = RunState::Blocked {
                reason: format!(
                    "the final review rejected the branch:\n{}",
                    review
                        .findings
                        .iter()
                        .map(|f| format!("- {f}"))
                        .collect::<Vec<_>>()
                        .join("\n")
                ),
            };
            self.store.write_run(&*self.clock, &run)?;
            return Ok(self.report(&run, self.describe(&run, Some(&plan))?));
        }

        let head = self.git.run_in(&worktree, &["rev-parse", "HEAD"])?;
        self.git.push(&worktree, "origin", &run.branch)?;
        let report = self.report_markdown(&plan, &run);
        self.store.write_report(&report)?;
        let pr = self.forge.create_draft(
            &worktree,
            &plan.base_branch,
            &run.branch,
            &plan.goal.statement,
            &report,
        )?;

        run.reviewed_head = Some(head);
        run.state = RunState::AwaitingAdjustOrShip {
            pr_url: pr.url.clone(),
            challenge: plan.digest()?.challenge(),
        };
        self.store.write_run(&*self.clock, &run)?;
        Ok(self.report(&run, self.describe(&run, Some(&plan))?))
    }

    fn adjust(&self, mut run: Run, user_input: Option<&str>) -> Result<StepOutcome> {
        let plan = self.require_plan()?;
        let Some(input) = user_input else {
            return Ok(self.report(&run, self.describe(&run, Some(&plan))?));
        };
        if input.trim().is_empty() {
            return Ok(self.report(&run, self.describe(&run, Some(&plan))?));
        }

        // An adjustment re-opens PLAN at the same revision's successor. Accepted units stay
        // accepted; the freeze gate decides which of them the new answers invalidate.
        let mut plan = plan;
        plan.revision += 1;
        plan.frozen = None;
        plan.reviews = crate::plan::PlanReviews::default();
        self.save_plan(&plan)?;

        run.revision = plan.revision;
        run.state = RunState::Deciding;
        self.store.write_run(&*self.clock, &run)?;
        Ok(self.report(
            &run,
            format!(
                "Hwahap will fold this into the plan as revision {}:\n\n{}\n\nIt will ask about \
                 anything that changes a decision you already made.",
                plan.revision,
                input.trim()
            ),
        ))
    }

    // ----------------------------------------------------------------- helpers

    async fn ask(
        &self,
        sessions: &dyn Sessions,
        role: Role,
        unit: Option<String>,
        prompt: String,
    ) -> Result<SessionOutcome> {
        let cwd = match crate::acp::access_for(role) {
            // Writers see only the run worktree. Readers see the repository, because a reviewer
            // that cannot read the code it is reviewing is not a reviewer.
            crate::acp::Access::WorkspaceWrite => self.store.worktree_path(),
            crate::acp::Access::ReadOnly => {
                let worktree = self.store.worktree_path();
                if worktree.exists() {
                    worktree
                } else {
                    self.repo_root.clone()
                }
            }
        };
        let spec = SessionSpec {
            cwd,
            role,
            unit,
            prompt,
        };
        let outcome = sessions.run(&spec).await?;
        outcome.receipt.verify()?;
        self.store.write_artifact(
            &format!(
                "receipt-{}-{}.json",
                role.as_str(),
                self.clock.now().replace(':', "-")
            ),
            &serde_json::to_string_pretty(&outcome.receipt)
                .map_err(|e| Error::Internal(e.to_string()))?,
        )?;
        Ok(outcome)
    }

    fn apply_decisions(&self, plan: &mut Plan, final_message: &str) -> Result<()> {
        let (decisions, not_applicable) = proposal::DecisionsProposal::parse(final_message, plan)?;
        plan.decisions.extend(decisions);
        for na in not_applicable {
            // Recorded as a proposal only. The surface stays applicable until the user types
            // `S<n>=NA`, which is what [`Engine::record_answers`] acts on.
            plan.open_items.push(crate::plan::OpenItem {
                id: format!("NA-{}", na.surface),
                decision_id: String::new(),
                detail: format!(
                    "{} is proposed as not applicable ({}); confirm with {}=NA",
                    na.surface, na.reason, na.surface
                ),
            });
        }
        Ok(())
    }

    fn record_answers(&self, plan: &mut Plan, directives: &[Directive]) -> Result<()> {
        let now = self.clock.now();
        for directive in directives {
            match directive {
                Directive::Decision { id, selection } => {
                    let Some(decision) = plan.decision_mut(id) else {
                        return Err(Error::Rejected(format!(
                            "{id} is not a decision in this plan"
                        )));
                    };
                    if let Selection::Alternative { id: alt } = selection {
                        if !decision.alternatives.iter().any(|a| &a.id == alt) {
                            return Err(Error::Rejected(format!("{id} has no alternative {alt}")));
                        }
                    }
                    let identity = decision.identity_digest()?;
                    let recommendation = matches!(selection, Selection::Recommendation)
                        .then(|| decision.recommendation_digest())
                        .transpose()?;
                    decision.answer = Some(Answer {
                        text: format!("{id}={}", describe_selection(selection)),
                        selection: selection.clone(),
                        ts: now.clone(),
                        identity,
                        recommendation,
                    });
                }
                Directive::Surface { id } => {
                    let Some(surface) = Surface::parse(id) else {
                        return Err(Error::Rejected(format!("{id} is not one of S1..S12")));
                    };
                    let reason = plan
                        .open_items
                        .iter()
                        .find(|item| item.id == format!("NA-{id}"))
                        .map(|item| item.detail.clone())
                        .unwrap_or_else(|| "the user marked this surface not applicable".into());
                    plan.surfaces.insert(
                        surface.id().to_string(),
                        SurfaceStatus::NotApplicable {
                            reason,
                            answer: Answer {
                                text: format!("{id}=NA"),
                                selection: Selection::NotApplicable,
                                ts: now.clone(),
                                identity: Digest::zero(),
                                recommendation: None,
                            },
                        },
                    );
                    plan.open_items.retain(|item| item.id != format!("NA-{id}"));
                }
                Directive::ConfirmPlan { .. } | Directive::Ship { .. } => {}
            }
        }
        Ok(())
    }

    fn save_plan(&self, plan: &Plan) -> Result<()> {
        self.store.write_plan(plan)?;
        self.store
            .write_plan_markdown(&render::plan_markdown(plan)?)
    }

    fn require_plan(&self) -> Result<Plan> {
        let plan = self
            .store
            .read_plan()?
            .ok_or_else(|| Error::Corrupt("the run has no plan.json".into()))?;
        plan.require_supported_schema()?;
        Ok(plan)
    }

    async fn run_command(&self, cwd: &Path, command: &str) -> Result<CommandOutput> {
        // Run through a shell because the plan's commands are written the way a person writes
        // them, with pipes and flags. The command comes from a frozen plan the user confirmed.
        let child = tokio::process::Command::new("sh")
            .arg("-c")
            .arg(command)
            .current_dir(cwd)
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
            .map_err(|e| Error::command(command, e.to_string()))?;

        let timeout = std::time::Duration::from_secs(self.config.test_timeout_secs);
        let finished = tokio::time::timeout(timeout, child.wait_with_output()).await;
        match finished {
            Ok(Ok(output)) => Ok(CommandOutput {
                success: output.status.success(),
                combined: format!(
                    "{}{}",
                    String::from_utf8_lossy(&output.stdout),
                    String::from_utf8_lossy(&output.stderr)
                ),
            }),
            Ok(Err(e)) => Err(Error::command(command, e.to_string())),
            Err(_) => Ok(CommandOutput {
                success: false,
                combined: format!(
                    "the command did not finish within {}s and was treated as a failure",
                    self.config.test_timeout_secs
                ),
            }),
        }
    }

    fn report(&self, run: &Run, message: String) -> StepOutcome {
        StepOutcome {
            run_id: run.run_id.clone(),
            phase: run.state.phase().name().to_string(),
            state: run.state.name().to_string(),
            next: run.state.next().name().to_string(),
            message,
            plan_digest: run.plan_digest.as_ref().map(|d| d.to_string()),
            pr_url: run.state.pr_url().map(str::to_string),
        }
    }

    fn describe(&self, run: &Run, plan: Option<&Plan>) -> Result<String> {
        Ok(match &run.state {
            RunState::Inspecting => "Hwahap is reading the repository.".into(),
            RunState::Deciding => match plan {
                Some(plan) => {
                    let frontier = frontier::derive(plan)?;
                    render::frontier_markdown(plan, &frontier.ready)?
                }
                None => "Hwahap is deciding.".into(),
            },
            RunState::Proving => "Hwahap is proving the plan.".into(),
            RunState::AwaitingConfirmation { challenge } => format!(
                "Read `.hwahap/plan.md`. To freeze it, type exactly:\n\nCONFIRM PLAN {challenge}"
            ),
            RunState::Coding { unit, attempt } => format!(
                "Building {unit} (attempt {attempt}). {} unit(s) accepted so far.",
                run.accepted_units.len()
            ),
            RunState::FinalVerifying => "Running the full suite and the final review.".into(),
            RunState::AwaitingAdjustOrShip { pr_url, challenge } => match plan {
                Some(plan) => self.summary(plan, run, pr_url, challenge),
                None => format!("{pr_url} is ready. Type `SHIP {challenge}` to mark it ready."),
            },
            RunState::Shipped { pr_url } => format!("{pr_url} is ready for review."),
            RunState::Blocked { reason } => format!("Hwahap stopped: {reason}"),
            RunState::PlanConflict { unit, detail } => {
                format!("{unit} hit a plan conflict: {detail}")
            }
        })
    }

    fn summary(&self, plan: &Plan, run: &Run, pr_url: &str, challenge: &str) -> String {
        format!(
            "Hwahap cycle completed\n\n\
             Units                 {}/{} accepted\n\
             Full suite            passed\n\
             Final review          passed\n\
             Draft PR              {pr_url}\n\n\
             Tell Hwahap what to change, or type exactly:\n\nSHIP {challenge}",
            run.accepted_units.len(),
            plan.units.iter().filter(|u| !u.probe).count(),
        )
    }

    fn report_markdown(&self, plan: &Plan, run: &Run) -> String {
        format!(
            "## Conclusion\n\n{}\n\n## Evidence\n\n- Plan digest: `{}`\n- Units accepted: {}\n\
             - Full suite: `{}`\n\n## Verification\n\nEvery unit's tests and the full suite were run \
             by Hwahap and judged by exit status. Changed paths were checked against each unit's \
             declared scope.\n\n## Limitations\n\nHwahap opened this pull request as a draft and did \
             not merge it.\n",
            plan.goal.statement,
            run.plan_digest
                .as_ref()
                .map(|d| d.to_string())
                .unwrap_or_default(),
            run.accepted_units.join(", "),
            plan.full_suite,
        )
    }
}

enum Resolved {
    Started(StepOutcome),
    Advance(Run),
}

enum UnitOutcome {
    Accepted,
    Conflict(String),
    Blocked(String),
}

struct CommandOutput {
    success: bool,
    combined: String,
}

fn describe_selection(selection: &Selection) -> String {
    match selection {
        Selection::Recommendation => "REC".into(),
        Selection::Alternative { id } => id.clone(),
        Selection::Other { value } => format!("OTHER: {value}"),
        Selection::Unknown => "UNKNOWN".into(),
        Selection::NotApplicable => "NA".into(),
    }
}

/// A stable, filesystem-safe run identifier derived from the date and the request.
fn goal_id(now: &str, request: &str) -> String {
    let date: String = now.chars().take(10).collect();
    let slug: String = request
        .chars()
        .flat_map(|c| c.to_lowercase())
        .map(|c| if c.is_alphanumeric() { c } else { '-' })
        .collect::<String>()
        .split('-')
        .filter(|part| !part.is_empty())
        .take(5)
        .collect::<Vec<_>>()
        .join("-");
    if slug.is_empty() {
        date
    } else {
        format!("{date}-{slug}")
    }
}

/// The last `limit` bytes of `text`, cut at a character boundary.
fn tail(text: &str, limit: usize) -> String {
    if text.len() <= limit {
        return text.to_string();
    }
    let mut start = text.len() - limit;
    while start < text.len() && !text.is_char_boundary(start) {
        start += 1;
    }
    format!("…\n{}", &text[start..])
}

impl Next {
    fn name(&self) -> &'static str {
        match self {
            Next::Continue => "continue",
            Next::AwaitUser => "await_user",
            Next::Completed => "completed",
            Next::Blocked => "blocked",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_goal_id_is_dated_slugged_and_filesystem_safe() {
        assert_eq!(
            goal_id("2026-09-04T10:00:00Z", "Add a dry-run flag to apply"),
            "2026-09-04-add-a-dry-run-flag"
        );
        assert_eq!(
            goal_id("2026-09-04T10:00:00Z", "  Fix   the   BUG  "),
            "2026-09-04-fix-the-bug"
        );
    }

    #[test]
    fn a_goal_id_survives_a_request_with_no_usable_characters() {
        assert_eq!(goal_id("2026-09-04T10:00:00Z", "!!! ???"), "2026-09-04");
        assert_eq!(goal_id("2026-09-04T10:00:00Z", ""), "2026-09-04");
    }

    #[test]
    fn a_goal_id_keeps_unicode_word_characters() {
        let id = goal_id("2026-09-04T10:00:00Z", "드라이런 기능 추가");
        assert_eq!(id, "2026-09-04-드라이런-기능-추가");
        assert!(!id.contains(' '));
    }

    #[test]
    fn a_goal_id_never_contains_a_path_separator() {
        for request in ["a/b", "../escape", "a\\b", "C:\\x"] {
            let id = goal_id("2026-09-04T10:00:00Z", request);
            assert!(!id.contains('/'), "{id}");
            assert!(!id.contains('\\'), "{id}");
            assert!(!id.contains(".."), "{id}");
        }
    }

    #[test]
    fn the_same_request_on_the_same_day_yields_the_same_id() {
        assert_eq!(
            goal_id("2026-09-04T00:00:00Z", "add dry-run"),
            goal_id("2026-09-04T23:59:59Z", "add dry-run")
        );
    }

    #[test]
    fn tail_returns_short_text_unchanged() {
        assert_eq!(tail("short", 100), "short");
        assert_eq!(tail("", 10), "");
    }

    #[test]
    fn tail_truncates_from_the_front_and_marks_it() {
        let long = "x".repeat(100);
        let cut = tail(&long, 10);
        assert!(cut.starts_with('…'), "{cut}");
        assert_eq!(cut.chars().filter(|c| *c == 'x').count(), 10);
    }

    #[test]
    fn tail_never_splits_a_multi_byte_character() {
        let text = "가".repeat(100);
        let cut = tail(&text, 10);
        // Slicing mid-character would have panicked; reaching here at all is most of the assertion.
        assert!(
            cut.chars().all(|c| c == '…' || c == '\n' || c == '가'),
            "{cut}"
        );
    }

    #[test]
    fn selections_render_back_into_the_grammar_the_user_typed() {
        assert_eq!(describe_selection(&Selection::Recommendation), "REC");
        assert_eq!(
            describe_selection(&Selection::Alternative { id: "ALT2".into() }),
            "ALT2"
        );
        assert_eq!(
            describe_selection(&Selection::Other {
                value: "fail after 10s".into()
            }),
            "OTHER: fail after 10s"
        );
        assert_eq!(describe_selection(&Selection::Unknown), "UNKNOWN");
        assert_eq!(describe_selection(&Selection::NotApplicable), "NA");
    }

    #[test]
    fn a_unit_gets_at_most_three_attempts() {
        // The constant is the whole retry policy; a change to it is a change to the contract with
        // the user about how long a stuck unit burns tokens.
        assert_eq!(MAX_ATTEMPTS, 3);
    }
}
