try:
    from .test_dependency_kit import *
except ImportError:
    from test_dependency_kit import *


class DependencyMarkdownTests(DependencyIntegrityTests):
    def test_hwahap_markdown_is_bounded_and_local_links_resolve(self) -> None:
        repository = ROOT.parents[2]
        documents = [ROOT.parents[2] / "README.md",
                     *sorted((repository / "skills/hwahap").rglob("*.md"))]
        for document in documents:
            with self.subTest(document=document.relative_to(repository)):
                self.assertLessEqual(len(document.read_text(encoding="utf-8").splitlines()), 200)
                for target in re.findall(r"\[[^]]+\]\(([^)]+\.md)\)", document.read_text(encoding="utf-8")):
                    if "://" not in target:
                        self.assertTrue((document.parent / target).resolve().is_file(), target)
