from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from backend.app.database import Base

class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    storage_path = Column(String, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    raw_text = Column(Text, nullable=True)
    
    # Parsed structured data
    parsed_skills = Column(JSON, nullable=True)  # List of skills e.g., ["React", "FastAPI"]
    parsed_experience = Column(Float, nullable=True)  # Experience in years
    parsed_location = Column(String, nullable=True)
    linkedin_url = Column(String, nullable=True)
    github_url = Column(String, nullable=True)
    portfolio_url = Column(String, nullable=True)
    
    # Relationships
    applications = relationship("Application", back_populates="resume", cascade="all, delete-orphan")

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    company = Column(String, index=True)
    description = Column(Text)
    url = Column(String, unique=True, index=True)
    location = Column(String, nullable=True)
    
    # Extracted fields for rule-based filter matching
    skills_required = Column(JSON, nullable=True)  # List of skills
    experience_required = Column(Float, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    applications = relationship("Application", back_populates="job", cascade="all, delete-orphan")

class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    resume_id = Column(Integer, ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    
    # Status transitions: "matched" -> "tailored" -> "approved" -> "applying" -> "applied" / "failed" / "rejected"
    status = Column(String, default="matched", index=True)
    match_score = Column(Float, nullable=True)
    
    # Paths and texts for tailored outputs
    tailored_resume_path = Column(String, nullable=True)
    cover_letter = Column(Text, nullable=True)
    
    # ATS and Critic fields
    ats_score = Column(Float, nullable=True)
    ats_critic_feedback = Column(JSON, nullable=True)  # Missing keywords list, recommendations
    ats_type = Column(String, default="Generic")  # "Greenhouse", "Lever", "Workday", "Ashby", "Generic"
    application_type = Column(String, default="Unknown", nullable=True)  # "Easy Apply", "External Website", "Recruiter Chatbot", "Assessment/Test", "OTP/Login", "Resume Required", "Unknown"
    
    # Log files and application timestamps
    applied_at = Column(DateTime, nullable=True)
    logs = Column(Text, nullable=True)
    
    # Relationships
    resume = relationship("Resume", back_populates="applications")
    job = relationship("Job", back_populates="applications")

class UserCredential(Base):
    __tablename__ = "user_credentials"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, unique=True, index=True)  # "linkedin", "naukri", "indeed"
    username = Column(String, nullable=False)
    encrypted_password = Column(String, nullable=False)
    session_cookies = Column(JSON, nullable=True)  # Store playwright session state
    last_login_at = Column(DateTime, nullable=True)

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="Sumit Kumar")
    email = Column(String, default="sumit@gmail.com")
    phone = Column(String, default="+91 7011676185")
    experience_years = Column(Float, default=3.0)
    current_ctc = Column(String, default="₹5 LPA")
    expected_ctc = Column(String, default="₹8 LPA")
    notice_period = Column(String, default="Immediate")
    current_location = Column(String, default="Noida")
    preferred_locations = Column(JSON, default=["Noida", "Delhi", "Gurgaon", "Remote"])
    work_authorization = Column(String, default="India")
    willing_to_relocate = Column(String, default="Yes")
    remote_preference = Column(String, default="Hybrid")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    target_roles = Column(JSON, default=["AI Engineer", "GenAI Engineer", "Backend Engineer"])
    minimum_salary = Column(Float, default=700000)
    employment_type = Column(JSON, default=["Full-time"])
    preferred_companies = Column(JSON, default=["Microsoft", "Google", "OpenAI"])
    created_at = Column(DateTime, default=datetime.utcnow)

class AnswerBank(Base):
    __tablename__ = "answer_bank"

    id = Column(Integer, primary_key=True, index=True)
    question_key = Column(String, index=True)
    question_pattern = Column(String, index=True)
    stored_answer = Column(Text, nullable=False)
    category = Column(String, default="general")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

