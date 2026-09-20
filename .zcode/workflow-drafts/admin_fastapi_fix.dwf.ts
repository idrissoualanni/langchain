// Workflow to fix FastAPI query parameters in admin observability and dashboard
// No imports – use global helpers provided by the runtime

phase('Patch observability query parameters');
await agent('observability-params-fix').ask('Replace every fastapi.Field used for request parameters in app/api/admin/observability.py with fastapi.Query. For each endpoint (get_recent_runs, get_recent_runs_detail, get_recent_traces, get_trace_detail, get_recent_evaluations, get_evaluation_detail, get_model_usage, get_error_log, get_recent_models, get_recent_examples, get_runs, get_models, get_metrics) change signatures like limit: int = Field(default=50, ge=1, le=500) to limit: int = Query(default=50, ge=1, le=500) and days: int = Field(default=7, ge=1, le=90) to days: int = Query(default=7, ge=1, le=90).');

phase('Patch dashboard activity-stats signature');
await agent('dashboard-activity-stats-fix').ask('Edit app/api/admin/dashboard.py: modify get_activity_stats signature to remove the SQLAlchemy Session dependency. Change to async def get_activity_stats(days: int = Query(default=7, ge=1, le=365), current_user: dict = Depends(get_current_admin_user)): and remove the db: Session = Depends(get_db) argument. Ensure the function uses the existing sqlite connection (conn) for its query.');

phase('Re-run lint and type-check');
await agent('frontend-lint').ask('npm run lint \u0026\u0026 npm run type-check');

phase('Re-run integration tests');
await agent('frontend-e2e-tests').ask('npm run test:e2e --filter admin \u0026\u0026 npm run test:e2e --filter video');

phase('Verify server starts cleanly');
await agent('backend-start-check').ask('python -m uvicorn app.main:app --port 8000 \u0026 sleep 5 \u0026\u0026 curl -s http://localhost:8000/health');

return 'Second workflow completed: FastAPI query parameters fixed, dashboard activity-stats works, lint & tests pass, server runs without 502.';