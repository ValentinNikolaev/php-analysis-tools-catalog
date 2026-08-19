from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def test_pages_workflow_is_reusable_without_unconditional_update_trigger(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")

        self.assertIn("  workflow_call:", workflow)
        self.assertIn("  workflow_dispatch:", workflow)
        self.assertNotIn("  workflow_run:", workflow)
        self.assertIn("      deploy:", workflow)
        self.assertIn("ref: ${{ inputs.ref || github.sha }}", workflow)
        self.assertIn("if: github.event_name != 'workflow_call' || inputs.deploy", workflow)
        self.assertIn("actions/upload-pages-artifact@7b1f4a764d45c48632c6b24a0339c27f5614fb0b # v4", workflow)
        self.assertIn("actions/deploy-pages@d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e # v4", workflow)

    def test_catalog_workflow_pushes_validated_changes_to_the_default_branch(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "update-catalog.yml").read_text(encoding="utf-8")

        mutation = workflow.index("python scripts/update_catalog.py")
        validation = workflow.rindex("python scripts/validate_catalog.py")
        tests = workflow.index("python -m unittest discover -s tests")
        publication = workflow.index('git push origin "HEAD:${DEFAULT_BRANCH}"')
        self.assertLess(mutation, validation)
        self.assertLess(validation, tests)
        self.assertLess(tests, publication)
        self.assertIn("python scripts/generate_site.py --output site-dist", workflow)
        self.assertIn("python scripts/generate_exports.py --as-of", workflow)
        self.assertIn("git add --", workflow)
        self.assertIn("            exports \\", workflow)
        self.assertIn("Verify generators are idempotent", workflow)
        self.assertIn("          ref: ${{ github.event.repository.default_branch }}", workflow)
        self.assertIn("          DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}", workflow)
        self.assertIn("      contents: write", workflow)
        self.assertIn("github-actions[bot]", workflow)
        self.assertNotIn("git add .", workflow)
        self.assertNotIn("peter-evans/create-pull-request", workflow)
        self.assertNotIn("pull-requests: write", workflow)

    def test_catalog_refresh_deploys_the_exact_committed_revision_via_reusable_pages_workflow(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "update-catalog.yml").read_text(encoding="utf-8")

        self.assertIn("      changed: ${{ steps.publish.outputs.changed }}", workflow)
        self.assertIn("      commit: ${{ steps.publish.outputs.commit }}", workflow)
        self.assertIn("  deploy-pages:", workflow)
        self.assertIn("    needs: update", workflow)
        self.assertIn("    if: needs.update.outputs.changed == 'true'", workflow)
        self.assertIn("    uses: ./.github/workflows/pages.yml", workflow)
        self.assertIn("      deploy: true", workflow)
        self.assertIn("      ref: ${{ needs.update.outputs.commit }}", workflow)

        deployment = workflow.index("  deploy-pages:")
        deploy_job = workflow[deployment:]
        self.assertIn("      contents: read", deploy_job)
        self.assertIn("      pages: write", deploy_job)
        self.assertIn("      id-token: write", deploy_job)
        self.assertNotIn("      contents: write", deploy_job)
        self.assertNotIn("actions/deploy-pages@", workflow)

    def test_external_actions_are_sha_pinned_and_runners_are_stable(self) -> None:
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            workflow = path.read_text(encoding="utf-8")
            self.assertNotIn("runs-on: ubuntu-latest", workflow, path.name)
            for action, revision in re.findall(r"uses:\s+([^\s@]+)@([^\s#]+)", workflow):
                if action.startswith("./"):
                    continue
                self.assertRegex(revision, r"^[0-9a-f]{40}$", f"{path.name}: {action}")

    def test_pages_build_validates_catalog_before_building(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertLess(workflow.index("python scripts/validate_catalog.py"), workflow.index("python scripts/generate_site.py"))

    def test_pull_requests_run_a_read_only_pages_build(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "pages-smoke.yml").read_text(encoding="utf-8")

        self.assertIn("  pull_request:", workflow)
        self.assertIn("    runs-on: ubuntu-24.04", workflow)
        self.assertIn("      contents: read", workflow)
        self.assertNotIn("pages: write", workflow)
        self.assertNotIn("id-token: write", workflow)
        self.assertNotIn("uses: ./.github/workflows/pages.yml", workflow)
        self.assertIn("actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803 # v6", workflow)
        self.assertIn("actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6", workflow)

        validation = workflow.index("python scripts/validate_catalog.py")
        tests = workflow.index("python -m unittest discover -s tests")
        build = workflow.index("python scripts/generate_site.py --output site-dist")
        self.assertLess(validation, tests)
        self.assertLess(tests, build)


if __name__ == "__main__":
    unittest.main()
