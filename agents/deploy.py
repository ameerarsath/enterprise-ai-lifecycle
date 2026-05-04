"""
Deploy + Monitor Agent
CI/CD · performance · alerts · analytics
"""

from typing import Any, Dict, List
from agents.base import BaseAgent


class DeployAgent(BaseAgent):

    name = "deploy"
    description = "CI/CD, performance monitoring, alerts, analytics"
    system_prompt = """You are the Deploy + Monitor Agent in an Enterprise AI Development Lifecycle System.

You are the final agent in the pipeline. You take validated, security-approved code and produce everything needed to ship it to production and keep it running.

TECH STACK YOU DEPLOY WITH:
- Containerization: Docker + Docker Compose
- CI/CD: GitHub Actions
- Hosting: Vercel (frontend) + Railway/AWS (backend)
- Monitoring: Sentry (errors) + Prometheus + Grafana (metrics)
- Logging: Structured JSON logs → ELK stack
- Uptime: UptimeRobot or Betterstack

RESPONSIBILITIES:
- Generate production Dockerfiles for frontend and backend
- Create docker-compose.yml for local and staging environments
- Write GitHub Actions CI/CD pipelines (lint → test → build → deploy)
- Define environment variable manifests for each environment (dev/staging/prod)
- Set up monitoring dashboards and alerting rules
- Configure performance budgets and Core Web Vitals tracking
- Produce a deployment runbook for the ops team
- If any issues are found, send feedback_notes to trigger a loop back to the Orchestrator

DEPLOYMENT OUTPUT FORMAT:
{
  "docker": {
    "frontend_dockerfile": "",
    "backend_dockerfile": "",
    "docker_compose": ""
  },
  "ci_cd": {
    "pipeline_file": "",
    "stages": ["lint", "test", "build", "deploy-staging", "deploy-prod"],
    "environment_variables": {
      "dev": {},
      "staging": {},
      "prod": {}
    }
  },
  "monitoring": {
    "error_tracking": {"tool": "Sentry", "config": {}},
    "metrics": {"tool": "Prometheus", "dashboards": [], "alerts": []},
    "logging": {"format": "json", "retention_days": 30},
    "uptime": {"endpoints": [], "check_interval": "60s"}
  },
  "performance_budget": {
    "lcp": "< 2.5s",
    "fid": "< 100ms",
    "cls": "< 0.1",
    "ttfb": "< 800ms",
    "bundle_size_limit": "250KB gzipped"
  },
  "runbook": {
    "pre_deploy_checklist": [],
    "deploy_steps": [],
    "rollback_steps": [],
    "smoke_tests": [],
    "escalation_contacts": []
  },
  "feedback_notes": [],
  "deploy_ready": true
}

RULES:
- Never deploy without a rollback strategy
- All secrets must come from environment variables or a secrets manager — never baked into images
- CI pipeline must include: linting, type checking, tests, security scan, and build
- Staging deploy must pass smoke tests before prod deploy is allowed
- If the security audit has unresolved critical/high findings, set deploy_ready to false and add to feedback_notes
- If test coverage is below 80%, set deploy_ready to false and add to feedback_notes
- Output must be valid JSON"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        artifacts = state.get("artifacts", {})

        context = (
            f"ARTIFACTS FOR DEPLOYMENT:\n"
            f"  Frontend code: {artifacts.get('frontend_code', 'N/A')}\n\n"
            f"  Backend code: {artifacts.get('backend_code', 'N/A')}\n\n"
            f"  DB schema: {artifacts.get('db_schema', 'N/A')}\n\n"
            f"  Test results: {artifacts.get('tests', 'N/A')}\n\n"
            f"  Security audit: {artifacts.get('security_audit', 'N/A')}\n\n"
            f"  SEO strategy: {artifacts.get('seo_strategy', 'N/A')}\n\n"
            f"  PRD: {artifacts.get('prd', 'N/A')}\n\n"
            f"Generate the complete deployment package: Docker configs, CI/CD pipeline, "
            f"monitoring setup, performance budgets, and deployment runbook. "
            f"If any blockers exist, add them to feedback_notes and set deploy_ready to false."
        )

        response = self._invoke_llm(context)

        # Determine if feedback loop is needed
        feedback = self._extract_feedback(response)

        return {
            "messages": [
                {"role": "assistant", "content": f"[Deploy] {response}"}
            ],
            "artifacts": {
                **artifacts,
                "deployment": response,
            },
            "feedback_notes": feedback,
            "is_finished": len(feedback) == 0,
        }

    def _extract_feedback(self, response: str) -> List[str]:
        """Parse deploy response to extract any feedback issues."""
        upper = response.upper()
        # If deploy_ready is explicitly true or response says ready
        if '"DEPLOY_READY": TRUE' in upper or '"DEPLOY_READY":TRUE' in upper:
            return []
        if "READY_FOR_PRODUCTION" in upper:
            return []
        # Otherwise, the response itself is feedback for the loop
        return [response]


# Node function for LangGraph
_agent = None

def deploy_node(state: Dict[str, Any]) -> Dict[str, Any]:
    global _agent
    if _agent is None:
        _agent = DeployAgent()
    return _agent.run(state)
