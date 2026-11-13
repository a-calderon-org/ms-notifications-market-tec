from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_app_service_startup_targets_fastapi_application():
    startup = (ROOT / "startup.sh").read_text(encoding="utf-8")

    assert '.python_packages/lib/site-packages' in startup
    assert 'export PYTHONPATH=' in startup
    assert "python -m uvicorn ms_notifications.api.main:app" in startup
    assert '--app-dir "${APP_ROOT}/src"' in startup
    assert "--host 0.0.0.0" in startup


def test_continuous_webjob_runs_queue_worker_from_deployment_root():
    webjob = (
        ROOT / "App_Data/jobs/continuous/notifications-worker/run.py"
    ).read_text(encoding="utf-8")

    assert 'parents[4]' in webjob
    assert 'web_root / ".python_packages" / "lib" / "site-packages"' in webjob
    assert 'web_root / "src"' in webjob
    assert "from ms_notifications.worker import main" in webjob


def test_deployment_uses_manual_oidc_without_publish_profile():
    workflow = (
        ROOT / ".github/workflows/deploy-development.yml"
    ).read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "id-token: write" in workflow
    assert "azure/login@v3" in workflow
    assert "azure/webapps-deploy@v3" in workflow
    assert "publish-profile" not in workflow
    assert "AZURE_WEBAPP_PUBLISH_PROFILE" not in workflow
