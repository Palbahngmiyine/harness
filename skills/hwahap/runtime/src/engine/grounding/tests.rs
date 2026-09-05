use super::*;
use crate::plan::Fact;

fn fixture() -> tempfile::TempDir {
    let dir = tempfile::tempdir().unwrap();
    assert!(std::process::Command::new("git")
        .args(["init", "-q"])
        .current_dir(dir.path())
        .status()
        .unwrap()
        .success());
    let git = Git::open(dir.path()).unwrap();
    git.run(&["config", "user.name", "Grounding Test"]).unwrap();
    git.run(&["config", "user.email", "grounding@example.invalid"])
        .unwrap();
    std::fs::write(dir.path().join("cited file.txt"), "\nalpha\n\nomega\n\n").unwrap();
    git.run(&["add", "cited file.txt"]).unwrap();
    git.run(&["commit", "-qm", "citation fixture"]).unwrap();
    dir
}

fn plan(source: &str) -> Plan {
    let mut plan = Plan::new("grounding", "main", "verify citations");
    plan.facts.push(Fact {
        id: "F1".into(),
        question: "Where is the fixture text?".into(),
        answer: "The tracked text file contains five lines".into(),
        sources: vec![source.into()],
    });
    plan
}

#[test]
fn verifies_committed_line_ranges_without_trimming_blank_lines() {
    let dir = fixture();
    for source in ["cited file.txt:1", "cited file.txt:2-5", "cited file.txt:5"] {
        verify_sources(&plan(source), dir.path()).unwrap();
    }
    std::fs::write(dir.path().join("cited file.txt"), "1\n2\n3\n4\n5\n6\n").unwrap();
    let err = verify_sources(&plan("cited file.txt:6"), dir.path()).unwrap_err();
    assert!(
        err.to_string().contains("committed file's 5 lines"),
        "{err}"
    );
}

#[test]
fn rejects_fabricated_untracked_unsafe_and_out_of_bounds_citations() {
    let dir = fixture();
    std::fs::write(dir.path().join("untracked.txt"), "uncommitted\n").unwrap();
    for source in [
        "missing.txt:1",
        "untracked.txt:1",
        "../cited file.txt:1",
        "/etc/passwd:1",
        "./cited file.txt:1",
        "a/../cited file.txt:1",
        ".git/config:1",
        "cited file.txt:0",
        "cited file.txt:3-2",
        "cited file.txt:1-6",
        "cited file.txt:-1",
        "cited file.txt",
    ] {
        assert!(
            verify_sources(&plan(source), dir.path()).is_err(),
            "accepted {source:?}"
        );
    }
}
