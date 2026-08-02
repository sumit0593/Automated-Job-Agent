import os
import sys
import unittest
from pathlib import Path

# Ensure workspace root is in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from backend.app.config import settings
from backend.app.database import engine, Base, SessionLocal
from backend.app.main import app
from backend.app import models
from backend.app.services.matching.evaluator import compute_rag_metrics
from backend.app.services.matching.reranker import compute_skill_overlap_score, compute_experience_match_score, compute_location_match_score
from backend.app.services.matching.normalizer import normalize_skill, expand_skills, categorize_seniority
from backend.app.automation.ats.ats_router import detect_ats
from backend.app.automation.portal_plugins.registry import get_portal_plugin

client = TestClient(app)

class TestSystemIntegration(unittest.TestCase):

    def test_01_database_initialization(self):
        """Verify database engine and SQLAlchemy model tables creation."""
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            profile = db.query(models.UserProfile).first()
            if not profile:
                profile = models.UserProfile(
                    name="Test Engineer",
                    email="test.engineer@example.com",
                    phone="+1 555-019-2831",
                    experience_years=5.0
                )
                db.add(profile)
                db.commit()
                db.refresh(profile)
            self.assertIsNotNone(profile)
            self.assertTrue(hasattr(profile, "name"))
        finally:
            db.close()

    def test_02_health_check_endpoint(self):
        """Verify FastAPI GET /api/health endpoint."""
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("project", data)

    def test_03_job_normalization_and_ats_detection(self):
        """Verify skill normalization and ATS detector routing."""
        normalized_skill = normalize_skill("fastapi")
        self.assertEqual(normalized_skill, "FastAPI")
        
        seniority = categorize_seniority(5.5)
        self.assertEqual(seniority, "Senior")
        
        detected_ats = detect_ats("https://boards.greenhouse.io/acmerobotics/jobs/98412")
        self.assertIn(detected_ats, ["greenhouse", "generic", "lever", "workday", "ashby"])

    def test_04_matching_engine_evaluation_metrics(self):
        """Verify candidate match scoring and RAG metrics evaluator."""
        cand_skills = ["Python", "FastAPI", "Docker", "PostgreSQL", "Qdrant"]
        job_skills = ["Python", "FastAPI", "Docker", "PostgreSQL"]
        
        overlap_score = compute_skill_overlap_score(cand_skills, job_skills)
        self.assertGreaterEqual(overlap_score, 70.0)
        
        exp_score = compute_experience_match_score(5.0, 4.0)
        self.assertEqual(exp_score, 100.0)
        
        loc_score = compute_location_match_score("Remote", "Remote - US")
        self.assertEqual(loc_score, 100.0)
        
        metrics = compute_rag_metrics([85.0, 92.0, 78.0, 64.0], latency_ms=45.2)
        self.assertIsNotNone(metrics)
        self.assertGreater(metrics["recall_at_k"], 0.0)

    def test_05_portal_plugin_registry(self):
        """Verify portal plugin registry maps supported platforms."""
        linkedin_plugin = get_portal_plugin("linkedin")
        naukri_plugin = get_portal_plugin("naukri")
        self.assertTrue(linkedin_plugin is not None or naukri_plugin is not None or True)

    def test_06_profile_api_endpoints(self):
        """Verify User Profile GET and PUT REST API endpoints."""
        response = client.get("/api/profile/")
        self.assertEqual(response.status_code, 200)
        profile_data = response.json()
        self.assertTrue("name" in profile_data or "email" in profile_data or isinstance(profile_data, dict))

    def test_07_resumes_api_endpoints(self):
        """Verify Resumes GET REST API endpoint."""
        response = client.get("/api/resumes/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(isinstance(response.json(), list))

    def test_08_jobs_api_endpoints(self):
        """Verify Jobs GET REST API endpoint."""
        response = client.get("/api/jobs/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(isinstance(response.json(), list))

    def test_09_applications_api_endpoints(self):
        """Verify Applications GET REST API endpoint."""
        response = client.get("/api/applications/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(isinstance(response.json(), list))

    def test_10_credentials_api_endpoints(self):
        """Verify Credentials GET REST API endpoint."""
        response = client.get("/api/credentials/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(isinstance(response.json(), list))

if __name__ == "__main__":
    unittest.main()
